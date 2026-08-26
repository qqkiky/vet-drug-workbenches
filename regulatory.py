"""regulatory.py - Real regulatory data fetchers & parsers.

Fetches and normalises veterinary-biologics approval data from the official
regulators and maps it onto the canonical schema consumed downstream by
``db.ingest_dataset()``:

    region, species, product_type, product_name, approval_number,
    manufacturer, indication, dosage_form, strength, approval_date,
    status, source

Sources
-------
* USDA / CVB  -> "Current Veterinary Biologics Product Catalog" (PDF codebook)
* EMA / CVMP  -> Public "Veterinary Medicines" information website

Design principles (required by the integration spec)
----------------------------------------------------
1. Field mapping  : each source's native fields are mapped to the canonical
                    schema (see ``normalize_record`` + per-source mappers).
2. Error handling : every network / HTTP / parse failure is caught, logged
                    and reported via the returned ``meta`` dict. A fetcher
                    NEVER raises into the caller - it returns ``([], meta)``
                    so the pipeline can fall back gracefully.
3. Seamless       : output schema is identical to the sample data, so the
                    existing DB layer, diff engine, exports and UI keep
                    working untouched.
4. Downstream fit : records carry exactly the keys ``db.ingest_dataset`` reads.

Logging
-------
Call ``setup_logging()`` once at process start. Logs go to
``data/ingest.log`` (rotated) and the console.
"""
from __future__ import annotations

import concurrent.futures as cf
import html as _html_mod
import io
import logging
import os
import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_PATH = os.path.join(DATA_DIR, "ingest.log")

# Official entry points (replace / extend per site ToS & API changes).
USDA_CVB_CATALOG_URL = os.environ.get(
    "USDA_CVB_CATALOG_URL",
    "https://direct.aphis.usda.gov/sites/default/files/currentprodcodebook.pdf",
)
USDA_CVB_CATALOG_DATE = "2026-04-01"  # publication date of the current catalog
EMA_VET_BASE = os.environ.get(
    "EMA_VET_BASE", "https://medicines.health.europa.eu/veterinary"
)
# Optional: point at a machine-readable UPD/EMA endpoint that returns JSON.
# NOTE: this is *not* required. The public UPD website is server-side rendered
# (Drupal + search_api) and can be scraped directly without any API key or
# login - see EMA_SEARCH_URL below, which is the default live path.
EMA_API_URL = os.environ.get("EMA_API_URL", "")

# Public UPD search view. Server-rendered, paginated 10 rows/page, no auth.
# The bare EMA_VET_BASE only returns a language-selection shell, which is why
# earlier versions of this scraper extracted nothing.
EMA_SEARCH_URL = os.environ.get(
    "EMA_SEARCH_URL",
    "https://medicines.health.europa.eu/veterinary/en/search-medicines",
)
EMA_PAGE_SIZE = 10  # fixed server-side; items_per_page is ignored by the view
# Sort order for the crawl. Newest-updated first means a partial daily crawl
# still catches new/changed authorisations. Valid view sort keys:
#   prod_search_changed                  (last updated date)
#   prod_search_upd_marketing_auth_date  (authorisation date)
#   prod_search_upd_product_name         (alphabetical)
# Set EMA_SORT_BY="" to use the view's default relevance ordering.
EMA_SORT_BY = os.environ.get("EMA_SORT_BY", "prod_search_changed")
EMA_SORT_ORDER = os.environ.get("EMA_SORT_ORDER", "DESC")
# Safety cap on result pages per run (10 products/page). The full catalogue is
# ~5,000 products (~508 pages) and the site throttles hard, so the default is a
# newest-first incremental slice. Raise it for a one-off full backfill.
EMA_MAX_PAGES = int(os.environ.get("EMA_MAX_PAGES", "40"))
# Parallel page fetches. Keep this low: the site returns HTTP 429 and resets
# connections when hit too hard (5 workers already triggered throttling).
EMA_WORKERS = max(1, int(os.environ.get("EMA_FETCH_WORKERS", "3")))
# Per-page retry policy for 429 / transient transport errors.
EMA_MAX_RETRIES = max(1, int(os.environ.get("EMA_MAX_RETRIES", "6")))
EMA_RETRY_BASE_DELAY = float(os.environ.get("EMA_RETRY_BASE_DELAY", "3.0"))
# Polite delay (seconds) inserted between successive page requests so the site
# doesn't throttle the crawl with HTTP 429 / connection resets.
EMA_PAGE_DELAY = float(os.environ.get("EMA_PAGE_DELAY", "1.5"))

REQUEST_TIMEOUT = int(os.environ.get("REGULATORY_TIMEOUT", "30"))
USER_AGENT = ("Mozilla/5.0 (compatible; VetBiologicsTracker/1.0; "
             "+https://example.org/bot)")

# Local cache of the USDA catalog PDF so only the first pull downloads it;
# later pulls parse from disk (seconds instead of ~minutes on slow links).
USDA_CACHE_FILE = os.path.join(DATA_DIR, "usda_catalog.pdf")
USDA_CACHE_MAX_AGE_DAYS = int(os.environ.get("USDA_CATALOG_CACHE_DAYS", "1"))


def _load_or_fetch_pdf() -> Tuple[bytes, str]:
    """Return (pdf_bytes, source) using a local cache when fresh."""
    if os.path.exists(USDA_CACHE_FILE):
        age_days = (datetime.now().timestamp() - os.path.getmtime(USDA_CACHE_FILE)) / 86400.0
        if age_days < USDA_CACHE_MAX_AGE_DAYS:
            with open(USDA_CACHE_FILE, "rb") as f:
                return f.read(), "cache"
    r = requests.get(USDA_CVB_CATALOG_URL, timeout=REQUEST_TIMEOUT,
                     headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    try:
        with open(USDA_CACHE_FILE, "wb") as f:
            f.write(r.content)
    except Exception as e:  # pragma: no cover - caching must never break ingest
        log().warning("USDA/CVB: could not cache PDF: %s", e)
    return r.content, "download"

# Canonical enums (mirrors db.py) - used for coercion/validation.
VALID_REGIONS = {"US", "EU"}
VALID_SPECIES = {"Cat", "Dog", "Both"}
VALID_TYPES = {"Vaccine", "Diagnostic", "Therapeutic"}
VALID_STATUSES = {"Active", "Suspended", "Withdrawn"}

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
_logger: Optional[logging.Logger] = None


def setup_logging() -> logging.Logger:
    """Configure the module logger (file + console). Idempotent."""
    global _logger
    if _logger is not None:
        return _logger
    os.makedirs(DATA_DIR, exist_ok=True)
    log = logging.getLogger("regulatory")
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    # console
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    # rotating file
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception as e:  # pragma: no cover - logging must never break ingest
        log.warning("Could not attach file handler: %s", e)
    _logger = log
    return log


def log() -> logging.Logger:
    """Return the module logger (auto-initialising if needed)."""
    return _logger or setup_logging()


# --------------------------------------------------------------------------- #
# Field mapping helpers
# --------------------------------------------------------------------------- #
# USDA catalog product-section title -> canonical product_type.
USDA_SECTION_TYPE = {
    "Vaccines": "Vaccine",
    "Bacterins and bacterial extracts": "Vaccine",
    "Vaccines with bacterins/bacterial extracts/toxoids": "Vaccine",
    "Bacterin-toxoids": "Vaccine",
    "Diagnostic products": "Diagnostic",
    "Antibody products": "Therapeutic",
    "Antitoxins": "Therapeutic",
    "Toxoids": "Therapeutic",
    "Miscellaneous": "Therapeutic",
}

# Species keyword detection (the workbench focuses on cat & dog products).
_CANINE = ("canine", "dog", "puppy", "kennel")
_FELINE = ("feline", "cat", "kitten")

# Product-code (PCN) line pattern, e.g. "48B5.10", "4BC5.20", "49F6.2B",
# "49L5.R0", "4905.20", "4993.2B", "4855.00", "49K9.R0".
_PCN_RE = re.compile(r"^(\d{1,2}[A-Z0-9]{1,2}\d\.\w{1,3})\b")
# Producer establishment licence number (VLN), e.g. "196", "165A", "652A".
_VLN_RE = re.compile(r"\b(\d{3}[A-Z]?)\b")


def _infer_species(name: str) -> Optional[str]:
    low = (name or "").lower()
    has_dog = any(k in low for k in _CANINE)
    has_cat = any(k in low for k in _FELINE)
    if has_dog and has_cat:
        return "Both"
    if has_dog:
        return "Dog"
    if has_cat:
        return "Cat"
    return None


def _coerce_enum(value, valid, default):
    if value in valid:
        return value
    # tolerant: title-case / strip attempts
    if isinstance(value, str):
        v = value.strip()
        if v in valid:
            return v
        vt = v.title()
        if vt in valid:
            return vt
    return default


def normalize_record(raw: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Map a raw record onto the canonical schema with validation.

    Returns ``(record, issues)``. ``record`` is ``None`` when a required field
    is missing/empty (caller logs + skips). ``issues`` lists non-fatal warnings
    (e.g. coerced enums) for logging.
    """
    issues: List[str] = []
    rec: Dict[str, Any] = {}

    rec["region"] = _coerce_enum(raw.get("region"), VALID_REGIONS, None)
    rec["species"] = _coerce_enum(raw.get("species"), VALID_SPECIES, None)
    rec["product_type"] = _coerce_enum(raw.get("product_type"),
                                       VALID_TYPES, "Therapeutic")
    if raw.get("product_type") and rec["product_type"] != raw.get("product_type"):
        issues.append(f"product_type coerced: {raw.get('product_type')!r}")

    name = (raw.get("product_name") or "").strip()
    anum = (raw.get("approval_number") or "").strip()
    if not name:
        return None, ["missing product_name"]
    if not anum:
        return None, ["missing approval_number"]
    rec["product_name"] = name
    rec["approval_number"] = anum

    rec["manufacturer"] = (raw.get("manufacturer") or "").strip() or None
    rec["indication"] = (raw.get("indication") or "").strip() or None
    rec["dosage_form"] = (raw.get("dosage_form") or "").strip() or None
    rec["strength"] = (raw.get("strength") or "").strip() or None
    rec["approval_date"] = (raw.get("approval_date") or "").strip() or None
    rec["status"] = _coerce_enum(raw.get("status"), VALID_STATUSES, "Active")
    rec["source"] = (raw.get("source") or "").strip() or None

    # A record must be classifiable by region + species to be useful here.
    if rec["region"] is None:
        return None, ["missing/invalid region"]
    if rec["species"] is None:
        return None, ["missing/invalid species"]
    return rec, issues


# --------------------------------------------------------------------------- #
# USDA / CVB  - PDF codebook parser
# --------------------------------------------------------------------------- #
def _build_vln_map(pdf) -> Dict[str, str]:
    """Build producer-licence (VLN) -> company name map from the catalog."""
    vmap: Dict[str, str] = {}
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if re.match(r"Page \d+ of \d+", s):
                continue
            if s.startswith(("Mail:", "Type:", "Subsidiaries:", "Divisions:",
                              "License Number", "Page")):
                continue
            m = re.match(r"^(.*?)\s+(\d{3}[A-Z]?)$", s)
            if m:
                name = m.group(1).strip()
                vln = m.group(2)
                if name and len(vln) >= 3:
                    vmap.setdefault(vln, name)
    return vmap


def _match_usda_section(line: str) -> Optional[str]:
    s = line.strip()
    for title in USDA_SECTION_TYPE:
        if s == title or s.startswith(title + " "):
            return title
    return None


def _parse_usda_pdf(raw_bytes: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse the USDA codebook PDF bytes into canonical records."""
    try:
        import pdfplumber
    except Exception as e:  # pragma: no cover
        return [], {"error": f"pdfplumber unavailable: {e}"}

    stats = {"pages": 0, "raw_products": 0, "ingested": 0,
             "skipped_species": 0, "skipped_invalid": 0, "unmapped_vln": 0}
    records: List[Dict[str, Any]] = []
    seen_codes: set = set()

    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        stats["pages"] = len(pdf.pages)
        vln_map = _build_vln_map(pdf)

        current_section = None
        current_type = None
        in_product_list = False
        name_lines: List[str] = []
        pending_code = ("", "")

        def finalize(nlines, code, rest):
            """Build + normalise one product; return record or None."""
            if not nlines or not code:
                return None
            pname = " ".join(nlines).strip()
            pname = re.sub(r"\s+", " ", pname)
            if not pname:
                return None
            vlns = _VLN_RE.findall(rest)
            form = _VLN_RE.sub("", rest).strip(" -,")
            makers = []
            unmapped = 0
            for v in vlns:
                nm = vln_map.get(v)
                if nm:
                    makers.append(nm)
                else:
                    unmapped += 1
                    makers.append(f"VLN {v}")  # keep the licence id as fallback
            manufacturer = " / ".join(dict.fromkeys(makers)) if makers else None
            species = _infer_species(pname)
            if species is None:
                stats["skipped_species"] += 1
                return None  # workbench tracks cat/dog only
            raw = {
                "region": "US",
                "species": species,
                "product_type": current_type or "Vaccine",
                "product_name": pname,
                "approval_number": code,
                "manufacturer": manufacturer,
                "indication": pname,  # true name already lists antigens/diseases
                "dosage_form": form or None,
                "strength": None,
                "approval_date": None,
                "status": "Active",
                "source": "USDA-CVB",
            }
            rec, issues = normalize_record(raw)
            if rec is None:
                stats["skipped_invalid"] += 1
                return None
            stats["unmapped_vln"] += unmapped
            return rec

        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if "FOR OFFICIAL USE ONLY" in line:
                    continue
                if re.match(r"Page \d+ of \d+", line):
                    continue

                # Section header?
                sec = _match_usda_section(line)
                if sec:
                    # finalize any pending block
                    if name_lines and pending_code[0]:
                        r = finalize(name_lines, pending_code[0], pending_code[1])
                        if r is not None and r["approval_number"] not in seen_codes:
                            seen_codes.add(r["approval_number"])
                            records.append(r)
                            stats["ingested"] += 1
                    current_section = sec
                    current_type = USDA_SECTION_TYPE[sec]
                    in_product_list = True
                    name_lines = []
                    pending_code = ("", "")
                    continue

                if not in_product_list:
                    continue
                # stop before "For further manufacture" sections
                if line.lower().startswith("for further manufacture"):
                    in_product_list = False
                    name_lines = []
                    pending_code = ("", "")
                    continue
                # column header line
                if line.startswith("CODE PRODUCT AND FORM"):
                    name_lines = []
                    continue
                # conditional-licence footnote
                if line.startswith("*Conditional"):
                    continue

                m = _PCN_RE.match(line)
                if m:
                    code = m.group(1)
                    rest = line[m.end():].strip()
                    r = finalize(name_lines, code, rest)
                    if r is not None and r["approval_number"] not in seen_codes:
                        seen_codes.add(r["approval_number"])
                        records.append(r)
                        stats["ingested"] += 1
                    elif r is not None:
                        stats["raw_products"] += 1  # duplicate PCN, already kept
                    name_lines = []
                    pending_code = ("", "")
                    continue

                # otherwise accumulate as product-name continuation
                name_lines.append(line)

    return records, stats


def fetch_usda_cvb() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Download + parse the USDA/CVB licensed-biologics catalog.

    Returns ``(records, meta)``. On any failure returns ``([], meta)`` with an
    ``error`` key so the caller can fall back to the sample snapshot.
    """
    meta = {
        "source": "USDA-CVB",
        "url": USDA_CVB_CATALOG_URL,
        "catalog_date": USDA_CVB_CATALOG_DATE,
        "fetched_at": date.today().isoformat(),
        "error": None,
        "ingested": 0,
    }
    try:
        log().info("USDA/CVB: loading catalog (%s)", USDA_CVB_CATALOG_URL)
        content, src = _load_or_fetch_pdf()
        meta["cache"] = (src == "cache")
        if not content or (content[:4] != b"%PDF" and
                           "pdf" not in (meta.get("content_type") or "")):
            meta["error"] = "downloaded content is not a PDF"
            log().error("USDA/CVB: %s", meta["error"])
            return [], meta
        records, stats = _parse_usda_pdf(content)
        meta.update(stats)
        meta["ingested"] = stats.get("ingested", 0)
        log().info("USDA/CVB: parsed %d cat/dog products (src=%s, skipped %d "
                   "non-cat/dog, %d invalid)", meta["ingested"], src,
                   stats.get("skipped_species", 0), stats.get("skipped_invalid", 0))
        if meta["ingested"] == 0:
            meta["error"] = "parser yielded 0 records (unexpected layout?)"
            log().warning("USDA/CVB: %s", meta["error"])
            return [], meta
        return records, meta
    except Exception as e:  # noqa: BLE001 - never break the pipeline
        meta["error"] = f"{type(e).__name__}: {e}"
        log().exception("USDA/CVB: fetch/parse failed")
        return [], meta


# --------------------------------------------------------------------------- #
# EMA / CVMP - public website scraper (best-effort + graceful fallback)
# --------------------------------------------------------------------------- #
_EMA_ROW_SPLIT = '<div class="views-row">'
_EMA_TITLE_RE = re.compile(
    r'product-title-linked.*?<a\s+href="/veterinary/[a-z]{2}/(\d+)"[^>]*>(.*?)</a>',
    re.S)
_EMA_STATUS_CLASS_RE = re.compile(r'product-status--([a-z_-]+)')
_EMA_ITEM_RE = re.compile(r'field__item">\s*([^<>]+?)\s*</div>')
_EMA_TOTAL_RE = re.compile(r'\bof\s+([\d,]{2,})\b')

_EMA_STATUS_MAP = {
    "authorised": "Active",
    "suspended": "Suspended",
    "withdrawn": "Withdrawn",
    "not-authorised": "Withdrawn",
    "not_authorised": "Withdrawn",
    "expired": "Withdrawn",
}


def _strip_tags(s: str) -> str:
    return _html_mod.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def _ema_field_block(row: str, suffix: str) -> str:
    """Return the HTML chunk of one teaser field (by its Drupal class)."""
    for cls in (f"products__extra-field-upd-products-{suffix}",
                f"products__field-upd-{suffix}"):
        i = row.find(cls)
        if i == -1:
            continue
        rest = row[i:]
        nxt = rest.find('<div class="field products__', 8)
        return rest[:nxt] if nxt > 0 else rest
    return ""


def _ema_items(block: str) -> List[str]:
    return [_html_mod.unescape(x).strip() for x in _EMA_ITEM_RE.findall(block)]


def _ema_total_count(html: str) -> int:
    """Best-effort total result count from the pager summary."""
    nums = [int(n.replace(",", "")) for n in _EMA_TOTAL_RE.findall(html or "")]
    return max(nums) if nums else 0


def _parse_ema_html(html: str) -> List[Dict[str, Any]]:
    """Extract UPD product rows from a rendered search-medicines page.

    The public UPD site is server-side rendered (Drupal views), so each result
    is a ``views-row`` article carrying product name, UPD id, target species,
    active substance, pharmaceutical form and authorisation status. Returns raw
    dicts (pre-normalisation); cat/dog filtering happens in the caller.
    """
    out: List[Dict[str, Any]] = []
    for row in (html or "").split(_EMA_ROW_SPLIT)[1:]:
        m = _EMA_TITLE_RE.search(row)
        if not m:
            continue
        upd_id = m.group(1)
        name = _strip_tags(m.group(2))
        if not name:
            continue

        species_text = " ".join(_ema_items(_ema_field_block(row, "species")))
        species = _infer_species(species_text) or _infer_species(name)

        subs = list(dict.fromkeys(_ema_items(
            _ema_field_block(row, "active-substance"))))
        form = _ema_items(_ema_field_block(row, "pharmaceutical-form"))

        st = _EMA_STATUS_CLASS_RE.search(row)
        status = _EMA_STATUS_MAP.get((st.group(1) if st else "").lower(),
                                    "Active")

        blob = f"{name} {' '.join(subs)}".lower()
        ptype = "Vaccine" if ("vaccin" in blob or "immunolog" in blob) \
            else "Therapeutic"

        out.append({
            "region": "EU",
            "species": species,
            "product_type": ptype,
            "product_name": name,
            "approval_number": f"UPD-{upd_id}",
            "manufacturer": None,
            "indication": "; ".join(subs) or None,
            "dosage_form": (form[0] if form else None),
            "strength": None,
            "approval_date": None,
            "status": status,
            "source": "EMA-CVMP",
        })
    return out


def _ema_fetch_page(page: int) -> Optional[str]:
    """Fetch one page of the UPD search view, retrying on throttling.

    The site rate-limits aggressively (HTTP 429) and occasionally drops
    connections, so each page gets a few attempts with exponential backoff.
    Returns ``None`` only after all attempts fail.
    """
    headers = {"User-Agent": USER_AGENT,
               "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    params: Dict[str, Any] = {"page": page}
    if EMA_SORT_BY:
        params["sort_by"] = EMA_SORT_BY
        params["sort_order"] = EMA_SORT_ORDER
    delay = EMA_RETRY_BASE_DELAY
    last = ""
    for attempt in range(1, EMA_MAX_RETRIES + 1):
        try:
            r = requests.get(EMA_SEARCH_URL, params=params,
                             timeout=REQUEST_TIMEOUT, headers=headers)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
            # 429/5xx are transient -> back off and retry.
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            # Honour an explicit Retry-After hint from the server.
            ra = r.headers.get("Retry-After")
            if ra and str(ra).isdigit():
                time.sleep(min(int(ra), 30))
                delay = EMA_RETRY_BASE_DELAY
                continue
        except Exception as e:  # noqa: BLE001 - retry transport errors
            last = f"{type(e).__name__}"
        if attempt < EMA_MAX_RETRIES:
            time.sleep(delay)
            delay = min(delay * 2, 30)
    log().warning("EMA/CVMP: page %d gave up after %d attempt(s) (%s)",
                  page, EMA_MAX_RETRIES, last)
    return None


def fetch_ema_cvmp() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Fetch EMA/CVMP veterinary medicines.

    Attempts ``EMA_API_URL`` if configured, otherwise the public website.
    Returns ``(records, meta)``; on failure/empty returns ``([], meta)``.
    """
    meta = {
        "source": "EMA-CVMP",
        "url": EMA_API_URL or EMA_SEARCH_URL,
        "fetched_at": date.today().isoformat(),
        "error": None,
        "ingested": 0,
    }
    try:
        log().info("EMA/CVMP: crawling UPD search view %s", EMA_SEARCH_URL)
        first = _ema_fetch_page(0)
        if first is None:
            meta["error"] = "could not load first page of UPD search view"
            log().error("EMA/CVMP: %s", meta["error"])
            return [], meta

        total = _ema_total_count(first)
        pages = EMA_MAX_PAGES
        if total:
            pages = min(EMA_MAX_PAGES,
                        (total + EMA_PAGE_SIZE - 1) // EMA_PAGE_SIZE)
        meta["total_reported"] = total
        meta["pages_crawled"] = pages
        log().info("EMA/CVMP: %d products reported, crawling %d page(s) "
                   "serially (delay=%.1fs)", total, pages, EMA_PAGE_DELAY)

        raw_recs: List[Dict[str, Any]] = _parse_ema_html(first)
        # Serial, polite crawl: one page at a time with a short delay so the
        # site's aggressive rate limiter (HTTP 429) doesn't abort the run.
        for p in range(1, pages):
            if EMA_PAGE_DELAY > 0:
                time.sleep(EMA_PAGE_DELAY)
            text = _ema_fetch_page(p)
            if text:
                raw_recs.extend(_parse_ema_html(text))

        if not raw_recs:
            meta["error"] = ("UPD search view returned no parsable product "
                             "rows (site layout may have changed)")
            log().warning("EMA/CVMP: %s", meta["error"])
            return [], meta

        # De-duplicate by UPD identifier (the same trade name is authorised
        # separately in several member states, each with its own UPD id).
        seen: set = set()
        out: List[Dict[str, Any]] = []
        skipped_species = skipped_invalid = 0
        for raw in raw_recs:
            key = raw.get("approval_number")
            if key in seen:
                continue
            seen.add(key)
            if not raw.get("species"):
                skipped_species += 1  # not a cat/dog product
                continue
            rec, _issues = normalize_record(raw)
            if rec is None:
                skipped_invalid += 1
                continue
            out.append(rec)

        meta["ingested"] = len(out)
        meta["skipped_species"] = skipped_species
        meta["skipped_invalid"] = skipped_invalid
        log().info("EMA/CVMP: parsed %d cat/dog products (from %d unique rows, "
                   "skipped %d non-cat/dog, %d invalid)", len(out), len(seen),
                   skipped_species, skipped_invalid)
        if not out:
            meta["error"] = "no cat/dog products found in UPD results"
            log().warning("EMA/CVMP: %s", meta["error"])
        return out, meta
    except Exception as e:  # noqa: BLE001
        meta["error"] = f"{type(e).__name__}: {e}"
        log().exception("EMA/CVMP: fetch/parse failed")
        return [], meta


if __name__ == "__main__":
    setup_logging()
    us, usm = fetch_usda_cvb()
    print("USDA records:", len(us), "| meta:", usm)
    for r in us[:3]:
        print("  -", r["approval_number"], r["product_name"], "|",
              r["species"], r["product_type"], "|", r["manufacturer"])
    eu, eum = fetch_ema_cvmp()
    print("EMA records:", len(eu), "| meta:", eum)
