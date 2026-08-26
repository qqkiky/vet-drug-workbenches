# -*- coding: utf-8 -*-
"""Pass A: 逐行扫描缓存公告页，对每个化药记录检查其所在表格行(含备注/监测期)是否明示犬/猫/宠物/伴侣。
恢复 is_pet=0 但行内明示物种的记录，并提取物种。"""
import os, re, sqlite3
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(ROOT, "pages")
DB = os.path.join(ROOT, "drugs.db")
PET_KW = ["犬", "猫", "宠物", "伴侣"]

con = sqlite3.connect(DB)
recs = con.execute(
    "SELECT id,ann_num,drug_name,table_type,drug_type,is_pet,remark,monitor_period,source_url "
    "FROM drugs WHERE drug_type='化药'").fetchall()

def page_for(url):
    m = re.search(r"(\d{6}/t\d+_\d+\.htm)", url or "")
    if m:
        return os.path.join(PAGES, "._" + m.group(1).replace("/", "_"))
    return None

def species_in(text):
    sp = set()
    if "犬" in text: sp.add("犬")
    if "猫" in text: sp.add("猫")
    if "宠物" in text or "伴侣" in text: sp.add("宠物")
    return sp

explicit_recovered = []   # is_pet=0 but row明示物种
explicit_already = []     # is_pet=1 and row明示物种 (sanity)
no_page = 0
for r in recs:
    rid, ann, name, ttype, dtype, ispet, remark, mon, url = r
    pf = page_for(url)
    if not pf or not os.path.exists(pf):
        no_page += 1
        continue
    html = open(pf, encoding="utf-8", errors="ignore").read()
    soup = BeautifulSoup(html, "html.parser")
    hit = None
    for t in soup.find_all("table"):
        for tr in t.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            first = cells[0]
            if name and (name == first or name in first or first in name) and len(first) >= 2:
                rowtext = " ".join(cells)
                sp = species_in(rowtext)
                if sp:
                    hit = (sp, rowtext)
                    break
        if hit:
            break
    if hit:
        sp, rowtext = hit
        entry = (rid, ann, name, "".join(sorted(sp)), ispet, rowtext[:60])
        if ispet == 0:
            explicit_recovered.append(entry)
        else:
            explicit_already.append(entry)

print("化药记录总数:", len(recs))
print("无缓存页:", no_page)
print("== 行内明示物种 且 当前 is_pet=0 (应恢复):", len(explicit_recovered))
for e in explicit_recovered:
    print("  ", e)
print("== 行内明示物种 且 当前 is_pet=1 (已正确):", len(explicit_already))
