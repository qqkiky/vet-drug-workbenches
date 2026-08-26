"""Build a self-contained static site (dist/) from the current SQLite data.

The resulting folder can be deployed to any static host (e.g. CloudStudio)
so the workbench is reachable from a fixed public URL without running the
Flask backend. All data is embedded into index.html as __INITIAL_DATA__ and
also written to data.json as a fallback.

Static mode (window.__STATIC__ = true) tells app.js to hide the live-update
and export buttons (which need the backend) and to show a snapshot banner.
"""
import os
import json
import shutil
from datetime import datetime

import db

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
DIST = os.path.join(ROOT, "dist")
SYNC_STATE = os.path.join(ROOT, "data", "sync_state.json")


def _load_sync_status():
    """Latest daily_sync.py result, embedded so the UI can show a status bar."""
    try:
        with open(SYNC_STATE, "r", encoding="utf-8") as f:
            state = json.load(f)
        latest = state.get("latest") or {}
        latest["history"] = state.get("history", [])[:14]
        return latest
    except Exception:
        return {}


def build():
    os.makedirs(DIST, exist_ok=True)

    initial = {
        "meta": {
            "regions": db.REGIONS,
            "species": db.SPECIES,
            "product_types": db.PRODUCT_TYPES,
            "statuses": db.STATUSES,
            "sources": ["USDA", "EMA"],
        },
        "products": db.get_products({}),
        "stats": db.get_stats(),
        "changes": db.get_changes(limit=300),
        "notifications": db.get_notifications(only_unread=True, limit=50),
    }

    snapshot = datetime.now().strftime("%Y-%m-%d")
    build_id = datetime.now().strftime("%Y%m%d%H%M%S")
    sync_status = _load_sync_status()

    # data.json fallback
    with open(os.path.join(DIST, "data.json"), "w", encoding="utf-8") as f:
        json.dump(initial, f, ensure_ascii=False, default=str)

    # index.html with embedded data + static flag
    with open(os.path.join(STATIC, "index.html"), "r", encoding="utf-8") as f:
        html = f.read()

    marker = '<script src="app.js?v=6" defer></script>'
    assert marker in html, "app.js marker not found in index.html"

    script = (
        "<script>window.__STATIC__ = true; "
        "window.__SNAPSHOT_DATE__ = " + json.dumps(snapshot) + "; "
        "window.__BUILD_ID__ = " + json.dumps(build_id) + "; "
        "window.__SYNC_STATUS__ = "
        + json.dumps(sync_status, ensure_ascii=False, default=str) + "; "
        "window.__INITIAL_DATA__ = "
        + json.dumps(initial, ensure_ascii=False, default=str)
        + ";</script>"
    )
    html = html.replace(marker, script + "\n  " + marker)

    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # copy static assets
    for fn in ["app.js", "styles.css", "chart.umd.min.js",
               "manifest.webmanifest", "icon-192.png", "icon-512.png"]:
        shutil.copy2(os.path.join(STATIC, fn), os.path.join(DIST, fn))

    # sw.js gets a build-specific cache name so clients refresh automatically
    with open(os.path.join(STATIC, "sw.js"), "r", encoding="utf-8") as f:
        sw = f.read()
    sw = sw.replace('const BUILD = "dev";', 'const BUILD = "%s";' % build_id)
    with open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw)

    # version.json - polled by the client to detect a fresh daily sync
    with open(os.path.join(DIST, "version.json"), "w", encoding="utf-8") as f:
        json.dump({
            "build": build_id,
            "snapshot": snapshot,
            "products": len(initial["products"]),
            "last_sync_at": sync_status.get("last_sync_at", ""),
            "sync_result": sync_status.get("result", ""),
        }, f, ensure_ascii=False)

    # sync_status.json - full detail for the status bar / history view
    with open(os.path.join(DIST, "sync_status.json"), "w", encoding="utf-8") as f:
        json.dump(sync_status, f, ensure_ascii=False, default=str)

    print("Built dist/  products=%d changes=%d snapshot=%s build=%s"
          % (len(initial["products"]), len(initial["changes"]), snapshot, build_id))


if __name__ == "__main__":
    build()
