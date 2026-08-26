"""Ingestion layer: pull data from regulators and merge into the DB.

Two modes (selected by ``live`` / env ``USE_LIVE_SOURCES``):

* Sample (default) - uses the illustrative seed snapshots so every feature is
  demonstrable offline. This is the original behaviour and is unchanged.
* Live  - pulls the real regulator feeds via ``regulatory.py``. Each source is
  fetched independently; if a source fails or yields no records it falls back
  to that region's sample slice, so the merge never breaks. A live pull is also
  source-aware at the diff layer (see db.py), so it can never false-withdraw
  the sample demo data.

The normalised output uses exactly the keys consumed by ``db.ingest_dataset``,
so downstream (diff engine, notifications, exports, UI) is untouched.
"""
import os
from datetime import date

import db
import regulatory
from seed_data import get_baseline_dataset, get_update_dataset

# Live ingestion is OPT-IN. Set USE_LIVE_SOURCES=1 to make the scheduler and
# the default "update" action use the real regulator feeds.
USE_LIVE_SOURCES = os.environ.get("USE_LIVE_SOURCES", "0") == "1"

# When switching to live for the first time, clear the matching sample slice
# first for a clean dataset. Off by default (merge is safest / non-destructive).
REPLACE_ON_LIVE = os.environ.get("REPLACE_ON_LIVE", "0") == "1"


def seed_baseline():
    """Populate the DB with the initial baseline snapshot."""
    return db.ingest_dataset(get_baseline_dataset())


def _sample_slice(region):
    """Return the baseline sample rows for one region (US / EU)."""
    return [r for r in get_baseline_dataset() if r["region"] == region]


#: Products listed per result page by the EMA UPD search view.
EMA_PAGE_SIZE = 10


def _complete_sources(meta):
    """Return the set of sources whose pull covered the FULL source catalogue.

    Only such sources may drive withdrawal inference, because only for them
    does "missing from the feed" actually mean "no longer listed".

    * USDA-CVB parses the complete product code book PDF in one shot, so a
      successful fetch is always authoritative.
    * EMA-CVMP crawls at most ``EMA_MAX_PAGES`` of the ~508-page UPD view
      (newest-first). It counts as complete only when the pages it crawled
      cover every product the view reported.
    """
    per = (meta or {}).get("per_source", {}) or {}
    complete = set()

    for key, info in per.items():
        info = info or {}
        if info.get("error") or not info.get("ingested"):
            continue

        if key == "EMA-CVMP":
            total = info.get("total_reported")
            pages = info.get("pages_crawled")
            if not total or not pages:
                continue  # unknown coverage -> assume partial (safe)
            pages_needed = -(-int(total) // EMA_PAGE_SIZE)  # ceil division
            if int(pages) >= pages_needed:
                complete.add(key)
        else:
            complete.add(key)

    return complete


def pull_update(ingest_date=None, live=None, replace=None):
    """Merge a fresh regulatory pull into the DB and return a summary.

    Parameters
    ----------
    ingest_date : optional ISO date override.
    live        : force live (True) or sample (False); when None, falls back to
                  the ``USE_LIVE_SOURCES`` env flag.
    replace     : when live and True, clear the live-source sample slices before
                  ingesting so the workbench shows only real data. When None,
                  falls back to the ``REPLACE_ON_LIVE`` env flag.
    """
    use_live = bool(live) if live is not None else USE_LIVE_SOURCES
    do_replace = bool(replace) if replace is not None else REPLACE_ON_LIVE

    if not use_live:
        # ---- Original sample behaviour (unchanged) -------------------------
        return db.ingest_dataset(get_update_dataset(), ingest_date=ingest_date,
                                 source_label="simulated-live")

    # ---- Live mode -------------------------------------------------------
    regulatory.setup_logging()
    meta = {"mode": "live", "per_source": {}, "errors": [],
            "fallbacks": [], "live_used": True}
    records = []
    live_sources = []

    # USDA / CVB
    us_recs, us_meta = regulatory.fetch_usda_cvb()
    meta["per_source"]["USDA-CVB"] = us_meta
    if us_recs:
        records.extend(us_recs)
        live_sources.append("USDA-CVB")
    else:
        # Source failed: keep whatever is already in the DB for this region.
        # Do NOT re-ingest the sample slice here — that would create noisy fake
        # change notifications on every run (and thus daily spam emails).
        meta["errors"].append(f"USDA: {us_meta.get('error')}")
        meta["fallbacks"].append("US")

    # EMA / CVMP
    eu_recs, eu_meta = regulatory.fetch_ema_cvmp()
    meta["per_source"]["EMA-CVMP"] = eu_meta
    if eu_recs:
        records.extend(eu_recs)
        live_sources.append("EMA-CVMP")
    else:
        meta["errors"].append(f"EMA: {eu_meta.get('error')}")
        meta["fallbacks"].append("EU")

    # If BOTH live sources failed, the dataset is entirely sample data; keep
    # the original source labels so the demo diff still behaves as before.
    if not live_sources:
        meta["live_used"] = False
        meta["mode"] = "live-failed-fallback-sample"
        summary = db.ingest_dataset(get_update_dataset(),
                                    ingest_date=ingest_date,
                                    source_label="simulated-live")
        summary["meta"] = meta
        return summary

    # Which sources delivered an authoritative FULL listing this run? Only
    # those may drive withdrawal inference (see db.ingest_dataset).
    complete_sources = _complete_sources(meta)
    meta["complete_sources"] = sorted(complete_sources)
    partial = [s for s in live_sources if s not in complete_sources]
    if partial:
        regulatory.log().info(
            "Partial pull for %s - withdrawal inference disabled for these "
            "sources (absence does not imply withdrawal)", ", ".join(partial))

    if do_replace:
        # Clear the illustrative sample sources so the workbench shows only
        # live/real data (regions whose live pull failed are refilled from the
        # sample slice below). Live data uses distinct source tags
        # ("USDA-CVB" / "EMA-CVMP") so it is never wiped here.
        cleared = db.clear_source_products(["USDA", "EMA"])
        regulatory.log().info("Live replace: cleared %d sample records", cleared)

    summary = db.ingest_dataset(records, ingest_date=ingest_date,
                                source_label="live-regulatory",
                                complete_sources=complete_sources)
    summary["meta"] = meta
    return summary


def ensure_seeded():
    """Seed baseline only if the products table is empty.

    The initial baseline import is recorded in change_log (for history) but
    marked as already-read so it does not create noisy unread notifications;
    only *subsequent* pulls raise notifications for genuine changes.
    """
    conn = db.get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    conn.close()
    if n == 0:
        summary = seed_baseline()
        db.mark_notifications_read()
        return summary
    return {"new": 0, "updated": 0, "status_change": 0, "withdrawn": 0,
            "total": n, "changes": [], "already_seeded": True}


if __name__ == "__main__":
    db.init_db()
    print("Baseline:", seed_baseline())
    print("Sample update :", pull_update())
    print("Live update   :", pull_update(live=True))


def _persist_sync_state(summary, started):
    """Record this pull in data/sync_state.json.

    Without this the "last sync" timestamp embedded by build_static.build()
    silently keeps showing the *previous* run, so the published page misreports
    when it was last refreshed. Reuses daily_sync's status builder rather than
    triggering a second (expensive) network crawl.
    """
    import daily_sync

    status = daily_sync.build_status(summary, started=started)
    return daily_sync.persist_status(status)


def run_scheduled_update(force_live=True):
    """Daily job entry point.

    1. Make sure the DB is seeded.
    2. Merge the latest regulator pull (live by default).
    3. Persist the sync state so the static build reports an accurate
       "last sync" time.
    4. Email a digest of any *new* changes — but only if something actually
       changed (notify_email.send_digest returns 0 when nothing is pending, so
       quiet days send no mail).

    Returns the ingest summary with an extra ``emailed`` field:
      >=0  number of changes emailed
      -1   email step failed (data was still updated)
    """
    from datetime import datetime

    started = datetime.now()
    ensure_seeded()
    summary = pull_update(live=force_live)

    try:
        summary["sync_status"] = _persist_sync_state(summary, started)
    except Exception as e:  # never let bookkeeping break the schedule
        try:
            regulatory.log().warning("persist sync_state failed: %s", e)
        except Exception:
            pass

    sent = 0
    try:
        import notify_email
        sent = notify_email.send_digest()
    except Exception as e:  # never let a notify failure break the schedule
        try:
            regulatory.log().warning("notify_email failed: %s", e)
        except Exception:
            pass
        sent = -1
    summary["emailed"] = sent
    return summary
