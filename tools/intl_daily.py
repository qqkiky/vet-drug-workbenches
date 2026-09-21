#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intl_daily.py - 国际工作台每日自动流水线（本机准点补位）。

一次执行完成：抓取 USDA/CVB + EMA/CVMP → 入库 → 重建 dist → 推送 GitHub。
供 Windows 计划任务每日调用；云端 GitHub Actions 仍保留为独立备份链路。

用法：
    python tools/intl_daily.py            # 完整流程
    python tools/intl_daily.py --no-push  # 只更新本地
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
LOG = os.path.join(ROOT, "data", "intl_daily.log")


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def step(title, args):
    log("开始：%s" % title)
    env = dict(os.environ)
    env.setdefault("EMA_MAX_PAGES", "40")
    r = subprocess.run([PY] + args, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    for line in (r.stdout or "").strip().splitlines()[-3:]:
        log("    %s" % line.strip()[:200])
    if r.returncode != 0:
        for line in (r.stderr or "").strip().splitlines()[-3:]:
            log("    [错误] %s" % line.strip()[:200])
        log("失败：%s" % title)
        return False
    log("完成：%s" % title)
    return True


def main():
    ap = argparse.ArgumentParser(description="国际工作台每日流水线（本机）")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    log("=== 国际工作台每日流水线开始 ===")
    ok = step("抓取 USDA/CVB + EMA/CVMP 并重建 dist", ["daily_sync.py"])
    if not args.no_push:
        ok = step("提交并推送 GitHub", ["git_sync.py"]) and ok
    log("=== 流水线结束（%s）===" % ("全部成功" if ok else "有步骤失败，详见日志"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
