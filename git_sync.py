#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git_sync.py - 本地工作台更新后自动提交并推送到 GitHub。

用于国内/进口注册工作台的每日自动化：抓取 + 重建完成后运行本脚本，
即可把 drugs.db、web/ 等全部变更提交并推送到远程仓库，触发云端自动发布。

用法：
    python git_sync.py                    # 自动提交并推送
    python git_sync.py --message "自定义" # 自定义提交信息
"""
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print("$", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    return r.returncode


def main():
    message = None
    args = sys.argv[1:]
    if "--message" in args:
        i = args.index("--message")
        if i + 1 < len(args):
            message = args[i + 1]

    if run(["git", "add", "-A"]) != 0:
        print("git add 失败，请检查仓库状态。")
        return 1

    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if r.returncode == 0:
        print("没有需要提交的变更，跳过推送。")
        return 0

    message = message or "chore: 工作台自动同步 %s" % datetime.now().strftime("%Y-%m-%d %H:%M")
    if run(["git", "commit", "-m", message]) != 0:
        print("git commit 失败。")
        return 1
    if run(["git", "push"]) != 0:
        print("git push 失败，请确认已登录 GitHub（gh auth status）。")
        return 1
    print("已提交并推送到 GitHub，云端将自动重新发布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
