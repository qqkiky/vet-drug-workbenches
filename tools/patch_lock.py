# -*- coding: utf-8 -*-
"""Replace the delete-based lock in daily_sync.py with a state-file lock.

The sandbox blocks os.remove() on this workspace (safe-delete fail-closed), so
releasing the lock by deleting the file left a permanent 'running' marker and
every later run would skip. The lock now stores a JSON state and is released by
rewriting it, never by deleting.
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "daily_sync.py")

NEW_BLOCK = '''def acquire_lock():
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
'''


def main():
    src = io.open(TARGET, encoding="utf-8").read()
    start = src.index("def acquire_lock():")
    end = src.index("# ---", start)
    patched = src[:start] + NEW_BLOCK + "\n\n" + src[end:]
    assert "os.remove(LOCK_FILE)" not in patched, "old lock removal still present"
    io.open(TARGET, "w", encoding="utf-8").write(patched)
    print("patched lock mechanism, %d -> %d bytes" % (len(src), len(patched)))


if __name__ == "__main__":
    main()
