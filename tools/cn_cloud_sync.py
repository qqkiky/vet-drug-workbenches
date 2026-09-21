#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cloud-safe updater for the domestic veterinary-drug workbench.

Runs both official domestic sources, rebuilds the static/PWA output, records a
machine-readable state file, and appends an auditable changelog entry.  The
script deliberately uses sys.executable so it works on GitHub's Linux runners
as well as on Windows.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench"
DB = WORKBENCH / "drugs.db"
STATE_FILE = ROOT / "data" / "cn_sync_state.json"
CHANGELOG = ROOT / "docs" / "变更日志.md"
HISTORY_LIMIT = 60


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def snapshot() -> dict:
    with sqlite3.connect(DB) as conn:
        return {
            "registration_total": _table_count(conn, "drugs"),
            "clinical_total": _table_count(conn, "clinical_approval"),
            "processed_announcements": _table_count(conn, "processed_ann"),
        }


def run_step(name: str, relative_script: str, env: dict | None = None) -> dict:
    command = [sys.executable, str(ROOT / relative_script)]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env or os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    error = ""
    if completed.returncode:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        error = " | ".join(tail[-4:])[:1000]
    return {
        "name": name,
        "script": relative_script,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "error": error,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def persist(status: dict) -> None:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        state = {"history": []}
    history = list(state.get("history") or [])
    history.insert(0, {
        "date": status["date"],
        "at": status["finished_at"],
        "result": status["result"],
        "registration_added": status["registration_added"],
        "clinical_added": status["clinical_added"],
        "registration_total": status["after"]["registration_total"],
        "clinical_total": status["after"]["clinical_total"],
        "sources": status["sources"],
    })
    state["latest"] = status
    state["history"] = history[:HISTORY_LIMIT]
    write_json(STATE_FILE, state)


def append_changelog(status: dict) -> None:
    source_text = "、".join(
        f'{item["name"]}（{"✓" if item["ok"] else "✗"}）'
        for item in status["sources"]
    )
    block = (
        f'\n### {status["finished_at"]} · 国内工作台\n\n'
        f'- 状态：**{status["result"].upper()}**\n'
        f'- 注册审批：新增 {status["registration_added"]} 条，在库 {status["after"]["registration_total"]} 条\n'
        f'- 临床审批：新增 {status["clinical_added"]} 条，在库 {status["after"]["clinical_total"]} 条\n'
        f'- 数据源：{source_text}\n'
        f'- 说明：自动增量抓取、去重、重建网页与工作簿；失败来源将在下次运行重试。\n'
    )
    with CHANGELOG.open("a", encoding="utf-8") as handle:
        handle.write(block)


def main() -> int:
    started = datetime.now()
    before = snapshot()

    announcement = run_step(
        "农业农村部公告",
        "workbench/build_workbench.py",
    )
    vdts_env = os.environ.copy()
    vdts_env["VDTS_REQUIRE_LIVE"] = "1"
    clinical = run_step(
        "国家兽药基础数据库临床审批",
        "workbench/ingest_vdts_clinical.py",
        vdts_env,
    )

    fill = run_step("适应症补全", "workbench/fill_all_indications.py")
    web = run_step("国内网页重建", "workbench/build_web.py")
    if not fill["ok"] or not web["ok"]:
        raise RuntimeError("国内工作台重建失败；为避免发布半成品，本次不提交")

    source_results = [announcement, clinical]
    if not any(item["ok"] for item in source_results):
        raise RuntimeError("两个国内官方数据源均不可用；本次不提交旧数据")

    after = snapshot()
    finished = datetime.now()
    status = {
        "date": finished.date().isoformat(),
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S"),
        "result": "ok" if all(item["ok"] for item in source_results) else "partial",
        "duration_sec": round((finished - started).total_seconds(), 1),
        "before": before,
        "after": after,
        "registration_added": max(0, after["registration_total"] - before["registration_total"]),
        "clinical_added": max(0, after["clinical_total"] - before["clinical_total"]),
        "sources": source_results,
    }
    persist(status)
    append_changelog(status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAILED] {exc}", file=sys.stderr)
        raise
