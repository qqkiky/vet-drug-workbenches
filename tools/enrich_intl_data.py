#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enrich_intl_data.py - 国际工作台数据质量增强（EMA 词库 + USDA 清洗）。

用法：
    python tools/enrich_intl_data.py --stats    # 仅统计
    python tools/enrich_intl_data.py --apply    # 写回数据库并重建 dist/
"""
import argparse
import collections
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vet_biologics.db")

SUBSTANCE_INDICATIONS = {}


def _connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _norm_substance(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def stats():
    conn = _connect()
    rows = conn.execute(
        "SELECT product_name, indication, species, product_type, source "
        "FROM products WHERE source='EMA-CVMP'"
    ).fetchall()
    print("EMA rows:", len(rows))
    print("species:", dict(collections.Counter(r["species"] for r in rows)))
    print("product_type:", dict(collections.Counter(r["product_type"] for r in rows)))
    subs = collections.Counter(_norm_substance(r["indication"]) for r in rows)
    print("unique substances:", len(subs))
    for s, c in subs.most_common():
        print("%3d | %s" % (c, s[:90]))


def main():
    ap = argparse.ArgumentParser(description="国际工作台数据质量增强")
    ap.add_argument("--stats", action="store_true", help="仅输出统计")
    ap.add_argument("--apply", action="store_true", help="写回数据库并重建 dist/")
    args = ap.parse_args()
    if args.stats:
        stats()
    elif args.apply:
        print("apply 尚未实现")


if __name__ == "__main__":
    main()
