"""Database layer for the Veterinary Biologics Tracking Workbench.

Stores approved veterinary biologics (vaccines / diagnostics / therapeutics)
for cats & dogs from US (USDA/CVB) and EU (EMA/CVMP) regulators.
Provides query/filter, diffing (NEW / UPDATED / STATUS_CHANGE / WITHDRAWN)
and notification helpers.
"""
import sqlite3
import hashlib
import json
import os
from datetime import date, datetime
from urllib.parse import quote

DB_PATH = os.environ.get(
    "VET_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "vet_biologics.db"))

# ----- Schema constants -----
REGIONS = ["US", "EU"]
SPECIES = ["Cat", "Dog", "Both"]
PRODUCT_TYPES = ["Vaccine", "Diagnostic", "Therapeutic"]
STATUSES = ["Active", "Suspended", "Withdrawn"]

# Fields that are compared for change detection (besides status)
TRACKED_FIELDS = [
    "product_name", "manufacturer", "indication",
    "dosage_form", "strength", "approval_date",
]


def _hash(rec):
    """Stable hash of the meaningful fields of a product record."""
    parts = "|".join(str(rec.get(f, "")) for f in
                     ["region", "species", "product_type", "product_name",
                      "manufacturer", "indication", "dosage_form", "strength",
                      "approval_date", "status", "source"])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL,
            species TEXT NOT NULL,
            product_type TEXT NOT NULL,
            product_name TEXT NOT NULL,
            approval_number TEXT NOT NULL,
            manufacturer TEXT,
            indication TEXT,
            dosage_form TEXT,
            strength TEXT,
            approval_date TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            source TEXT,
            record_hash TEXT,
            first_seen TEXT,
            last_updated TEXT,
            UNIQUE(region, approval_number)
        );
        CREATE TABLE IF NOT EXISTS change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            change_type TEXT NOT NULL,
            change_date TEXT NOT NULL,
            field TEXT,
            prev_value TEXT,
            new_value TEXT,
            product_name TEXT,
            region TEXT,
            approval_number TEXT,
            notified INTEGER DEFAULT 0,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE INDEX IF NOT EXISTS idx_products_filters
            ON products(region, species, product_type, status);
        CREATE INDEX IF NOT EXISTS idx_changelog_date
            ON change_log(change_date);
    """)
    # Backward-compatible migration: add source_url column if missing.
    try:
        conn.execute("ALTER TABLE products ADD COLUMN source_url TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()


# Official public regulatory resources. Each product carries a source_url that
# links directly to the regulator's public database / downloadable material so
# users can verify and fetch the underlying公开资料.
USDA_PRODUCT_SUMMARIES = (
    "https://www.aphis.usda.gov/aphis/ourfocus/animalhealth/"
    "veterinary-biologics/product-summaries/")
EMA_VET_SEARCH = "https://medicines.health.europa.eu/veterinary/en/search-medicines"


def default_source_url(source, product_name):
    """Best-effort public reference URL for a product based on its source."""
    s = (source or "").upper()
    name = (product_name or "").strip()
    if "EMA" in s:
        return f"{EMA_VET_SEARCH}?search_api_fulltext={quote(name)}"
    if "USDA" in s:
        return USDA_PRODUCT_SUMMARIES
    return ""


# ---------------------------------------------------------------------------
# Ingestion + diff engine
# ---------------------------------------------------------------------------
def ingest_dataset(dataset, ingest_date=None, source_label="manual",
                   complete_sources=None):
    """Merge a dataset (list of product dicts) into the DB and log changes.

    A product dict uses keys: region, species, product_type, product_name,
    approval_number, manufacturer, indication, dosage_form, strength,
    approval_date, status, source.

    ``complete_sources`` gates withdrawal inference. "Absent from the feed"
    only implies withdrawal when the feed is an *authoritative full listing*
    for that source. Pass the set of sources whose pull is known-complete to
    restrict the inference to them; pass None (default) to treat every
    incoming source as complete, which is correct for the sample/seed
    datasets where the dataset IS the whole universe.

    This matters because an incremental pull (e.g. EMA/CVMP, where only the
    newest N pages of ~508 are crawled per run) returns a different subset
    each time. Without the gate, every run withdraws whatever did not appear
    in that run's slice and the next run flips it back to Active — pure churn
    that fabricates regulatory status changes.

    Returns a summary dict: {new, updated, status_change, withdrawn, total}.
    """
    if ingest_date is None:
        ingest_date = date.today().isoformat()

    conn = get_conn()
    summary = {"new": 0, "updated": 0, "status_change": 0, "withdrawn": 0,
               "total": 0, "changes": []}

    # Build lookup of existing products by (region, approval_number)
    existing = {}
    for row in conn.execute(
            "SELECT * FROM products"):
        existing[(row["region"], row["approval_number"])] = dict(row)

    seen_keys = set()

    for rec in dataset:
        key = (rec["region"], rec["approval_number"])
        seen_keys.add(key)
        rec["status"] = rec.get("status", "Active")
        # Ensure every product has a public reference link; let an explicit
        # source_url override the source-derived default.
        if not rec.get("source_url"):
            rec["source_url"] = default_source_url(rec.get("source"),
                                                  rec.get("product_name"))
        new_hash = _hash(rec)

        if key not in existing:
            # NEW product
            cur = conn.execute(
                """INSERT INTO products
                   (region, species, product_type, product_name, approval_number,
                    manufacturer, indication, dosage_form, strength, approval_date,
                    status, source, source_url, record_hash, first_seen, last_updated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["region"], rec["species"], rec["product_type"],
                 rec["product_name"], rec["approval_number"],
                 rec.get("manufacturer"), rec.get("indication"),
                 rec.get("dosage_form"), rec.get("strength"),
                 rec.get("approval_date"), rec["status"], rec.get("source"),
                 rec.get("source_url"),
                 new_hash, ingest_date, ingest_date))
            pid = cur.lastrowid
            _log_change(conn, pid, "NEW", ingest_date, None, None, None,
                        rec["product_name"], rec["region"], rec["approval_number"])
            summary["new"] += 1
            summary["changes"].append(_change_obj(pid, "NEW", ingest_date, rec["product_name"], rec["region"], rec["approval_number"]))
        else:
            old = existing[key]
            pid = old["id"]
            changed = False
            # Status change?
            if old["status"] != rec["status"]:
                _log_change(conn, pid, "STATUS_CHANGE", ingest_date, "status",
                            old["status"], rec["status"], rec["product_name"],
                            rec["region"], rec["approval_number"])
                summary["status_change"] += 1
                summary["changes"].append(_change_obj(pid, "STATUS_CHANGE", ingest_date, rec["product_name"], rec["region"], rec["approval_number"], "status", old["status"], rec["status"]))
                changed = True
            # Other field changes?
            for f in TRACKED_FIELDS:
                ov = (old.get(f) or "").strip()
                nv = (rec.get(f) or "").strip()
                if ov != nv and nv != "":
                    _log_change(conn, pid, "UPDATED", ingest_date, f, ov, nv,
                                rec["product_name"], rec["region"], rec["approval_number"])
                    summary["updated"] += 1
                    summary["changes"].append(_change_obj(pid, "UPDATED", ingest_date, rec["product_name"], rec["region"], rec["approval_number"], f, ov, nv))
                    changed = True
            if changed:
                conn.execute(
                    """UPDATE products SET species=?, product_type=?, product_name=?,
                       manufacturer=?, indication=?, dosage_form=?, strength=?,
                       approval_date=?, status=?, source=?, source_url=?, record_hash=?,
                       last_updated=? WHERE id=?""",
                    (rec["species"], rec["product_type"], rec["product_name"],
                     rec.get("manufacturer"), rec.get("indication"),
                     rec.get("dosage_form"), rec.get("strength"),
                     rec.get("approval_date"), rec["status"], rec.get("source"),
                     rec.get("source_url"),
                     new_hash, ingest_date, pid))
            else:
                # refresh hash even if no change
                conn.execute("UPDATE products SET record_hash=? WHERE id=?",
                             (new_hash, pid))

    # Sources represented in this incoming feed. Withdrawn detection is gated
    # on this set so that switching data sources (e.g. sample -> live regulator
    # feeds) never false-flags the *other* source's products as withdrawn.
    incoming_sources = {rec.get("source") for rec in dataset if rec.get("source")}

    # Second gate: only sources that delivered a COMPLETE listing may imply
    # withdrawal. Partial/incremental pulls are absence-agnostic.
    if complete_sources is not None:
        authoritative = incoming_sources & set(complete_sources)
    else:
        authoritative = incoming_sources

    # Withdrawn detection: previously Active/Suspended products missing from feed
    for key, old in existing.items():
        if (key not in seen_keys and old["status"] not in ("Withdrawn",)
                and old.get("source") in authoritative):
            pid = old["id"]
            conn.execute("UPDATE products SET status='Withdrawn', last_updated=? WHERE id=?",
                         (ingest_date, pid))
            _log_change(conn, pid, "WITHDRAWN", ingest_date, "status",
                        old["status"], "Withdrawn", old["product_name"],
                        old["region"], old["approval_number"])
            summary["withdrawn"] += 1
            summary["changes"].append(_change_obj(pid, "WITHDRAWN", ingest_date, old["product_name"], old["region"], old["approval_number"], "status", old["status"], "Withdrawn"))

    summary["total"] = len(existing) + summary["new"]
    conn.commit()
    conn.close()
    return summary


def _log_change(conn, pid, ctype, cdate, field, prev_v, new_v, pname, region, anum):
    conn.execute(
        """INSERT INTO change_log
           (product_id, change_type, change_date, field, prev_value, new_value,
            product_name, region, approval_number, notified)
           VALUES (?,?,?,?,?,?,?,?,?,0)""",
        (pid, ctype, cdate, field, prev_v, new_v, pname, region, anum))


def _change_obj(pid, ctype, cdate, pname, region, anum, field=None, prev_v=None, new_v=None):
    return {"product_id": pid, "change_type": ctype, "change_date": cdate,
            "product_name": pname, "region": region, "approval_number": anum,
            "field": field, "prev_value": prev_v, "new_value": new_v}


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_products(filters=None):
    filters = filters or {}
    where = []
    params = []
    if filters.get("region"):
        where.append("region=?")
        params.append(filters["region"])
    if filters.get("species"):
        where.append("species=?")
        params.append(filters["species"])
    if filters.get("product_type"):
        where.append("product_type=?")
        params.append(filters["product_type"])
    if filters.get("status"):
        where.append("status=?")
        params.append(filters["status"])
    q = (filters.get("q") or "").strip()
    if q:
        where.append("(product_name LIKE ? OR manufacturer LIKE ? OR indication LIKE ? OR approval_number LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])
    sql = "SELECT * FROM products"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY approval_date DESC, product_name"
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    return rows


def get_stats():
    conn = get_conn()
    stats = {}

    # annual approval trend (by region)
    cur = conn.execute(
        """SELECT region, substr(approval_date,1,4) AS yr, COUNT(*) AS c
           FROM products WHERE approval_date >= '2000' GROUP BY region, yr""")
    trend = {}
    for r in cur:
        trend.setdefault(r["region"], {})[r["yr"]] = r["c"]
    stats["annual_trend"] = trend

    # Undated products per region. Some regulator feeds (e.g. USDA/CVB's
    # current product codebook) do not publish a per-product original approval
    # date, so those records cannot appear in the annual trend. We surface the
    # count so the UI can explain why a region is absent from the trend instead
    # of looking broken.
    cur = conn.execute(
        """SELECT region, COUNT(*) AS c FROM products
           WHERE approval_date IS NULL OR approval_date = ''
           GROUP BY region""")
    stats["undated_by_region"] = {r["region"]: r["c"] for r in cur}

    # company distribution
    cur = conn.execute(
        """SELECT manufacturer, COUNT(*) AS c FROM products
           WHERE manufacturer IS NOT NULL AND manufacturer != ''
           GROUP BY manufacturer ORDER BY c DESC""")
    stats["companies"] = [{"name": r["manufacturer"], "count": r["c"]} for r in cur]

    # by region / species / type / status
    for dim, col in [("by_region", "region"), ("by_species", "species"),
                     ("by_type", "product_type"), ("by_status", "status")]:
        cur = conn.execute(f"SELECT {col} AS k, COUNT(*) AS c FROM products GROUP BY {col}")
        stats[dim] = [{"key": r["k"], "count": r["c"]} for r in cur]

    # cross: region x species x type matrix
    cur = conn.execute(
        """SELECT region, species, product_type, COUNT(*) AS c FROM products
           GROUP BY region, species, product_type""")
    stats["matrix"] = [dict(r) for r in cur]

    stats["total"] = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    conn.close()
    return stats


def get_changes(limit=200):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM change_log ORDER BY change_date DESC, id DESC LIMIT ?",
        (limit,))]
    conn.close()
    return rows


def get_notifications(only_unread=False, limit=50):
    conn = get_conn()
    sql = "SELECT * FROM change_log"
    if only_unread:
        sql += " WHERE notified=0"
    sql += " ORDER BY change_date DESC, id DESC LIMIT ?"
    rows = [dict(r) for r in conn.execute(sql, (limit,))]
    conn.close()
    return rows


def mark_notifications_read():
    conn = get_conn()
    conn.execute("UPDATE change_log SET notified=1 WHERE notified=0")
    conn.commit()
    conn.close()


def backfill_source_urls():
    """One-off migration: fill source_url for products that lack it."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, source, product_name, source_url FROM products").fetchall()
    n = 0
    for r in rows:
        if r["source_url"]:
            continue
        url = default_source_url(r["source"], r["product_name"])
        if url:
            conn.execute("UPDATE products SET source_url=? WHERE id=?",
                         (url, r["id"]))
            n += 1
    conn.commit()
    conn.close()
    return n


def clear_source_products(sources):
    """Delete products (and their change_log rows) belonging to the given
    source(s). Used by the optional 'replace with live regulator feed' mode so
    a fresh live pull starts from a clean slate for that source family without
    touching other data.
    """
    if not sources:
        return 0
    placeholders = ",".join("?" for _ in sources)
    conn = get_conn()
    # remove change_log rows referencing those products first
    conn.execute(
        f"""DELETE FROM change_log WHERE product_id IN (
               SELECT id FROM products WHERE source IN ({placeholders}))""",
        tuple(sources))
    cur = conn.execute(f"DELETE FROM products WHERE source IN ({placeholders})",
                       tuple(sources))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


if __name__ == "__main__":
    init_db()
    print("DB initialised at", DB_PATH)
