#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cn_daily.py - 国内/进口工作台每日自动流水线。

一次执行完成：抓取公告 → 导入临床审批 → 补全适应症 → 重建网页 → 推送 GitHub。
供 Windows 计划任务每日 20:00 调用（也可手动执行）。

用法：
    python tools/cn_daily.py            # 完整流程
    python tools/cn_daily.py --no-push  # 只更新本地，不推送
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
LOG = os.path.join(ROOT, "data", "cn_daily.log")

STEPS = [
    ("抓取农业农村部公告 + 生成工作簿", os.path.join("workbench", "build_workbench.py")),
    ("导入临床审批数据", os.path.join("workbench", "ingest_vdts_clinical.py")),
    ("补全适应症", os.path.join("workbench", "fill_all_indications.py")),
    ("重建国内工作台网页", os.path.join("workbench", "build_web.py")),
]


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run_step(title, script):
    path = os.path.join(ROOT, script)
    if not os.path.exists(path):
        log("跳过（脚本不存在）：%s" % script)
        return True
    log("开始：%s" % title)
    r = subprocess.run([PY, path], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-3:]
    for line in tail:
        log("    %s" % line.strip()[:200])
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()[-3:]
        for line in err:
            log("    [错误] %s" % line.strip()[:200])
        log("失败：%s（退出码 %s）" % (title, r.returncode))
        return False
    log("完成：%s" % title)
    return True


def main():
    ap = argparse.ArgumentParser(description="国内工作台每日流水线")
    ap.add_argument("--no-push", action="store_true", help="只更新本地，不推送")
    args = ap.parse_args()

    log("=== 国内工作台每日流水线开始 ===")
    ok = True
    for title, script in STEPS:
        if not run_step(title, script):
            ok = False  # 单步失败仍继续后续步骤，保证网页尽量更新
    if not args.no_push:
        log("开始：推送 GitHub")
        r = subprocess.run([PY, os.path.join(ROOT, "git_sync.py")], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        for line in (r.stdout or "").strip().splitlines()[-3:]:
            log("    %s" % line.strip()[:200])
        if r.returncode != 0:
            for line in (r.stderr or "").strip().splitlines()[-3:]:
                log("    [错误] %s" % line.strip()[:200])
            log("失败：推送 GitHub")
            ok = False
        else:
            log("完成：推送 GitHub")
    log("=== 流水线结束（%s）===" % ("全部成功" if ok else "有步骤失败，详见上方日志"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
