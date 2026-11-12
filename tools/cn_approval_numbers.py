#!/usr/bin/env python3
"""Match registration drug names to official domestic product approval numbers."""
import json
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "workbench" / "drugs.db"
OUTPUT = ROOT / "workbench" / "approval_numbers.json"
API = "http://vdts.ivdc.org.cn:8099/api/api/cx/h5/sycppzwh/list"


def key(value):
    return "".join((value or "").split())


def fetch(page):
    body = json.dumps({"page": page, "rows": 5000, "conditionItems": []}).encode()
    request = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main():
    with sqlite3.connect(DB) as conn:
        names = {key(row[0]) for row in conn.execute(
            "SELECT DISTINCT drug_name FROM drugs WHERE table_type != 'import_drug'"
        ) if row[0]}
    matched = {}
    page = 1
    while True:
        data = fetch(page)
        rows = data.get("rows") or []
        if not rows:
            break
        for row in rows:
            name = key(row.get("tym"))
            number = (row.get("pzwh") or "").strip()
            company = (row.get("qymc") or "").strip()
            if name in names and number and company:
                item = {"number": number, "company": company,
                        "approved": row.get("pzrq") or ""}
                matched.setdefault(name, {})[(number, company)] = item
        if page * 5000 >= int(data.get("total") or data.get("records") or 0):
            break
        page += 1
    if page < 2:
        raise RuntimeError("官方批准文号接口没有返回完整列表")
    result = {name: sorted(items.values(), key=lambda x: (x["company"], x["number"]))
              for name, items in matched.items()}
    tmp = OUTPUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT)
    print(f"批准文号：读取 {page} 页，匹配 {len(result)} 个药品名称、"
          f"{sum(map(len, result.values()))} 个文号/企业组合")


if __name__ == "__main__":
    main()
