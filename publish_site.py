#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_site.py - 组装 GitHub Pages 统一站点。

从两个工作台的构建产物生成一个静态站点：

    _site/index.html   入口页（选择工作台 + 最近更新时间）
    _site/intl/        国际兽用生物制品监管追踪工作台（来自 dist/）
    _site/cn/          国内/进口兽药注册与审批查询工作台（来自 workbench/web/）

用法：
    python publish_site.py             # 默认输出到 _site/
    python publish_site.py --out site  # 指定输出目录
"""
import argparse
import json
import os
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
INTL_SRC = os.path.join(ROOT, "dist")
CN_SRC = os.path.join(ROOT, "workbench", "web")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _v(value):
    return str(value or "—")


def build_landing(intl_ver, cn_ver):
    intl_build = _v((intl_ver or {}).get("build"))
    intl_snapshot = _v((intl_ver or {}).get("snapshot"))
    intl_products = _v((intl_ver or {}).get("products"))
    intl_sync = _v((intl_ver or {}).get("last_sync_at"))
    cn_build = _v((cn_ver or {}).get("build"))
    cn_generated = _v((cn_ver or {}).get("generated"))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>兽药数据收集工作台</title>
<meta name="description" content="国内/进口兽药注册查询与海外兽用生物制品监管追踪，每日自动更新">
<style>
:root{{
  --bg:#0f172a; --card:#ffffff; --ink:#1e293b; --muted:#64748b;
  --brand:#1e6fd9; --brand2:#0ea5a4; --line:#e2e8f0;
}}
*{{box-sizing:border-box; margin:0; padding:0;}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(160deg,#0f172a 0%,#12355f 55%,#0f2f4d 100%);
  color:var(--ink); min-height:100vh; padding:48px 20px;
}}
.wrap{{max-width:960px; margin:0 auto;}}
header{{text-align:center; margin-bottom:40px; color:#fff;}}
header h1{{font-size:28px; letter-spacing:1px;}}
header p{{color:#b6c8e4; margin-top:8px; font-size:14px;}}
.grid{{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:20px;}}
.card{{
  background:var(--card); border-radius:14px; padding:26px 24px;
  box-shadow:0 10px 30px rgba(2,10,30,.35); display:flex; flex-direction:column;
  transition:transform .15s ease; text-decoration:none; color:inherit;
}}
.card:hover{{transform:translateY(-3px);}}
.tag{{
  display:inline-block; font-size:12px; font-weight:600; padding:3px 10px;
  border-radius:999px; margin-bottom:12px; width:fit-content;
}}
.tag.intl{{background:#e0f2fe; color:#0369a1;}}
.tag.cn{{background:#dcfce7; color:#15803d;}}
.card h2{{font-size:19px; margin-bottom:8px;}}
.card .desc{{color:var(--muted); font-size:13.5px; line-height:1.7; flex:1;}}
.meta{{margin-top:18px; padding-top:14px; border-top:1px solid var(--line); font-size:12.5px; color:var(--muted);}}
.meta div{{margin-top:3px;}}
.go{{display:inline-block; margin-top:16px; color:var(--brand); font-weight:600; font-size:14px;}}
footer{{text-align:center; color:#8fa6c9; font-size:12.5px; margin-top:36px; line-height:1.8;}}
footer a{{color:#c4d6f2;}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>兽药数据收集工作台</h1>
    <p>Pet &amp; Veterinary Drug Data Workbenches · 每日自动更新 · 稳定云链接</p>
  </header>
  <div class="grid">
    <a class="card" href="intl/">
      <span class="tag intl">海外监管</span>
      <h2>国际兽用生物制品监管追踪</h2>
      <div class="desc">
        追踪美国 USDA/CVB 与欧盟 EMA/CVMP 获批的猫犬兽用生物制品
        （疫苗 / 诊断试剂 / 治疗性生物制品），支持中英切换、筛选、导出。
      </div>
      <div class="meta">
        <div>数据快照：{intl_snapshot}（在库 {intl_products} 条）</div>
        <div>最近同步：{intl_sync} · 构建 {intl_build}</div>
      </div>
      <span class="go">进入工作台 →</span>
    </a>
    <a class="card" href="cn/">
      <span class="tag cn">国内注册</span>
      <h2>国内 / 进口兽药注册与审批</h2>
      <div class="desc">
        农业农村部公告整理：国产 / 进口新兽药注册、变更注册、临床审批，
        面向宠物（犬猫）用药筛选，PC 与手机同源同步。
      </div>
      <div class="meta">
        <div>构建日期：{cn_generated} · 构建号 {cn_build}</div>
      </div>
      <span class="go">进入工作台 →</span>
    </a>
  </div>
  <footer>
    数据来源：农业农村部 / 中国兽药信息网 · USDA/CVB · EMA/CVMP 官方公开信息<br>
    本入口页由 <a href="https://github.com/qqkiky/vet-drug-workbenches">vet-drug-workbenches</a> 自动发布
  </footer>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="组装 GitHub Pages 站点")
    ap.add_argument("--out", default="_site", help="输出目录（默认 _site）")
    args = ap.parse_args()

    out = os.path.abspath(os.path.join(ROOT, args.out))
    for sub in ("intl", "cn"):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    shutil.copytree(INTL_SRC, os.path.join(out, "intl"))
    shutil.copytree(CN_SRC, os.path.join(out, "cn"))

    intl_ver = read_json(os.path.join(INTL_SRC, "version.json"))
    cn_ver = read_json(os.path.join(CN_SRC, "version.json"))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_landing(intl_ver, cn_ver))

    with open(os.path.join(out, "version.json"), "w", encoding="utf-8") as f:
        json.dump({
            "build": datetime.now().strftime("%Y%m%d%H%M%S"),
            "intl": intl_ver,
            "cn": cn_ver,
        }, f, ensure_ascii=False, indent=2)
    print("站点已组装到 %s（intl=%d 文件, cn=%d 文件）" % (
        out,
        sum(len(fs) for _, _, fs in os.walk(os.path.join(out, "intl"))),
        sum(len(fs) for _, _, fs in os.walk(os.path.join(out, "cn"))),
    ))


if __name__ == "__main__":
    main()
