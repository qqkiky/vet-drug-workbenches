#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enrich_intl_data.py - EMA 数据适应症补全（存量数据一次性增强）。

EMA/CVMP 检索列表只含活性成分；本脚本用 ema_indications 词库把
存量 EMA 记录的 indication 从“成分列表”改写为规范英文适应症，
并同步重算 record_hash（差异引擎据此识别字段变化）。

用法：
    python tools/enrich_intl_data.py --stats    # 仅统计成分覆盖情况
    python tools/enrich_intl_data.py --apply    # 写回数据库
    python tools/enrich_intl_data.py --apply --build   # 写回并重建 dist/
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DB = os.path.join(ROOT, "data", "vet_biologics.db")

import db  # noqa: E402
from ema_indications import enrich_indication  # noqa: E402


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def stats():
    c = _conn()
    rows = c.execute(
        "SELECT id, indication, product_type FROM products WHERE source='EMA-CVMP'"
    ).fetchall()
    total = len(rows)
    mapped = 0
    samples = []
    for r in rows:
        enriched = enrich_indication(r["indication"], r["product_type"])
        if enriched and "Active substance" not in enriched:
            mapped += 1
        else:
            samples.append((r["indication"] or "")[:100])
    print("EMA rows: %d | 词库可补全: %d | 待人工/官方补充: %d"
          % (total, mapped, total - mapped))
    print("--- 未覆盖样本（前 20）---")
    for s in samples[:20]:
        print("  ", s)


def apply(build=False):
    c = _conn()
    rows = c.execute(
        "SELECT id, indication, product_type, region, species, product_name, "
        "manufacturer, dosage_form, strength, approval_date, status, source "
        "FROM products WHERE source='EMA-CVMP'"
    ).fetchall()
    changed = 0
    for r in rows:
        enriched = enrich_indication(r["indication"], r["product_type"])
        if not enriched or enriched == (r["indication"] or ""):
            continue
        rec = dict(r)
        rec["indication"] = enriched
        new_hash = db._hash(rec)
        c.execute("UPDATE products SET indication=?, record_hash=? WHERE id=?",
                  (enriched, new_hash, r["id"]))
        changed += 1
    c.commit()
    print("已补全 %d 条 EMA 记录" % changed)
    if build:
        import build_static
        build_static.build()


def main():
    ap = argparse.ArgumentParser(description="EMA 数据适应症增强")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    if args.stats:
        stats()
    if args.apply:
        apply(build=args.build)


if __name__ == "__main__":
    main()
