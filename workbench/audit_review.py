# -*- coding: utf-8 -*-
"""整合审计：Pass A(行内明示物种) + Pass B(伴侣动物化药词库匹配)。
不修改数据库，仅输出待恢复清单与物种判定，供复核。"""
import os, re, sqlite3
from bs4 import BeautifulSoup
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(ROOT, "pages")
DB = os.path.join(ROOT, "drugs.db")

con = sqlite3.connect(DB)
recs = con.execute(
    "SELECT id,ann_num,drug_name,table_type,drug_type,is_pet,remark,monitor_period,source_url "
    "FROM drugs WHERE drug_type='化药'").fetchall()

def page_for(url):
    m = re.search(r"(\d{6}/t\d+_\d+\.htm)", url or "")
    if m:
        return os.path.join(PAGES, "._" + m.group(1).replace("/", "_"))
    return None

# ---------- Pass A: 行内明示物种 ----------
explicit = {}  # id -> species_str
for r in recs:
    rid, ann, name, ttype, dtype, ispet, remark, mon, url = r
    if ispet != 0:
        continue
    pf = page_for(url)
    if not pf or not os.path.exists(pf):
        continue
    html = open(pf, encoding="utf-8", errors="ignore").read()
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all("table"):
        for tr in t.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            first = cells[0]
            if name and (name == first or name in first or first in name) and len(first) >= 2:
                rowtext = " ".join(cells)
                sp = set()
                if "犬" in rowtext: sp.add("犬")
                if "猫" in rowtext: sp.add("猫")
                if "宠物" in rowtext or "伴侣" in rowtext: sp.add("宠物")
                if sp:
                    explicit[rid] = ("".join(sorted(sp)), rowtext)
                break
        if rid in explicit:
            break

# ---------- Pass B: 伴侣动物化药词库 ----------
# 物种映射: 犬 / 猫 / 犬猫通用
LEX = {
    "氟雷拉纳":"犬猫通用", "阿福拉纳":"犬猫通用", "沙罗拉纳":"犬猫通用", "洛替拉纳":"犬猫通用",
    "司拉菌素":"犬猫通用", "塞拉菌素":"犬猫通用", "多杀菌素":"犬猫通用", "非泼罗尼":"犬猫通用",
    "吡虫啉":"犬猫通用", "烯啶虫胺":"犬猫通用", "米尔贝肟":"犬猫通用", "双甲脒":"犬",
    "虱螨脲":"犬猫通用", "甲氧普烯":"犬猫通用", "吡丙醚":"犬猫通用", "咪康唑":"犬猫通用",
    "格拉匹仑":"犬", "普瑞巴林":"猫", "卡洛芬":"犬猫通用", "非罗考昔":"犬", "地洛昔康":"犬",
    "维他昔布":"猫", "美洛昔康":"犬猫通用", "依托度酸":"犬", "吡罗昔康":"犬猫通用", "罗非考昔":"犬",
    "礼舒替尼":"犬", "加巴喷丁":"犬猫通用", "替来他明":"犬猫通用",
    "马波沙星":"犬猫通用", "头孢维星":"犬猫通用",
    "盐酸特比萘芬":"犬猫通用", "酮康唑":"犬猫通用", "伊曲康唑":"犬猫通用", "氟康唑":"犬猫通用", "灰黄霉素":"犬猫通用",
    "盐酸氯米帕明":"犬", "盐酸氟西汀":"犬", "司来吉兰":"犬", "苯巴比妥":"犬猫通用",
    "环孢素":"犬", "吡喹酮":"犬猫通用", "硼酸":"犬猫通用",
}
#  borderline: 食品动物也大量使用，需人工确认，先不自动恢复
BORDERLINE = ["恩诺沙星","阿莫西林","多西环素","伊维菌素","芬苯达唑","阿苯达唑","莫昔克丁",
              "乙酰氨基阿维菌素","甲硝唑","克林霉素","头孢噻呋","左旋咪唑","噻嘧啶","非班太尔","磺胺"]

lex_hits = {}  # id -> (species, keyword)
for r in recs:
    rid, ann, name, ttype, dtype, ispet, remark, mon, url = r
    if ispet != 0:
        continue
    if rid in explicit:
        continue
    for kw, sp in LEX.items():
        if kw in name:
            # 商品名/规格中的 犬用/猫用 覆盖
            if "犬用" in name or "（犬）" in name: sp = "犬"
            elif "猫用" in name or "（猫）" in name: sp = "猫"
            lex_hits[rid] = (sp, kw)
            break

# borderline 命中（供提示）
borderline_found = defaultdict(list)
for r in recs:
    rid, ann, name, ttype, dtype, ispet, remark, mon, url = r
    if ispet != 0:
        continue
    if rid in explicit or rid in lex_hits:
        continue
    for kw in BORDERLINE:
        if kw in name:
            borderline_found[kw].append((rid, ann, name))
            break

# ---------- 合并输出 ----------
print("===== Pass A 行内明示 (公告明示物种, is_pet=0) =====")
print("数量:", len(explicit))
for rid,(sp,row) in explicit.items():
    rec = next(x for x in recs if x[0]==rid)
    print(f"  [{sp}] ann{rec[1]} id{rid} {rec[2]}")

print("\n===== Pass B 词库匹配 (药理推断物种, is_pet=0) =====")
print("数量:", len(lex_hits))
for rid,(sp,kw) in lex_hits.items():
    rec = next(x for x in recs if x[0]==rid)
    print(f"  [{sp}|词:{kw}] ann{rec[1]} id{rid} {rec[2]}")

print("\n===== Borderline 命中 (食品动物也用, 未自动恢复, 待人工确认) =====")
for kw, lst in borderline_found.items():
    print(f"  {kw}: {len(lst)} 条 (例: {lst[0][2] if lst else ''})")

# 已 is_pet=1 但无行内物种明示的（可能也缺物种标注）
no_explicit_pet1 = [(r[0],r[1],r[2]) for r in recs if r[5]==1]
print("\n===== 当前 is_pet=1 化药总数:", len(no_explicit_pet1), " (其中行内明示物种者见上, 其余物种为推断/缺失) =====")
