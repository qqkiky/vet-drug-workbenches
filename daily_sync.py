#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_sync.py - Daily automated regulatory pull for the mobile workbench.

Pipeline
--------
1. Pull the live regulator feeds (USDA/CVB catalog + EMA/CVMP) via ingest.py.
2. Merge into SQLite through db.ingest_dataset(), which de-duplicates on
   (region, approval_number) and only records a change when the content hash
   actually differs.
3. Identify the products that are genuinely NEW in this run and keep the ones
   whose approval_date falls inside the recent window (newly approved drugs).
4. Persist a machine-readable status file so the front-end can show a compact
   "last sync" banner, plus a rolling run history for auditing.
5. Rebuild dist/ so the deployed mobile PWA picks up the new data.

De-duplication is layered so a repeated run never double-inserts:
  L1  (region, approval_number) uniqueness  -> existing rows are never re-added
  L2  record_hash content comparison        -> unchanged rows log no change
  L3  run fingerprint per calendar day      -> a same-day rerun updates the
      existing history entry instead of appending a duplicate one

Usage
-----
    python daily_sync.py              # full run: fetch + merge + rebuild dist
    python daily_sync.py --no-build   # fetch + merge only
    python daily_sync.py --json       # emit only the JSON summary on stdout
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "data")
DIST_DIR = os.path.join(ROOT, "dist")
STATE_FILE = os.path.join(DATA_DIR, "sync_state.json")
LOCK_FILE = os.path.join(DATA_DIR, "daily_sync.lock")
LOG_FILE = os.path.join(DATA_DIR, "daily_sync.log")

# A product counts as "newly approved" when its approval_date is within this
# many days of the run date. Regulator catalogs publish in batches, so a short
# window would miss records that are new to us but dated a few weeks back.
NEW_APPROVAL_WINDOW_DAYS = 120
# How many runs to keep in the rolling history.
HISTORY_LIMIT = 60
# Stale lock guard (seconds) so a crashed run cannot block the schedule.
LOCK_TTL = 45 * 60

SOURCE_LABELS = {
    "USDA-CVB": "美国 USDA/CVB",
    "EMA-CVMP": "欧盟 EMA/CVMP",
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


def acquire_lock():
    """Single-instance guard.

    The workspace sandbox blocks file deletion, so the lock is a *state* file
    rather than a presence marker: releasing rewrites it to "idle" instead of
    removing it. A run older than LOCK_TTL is treated as crashed and reclaimed.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    cur = _read_json(LOCK_FILE, None)
    if isinstance(cur, dict) and cur.get("state") == "running":
        age = time.time() - float(cur.get("ts") or 0)
        if age < LOCK_TTL:
            return False
        _log("reclaiming stale lock (%.0f min old)" % (age / 60))
    _write_json(LOCK_FILE, {"state": "running", "pid": os.getpid(),
                            "ts": time.time(),
                            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return True


def release_lock():
    """Mark the lock idle (never delete - deletion is sandbox-blocked)."""
    try:
        _write_json(LOCK_FILE, {"state": "idle", "pid": os.getpid(),
                                "ts": time.time(),
                                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception:
        pass


# --------------------------------------------------------------------------
# core
# --------------------------------------------------------------------------
def _collect_new_products(changes, run_date):
    """Turn the NEW entries of an ingest summary into a display list.

    Only products whose approval_date sits inside the recent window are kept,
    so a first-time backfill does not report thousands of historical rows as
    "today's approvals".
    """
    import db

    conn = db.get_conn()
    cutoff = (run_date - timedelta(days=NEW_APPROVAL_WINDOW_DAYS)).isoformat()
    items = []
    for ch in changes:
        if ch.get("type") != "NEW":
            continue
        row = conn.execute(
            "SELECT product_name, region, approval_number, manufacturer, "
            "       product_type, species, approval_date, source, source_url "
            "FROM products WHERE id=?", (ch.get("product_id"),)).fetchone()
        if not row:
            continue
        rec = dict(row)
        rec["recent"] = bool(rec.get("approval_date")
                             and str(rec["approval_date"]) >= cutoff)
        items.append(rec)
    conn.close()

    recent = [i for i in items if i["recent"]]
    recent.sort(key=lambda x: str(x.get("approval_date") or ""), reverse=True)
    return items, recent


def _source_states(meta):
    """Normalise per-source fetch outcome for the UI."""
    out = []
    per = (meta or {}).get("per_source", {}) or {}
    for key, info in per.items():
        info = info or {}
        count = info.get("ingested")
        if count is None:
            count = info.get("records", info.get("count", 0))
        ok = bool(count) and not info.get("error")
        out.append({
            "key": key,
            "label": SOURCE_LABELS.get(key, key),
            "ok": ok,
            "count": count or 0,
            "url": info.get("url", ""),
            "error": (info.get("error") or "")[:200],
        })
    out.sort(key=lambda x: x["key"])
    return out


def _base_status(started, run_date):
    """Empty status skeleton for one synchronisation cycle."""
    return {
        "last_sync_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_date": run_date.isoformat(),
        "result": "ok",
        "message": "",
        "added": 0,
        "updated": 0,
        "status_change": 0,
        "total": 0,
        "sources": [],
        "new_items": [],
        "new_recent_count": 0,
        "duration_sec": 0,
        "window_days": NEW_APPROVAL_WINDOW_DAYS,
    }


def build_status(summary, started=None, run_date=None):
    """Turn an ``ingest.pull_update`` summary into the UI-facing status dict.

    Split out of ``run_sync`` so any caller that already performed its own pull
    (e.g. ``ingest.run_scheduled_update``) can persist an accurate "last sync"
    record without paying for a second network crawl.
    """
    run_date = run_date or date.today()
    started = started or datetime.now()
    status = _base_status(started, run_date)

    meta = (summary or {}).get("meta", {}) or {}
    status["added"] = summary.get("new", 0)
    status["updated"] = summary.get("updated", 0)
    status["status_change"] = summary.get("status_change", 0)
    status["total"] = summary.get("total", 0)
    status["sources"] = _source_states(meta)

    all_new, recent_new = _collect_new_products(summary.get("changes", []), run_date)
    status["new_recent_count"] = len(recent_new)
    status["new_items"] = recent_new[:20]

    ok_sources = [s for s in status["sources"] if s["ok"]]
    if not ok_sources:
        status["result"] = "failed"
        status["message"] = "所有数据源均不可用，本次未更新数据"
    elif len(ok_sources) < len(status["sources"]):
        failed = "、".join(s["label"] for s in status["sources"] if not s["ok"])
        status["result"] = "partial"
        status["message"] = "部分数据源不可用（%s），其余已更新" % failed
    else:
        if status["added"] or status["updated"] or status["status_change"]:
            status["message"] = "新增 %d 条，变更 %d 条" % (
                status["added"], status["updated"] + status["status_change"])
        else:
            status["message"] = "数据源无新增，已是最新"

    status["duration_sec"] = round((datetime.now() - started).total_seconds(), 1)
    return status


def run_sync(force=False):
    """Execute one synchronisation cycle (live pull) and return the status dict."""
    import db
    import ingest

    run_date = date.today()
    started = datetime.now()

    db.init_db()
    ingest.ensure_seeded()

    try:
        summary = ingest.pull_update(live=True)
    except Exception as e:
        _log("抓取失败：%s" % e)
        _log(traceback.format_exc())
        status = _base_status(started, run_date)
        status["result"] = "failed"
        status["message"] = "数据源抓取失败：%s" % e
        status["duration_sec"] = round((datetime.now() - started).total_seconds(), 1)
        return status

    return build_status(summary, started, run_date)


def persist_status(status):
    """Write sync_status.json + rolling history (same-day runs are merged)."""
    state = _read_json(STATE_FILE, {"history": []})
    history = state.get("history", [])

    entry = {
        "date": status["last_sync_date"],
        "at": status["last_sync_at"],
        "result": status["result"],
        "added": status["added"],
        "updated": status["updated"],
        "status_change": status["status_change"],
        "total": status["total"],
        "runs": 1,
        "message": status["message"],
    }

    # L3 de-duplication: merge repeated runs on the same calendar day.
    if history and history[0].get("date") == entry["date"]:
        prev = history[0]
        entry["added"] = prev.get("added", 0) + entry["added"]
        entry["updated"] = prev.get("updated", 0) + entry["updated"]
        entry["status_change"] = prev.get("status_change", 0) + entry["status_change"]
        entry["runs"] = prev.get("runs", 1) + 1
        history[0] = entry
    else:
        history.insert(0, entry)

    state["history"] = history[:HISTORY_LIMIT]
    state["latest"] = status
    _write_json(STATE_FILE, state)

    status["today_added"] = history[0]["added"]
    status["runs_today"] = history[0]["runs"]
    status["history"] = state["history"][:14]
    return status


def rebuild_dist(status):
    """Regenerate dist/ so the deployed PWA serves the refreshed dataset."""
    import build_static

    build_static.build()
    _write_json(os.path.join(DIST_DIR, "sync_status.json"), status)
    _log("dist/ 已重建")


def format_feedback(status):
    """Short human-readable status line for the scheduler / chat feedback."""
    icon = {"ok": "OK", "partial": "PARTIAL", "failed": "FAILED"}.get(
        status["result"], "?")
    srcs = " ".join(
        "%s%s" % (s["label"], "✓" if s["ok"] else "✗") for s in status["sources"])
    return (
        "[%s] %s 同步完成 | 新增 %d 条（近%d天新批 %d 条）| 变更 %d 条 | "
        "在库 %d 条 | 数据源: %s | 耗时 %.1fs | %s" % (
            icon, status["last_sync_at"], status["added"],
            status.get("window_days", NEW_APPROVAL_WINDOW_DAYS),
            status["new_recent_count"],
            status["updated"] + status["status_change"], status["total"],
            srcs or "无", status["duration_sec"], status["message"]))


def main():
    ap = argparse.ArgumentParser(description="每日自动抓取兽用生物制品审批动态")
    ap.add_argument("--no-build", action="store_true", help="仅同步数据，不重建 dist/")
    ap.add_argument("--json", action="store_true", help="仅输出 JSON 摘要")
    ap.add_argument("--force", action="store_true", help="忽略锁文件强制执行")
    args = ap.parse_args()

    if not args.force and not acquire_lock():
        msg = "已有同步任务在运行，本次跳过"
        print(json.dumps({"result": "skipped", "message": msg}, ensure_ascii=False)
              if args.json else "[SKIP] " + msg)
        return 0

    try:
        status = run_sync()
        status = persist_status(status)
        if not args.no_build:
            try:
                rebuild_dist(status)
                status["dist_built"] = True
            except Exception as e:
                _log("dist 重建失败：%s" % e)
                status["dist_built"] = False
                status["message"] += "（dist 重建失败：%s）" % e
        if args.json:
            print(json.dumps(status, ensure_ascii=False, default=str))
        else:
            _log(format_feedback(status))
        return 0 if status["result"] != "failed" else 1
    finally:
        if not args.force:
            release_lock()


if __name__ == "__main__":
    sys.exit(main())
