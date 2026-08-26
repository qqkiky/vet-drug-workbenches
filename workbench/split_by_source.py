# -*- coding: utf-8 -*-
"""
从历史数据库(drugs.db)中读取宠物药记录，按药品来源属性(国产/进口)拆分，
复用 build_workbench.build_excel 生成两个格式与「宠物药注册工作台.xlsx」完全一致的工作簿：
  - 国产宠物药注册工作台.xlsx  (table_type in new_drug, change)
  - 进口宠物药注册工作台.xlsx  (table_type == import_drug)
不重新抓取网络，直接以 DB 为唯一数据源。
"""
import os
import sqlite3
import importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "drugs.db")

# 复用 build_workbench 的 build_excel，保证列/布局/统计结构完全一致
spec = importlib.util.spec_from_file_location("bw", os.path.join(ROOT, "build_workbench.py"))
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)
build_excel = bw.build_excel

COLS = ["ann_num", "ann_date", "ann_title", "table_type", "drug_type", "drug_name",
        "org", "category", "country", "cert_no", "monitor_period", "valid_period",
        "change_item", "std_source", "remark", "is_pet", "source_url"]

con = sqlite3.connect(DB)
rows = con.execute("SELECT %s FROM drugs WHERE is_pet=1" % ",".join(COLS)).fetchall()
con.close()
records = [dict(zip(COLS, r)) for r in rows]

domestic = [r for r in records if r["table_type"] in ("new_drug", "change")]
imported = [r for r in records if r["table_type"] == "import_drug"]

dom_path = os.path.join(ROOT, "国产宠物药注册工作台.xlsx")
imp_path = os.path.join(ROOT, "进口宠物药注册工作台.xlsx")

build_excel(domestic, dom_path, "国产宠物药注册工作台 · 统计汇总", pet_only=True)
build_excel(imported, imp_path, "进口宠物药注册工作台 · 统计汇总", pet_only=True)

print("宠物药总计:", len(records))
print("国产:", len(domestic), "->", dom_path)
print("进口:", len(imported), "->", imp_path)
assert len(domestic) + len(imported) == len(records), "拆分后数量之和应等于总数"
print("校验通过：国产 + 进口 = 总计，无重叠/遗漏")
