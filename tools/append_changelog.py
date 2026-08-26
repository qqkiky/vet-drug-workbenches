#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_changelog.py - 把最近一次国际工作台同步结果追加到变更日志。

用法：
    python tools/append_changelog.py
"""
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "sync_state.json")
LOG = os.path.join(ROOT, "docs", "变更日志.md")


def main():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        print("读取同步状态失败：", e)
        return 1

    latest = state.get("latest") or {}
    entry = latest.get("last_sync_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = latest.get("result", "ok")
    added = latest.get("added", 0)
    updated = latest.get("updated", 0)
    status_change = latest.get("status_change", 0)
    total = latest.get("total", 0)
    message = latest.get("message", "")
    sources = "、".join(
        "%s（%s）" % (s.get("label", s.get("key", "?")), "✓" if s.get("ok") else "✗")
        for s in latest.get("sources", [])
    ) or "无"

    block = (
        "\n### %s\n\n"
        "- 状态：**%s**\n"
        "- 新增 %s 条 / 变更 %s 条 / 状态变更 %s 条；在库共 %s 条\n"
        "- 数据源：%s\n"
        "- 说明：%s\n"
    ) % (entry, result.upper(), added, updated, status_change, total, sources, message or "—")

    with open(LOG, "a", encoding="utf-8") as f:
        f.write(block)
    print("已追加变更日志：", entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
