#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git_sync.py - 本地工作台更新后自动提交并推送到 GitHub。

用于国内/进口注册工作台的每日自动化：抓取 + 重建完成后运行本脚本，
即可把 drugs.db、web/ 等全部变更提交并推送到远程仓库，触发云端自动发布。

每次运行会把结果写入 data/git_sync.log，供定时任务事后核对。

用法：
    python git_sync.py                    # 自动提交并推送
    python git_sync.py --message "自定义" # 自定义提交信息
"""
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT, "data", "git_sync.log")


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    return r.returncode


def main():
    message = None
    args = sys.argv[1:]
    if "--message" in args:
        i = args.index("--message")
        if i + 1 < len(args):
            message = args[i + 1]

    log("git_sync 开始")
    if run(["git", "add", "-A"]) != 0:
        log("git add 失败")
        return 1

    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if r.returncode == 0:
        log("没有需要提交的变更，跳过推送")
        return 0

    message = message or "chore: 工作台自动同步 %s" % datetime.now().strftime("%Y-%m-%d %H:%M")
    if run(["git", "commit", "-m", message]) != 0:
        log("git commit 失败")
        return 1
    if run(["git", "push"]) != 0:
        log("git push 失败（请检查 GitHub 登录与网络）")
        return 1
    log("已提交并推送到 GitHub，云端将自动重新发布")
    return 0


if __name__ == "__main__":
    sys.exit(main())
