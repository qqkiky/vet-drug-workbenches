# -*- coding: utf-8 -*-
"""Wire the daily-sync pipeline into app.py (desktop Flask side).

1. Adds GET /api/sync-status so the desktop page shows the same status bar as
   the deployed mobile PWA.
2. Routes the built-in 20:00 scheduler through daily_sync so both entry points
   share one de-duplicating pipeline and one status file.

Idempotent + ASCII anchors only.
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")

ROUTE = '''@app.route("/api/sync-status")
def sync_status():
    """Latest daily_sync.py outcome (shared by desktop + mobile status bar)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "sync_state.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        latest = state.get("latest") or {}
        latest["history"] = state.get("history", [])[:14]
        return jsonify(latest)
    except Exception:
        return jsonify({})


'''

OLD_JOB = """                summary = ingest.run_scheduled_update(force_live=True)
                app.logger.info("Daily 20:00 update: %s", summary)"""

NEW_JOB = """                import daily_sync
                status = daily_sync.persist_status(daily_sync.run_sync())
                app.logger.info("Daily 20:00 sync: %s",
                                daily_sync.format_feedback(status))
                try:
                    import notify_email
                    notify_email.send_digest()
                except Exception as ne:  # noqa: BLE001
                    app.logger.warning("digest failed: %s", ne)"""


def main():
    src = io.open(APP, encoding="utf-8").read()
    changed = []

    if "/api/sync-status" not in src:
        anchor = '@app.route("/api/changes")'
        assert anchor in src, "changes route anchor missing"
        src = src.replace(anchor, ROUTE + anchor, 1)
        changed.append("route")

    if OLD_JOB in src:
        src = src.replace(OLD_JOB, NEW_JOB, 1)
        changed.append("scheduler")

    for mod in ("import json", "import os"):
        if mod not in src.split("app = Flask")[0]:
            src = src.replace("import time\n", "import time\n%s\n" % mod, 1)
            changed.append(mod)

    io.open(APP, "w", encoding="utf-8").write(src)
    print("patched app.py:", ", ".join(changed) or "nothing to do")


if __name__ == "__main__":
    main()
