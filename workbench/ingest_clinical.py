#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_clinical.py — 兽药临床审批数据摄取管道。

数据来源策略（满足需求：主源 vdts.ivdc.org.cn，官方未及时更新时从企业新闻补充）：
  1) fetch_vdts()   : 尝试从主管网站抓取。该站为 JS 单页应用(SPA)，其数据 API 需
                     通过无头浏览器(Playwright)渲染后捕获 XHR。本函数提供可启用的
                     抓取骨架；在可执行环境中运行时填入真实接口即可。当前若环境无法
                     渲染，则跳过并明确记录，不污染本地数据。
  2) supplement      : 从 clinical_supplement.json 读取经人工/企业新闻核查的补充记录，
                     去重写入 clinical_approval，并写一条 update_log（更新动态/来源说明）。

每次运行都会把“新增条数 + 来源 + 说明”写入 update_log，供前端「更新动态」展示。

用法:
  python ingest_clinical.py            # 执行补充摄取(默认)
  python ingest_clinical.py --vdts     # 额外尝试 vdts 抓取(需 Playwright)
"""
import sqlite3
import os
import json
import datetime
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "drugs.db")
SUPPLEMENT = os.path.join(HERE, "clinical_supplement.json")
VDTS_URL = "http://vdts.ivdc.org.cn:8099/cx/#/"

REG_MAP = {"domestic": "国产新兽药注册", "import": "进口新兽药注册"}


def connect():
    return sqlite3.connect(DB)


def upsert_records(records, source, note):
    """写入补充/抓取记录，去重(approval_no+org)，返回新增条数，并写 update_log。"""
    c = connect()
    added = 0
    for r in records:
        reg = r.get("reg_type", "domestic")
        if reg not in REG_MAP:
            reg = "domestic"
        approval_no = (r.get("approval_no") or "").strip()
        org = (r.get("org") or "").strip()
        exists = c.execute(
            "SELECT 1 FROM clinical_approval WHERE approval_no=? AND org=?",
            (approval_no, org),
        ).fetchone()
        if exists:
            continue
        c.execute(
            """INSERT INTO clinical_approval
               (reg_type,drug_name,org,species,indication,approval_no,accept_no,
                approve_date,status,is_pet,source_name,source_url,note,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (reg, r.get("drug_name", ""), org, r.get("species", ""),
             r.get("indication", ""), approval_no, r.get("accept_no", ""),
             r.get("approve_date", ""), r.get("status", "同意临床试验"),
             int(r.get("is_pet", 0)), r.get("source_name", ""),
             r.get("source_url", ""), r.get("note", ""),
             datetime.date.today().isoformat()),
        )
        added += 1
    c.commit()
    total = c.execute("SELECT COUNT(*) FROM clinical_approval").fetchone()[0]
    if added > 0 or note:
        c.execute(
            """INSERT INTO update_log (ts,domain,source,note,added,total)
               VALUES (?,?,?,?,?,?)""",
            (datetime.date.today().isoformat(), "clinical", source, note, added, total),
        )
        c.commit()
    c.close()
    return added, total


def read_supplement():
    if not os.path.exists(SUPPLEMENT):
        return []
    with open(SUPPLEMENT, encoding="utf-8") as f:
        data = json.load(f)
    recs = data.get("records", []) if isinstance(data, dict) else data
    # 过滤模板占位记录（含“示例/example/XXX”等占位符的不要入库）
    clean = []
    for r in recs:
        blob = " ".join(str(r.get(k, "")) for k in ("approval_no", "org", "drug_name"))
        if not r.get("approval_no") or "示例" in blob or "example" in blob.lower() or "xxx" in str(r.get("approval_no", "")).lower():
            continue
        clean.append(r)
    return clean


def fetch_vdts():
    """
    从主管网站抓取临床审批数据。

    该站为 SPA，真实数据经 JS 从后端 API 加载。可靠抓取需要无头浏览器渲染并捕获 XHR。
    下方为可启用骨架：在已安装 Playwright 的环境中，渲染页面、监听网络请求拿到 JSON，
    再映射为 clinical_approval 字段即可。当前环境若不可用，返回 [] 并由 supplement 兜底。
    """
    try:
        from playwright.sync_api import sync_playwright  # 需 pip install playwright
    except ImportError:
        print("[vdts] 未安装 playwright，跳过官网抓取（使用 supplement 补充）。")
        return []

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = p.chromium.new_page() if False else browser.new_page()
            captured = []
            page.on("response", lambda resp: captured.append(resp) if "approval" in resp.url else None)
            page.goto(VDTS_URL, timeout=30000)
            page.wait_for_timeout(4000)
            # TODO: 根据捕获到的真实接口解析 results
            browser.close()
    except Exception as e:
        print(f"[vdts] 抓取失败: {e}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vdts", action="store_true", help="尝试从 vdts 主管网站抓取")
    args = ap.parse_args()

    # 1) supplement（企业新闻/人工核查补充）
    supp = read_supplement()
    if supp:
        added, total = upsert_records(
            supp, "enterprise_news",
            f"从 clinical_supplement.json 补充企业新闻核查记录 {len(supp)} 条（待去重）。"
            f"主管网站 {VDTS_URL} 为官方主数据源。",
        )
        print(f"[supplement] 新增 {added} 条，临床审批累计 {total} 条")
    else:
        print("[supplement] 无补充文件或为空，跳过")

    # 2) vdts 官网抓取（可选）
    if args.vdts:
        recs = fetch_vdts()
        if recs:
            added, total = upsert_records(recs, "vdts", f"从主管网站抓取 {len(recs)} 条。")
            print(f"[vdts] 新增 {added} 条，累计 {total} 条")
        else:
            print("[vdts] 本次未获取到官网数据")


if __name__ == "__main__":
    main()
