#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_vdts_clinical.py — 从国家兽药基础数据库(vdts.ivdc.org.cn)抓取临床试验审批数据并写入本地库。

数据来源：http://vdts.ivdc.org.cn:8099/cx/#/  -> API http://vdts.ivdc.org.cn:8099/api/api/cx/h5/lcsysp/list
该库数据更新截止日期 2026-07-09，本脚本抓取全部 934 条历史临床审批记录。

写入表：clinical_approval
更新表：update_log
"""
import sqlite3
import os
import json
import re
import datetime
import requests
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "drugs.db")
JSON_PATH = os.path.join(HERE, "vdts_lcsysp_20260709.json")
VDTS_URL = "http://vdts.ivdc.org.cn:8099/cx/#/"
API_URL = "http://vdts.ivdc.org.cn:8099/api/api/cx/h5/lcsysp/list"

ANIMALS = [
    "猫", "犬", "狗", "鸡", "鸭", "鹅", "猪", "牛", "羊", "马", "兔", "鼠", "狐", "貉", "貂",
    "鸽", "鱼", "龟", "鸟", "蛇", "蜥蜴", "宠", "鹿", "骆驼", "骡", "驴", "鹌鹑", "雉",
    "鹧鸪", "鸵鸟", "牛蛙", "蜜蜂", "蚕", "参", "虾", "蟹", "贝", "水貂", "毛皮动物",
    "毛皮", "经济动物", "宠物", "禽",
]
ANIMALS.sort(key=len, reverse=True)

DRUG_PREFIXES = [
    "转移因子", "干扰素", "白细胞介素", "抗菌肽", "益生菌", "酶", "维生素", "矿物质", "氨基酸",
    "中草药", "中药", "植物提取物", "卵黄抗体", "抗血清", "血清", "毒素", "类毒素", "抗原",
    "单抗", "抗体", "核酸", "mRNA", "DNA", "重组", "亚单位", "基因工程", "载体", "灭活", "活",
    "多价", "二价", "三联", "二联", "多联", "单价",
]

DISEASE_ANIMAL = {
    "非洲猪瘟": "猪",
    "猪": "猪",
    "禽流感": "禽",
    "新城疫": "禽",
    "传染性支气管炎": "鸡",
    "传染性法氏囊": "鸡",
    "马立克": "鸡",
    "禽腺病毒": "禽",
    "病毒性关节炎": "鸡",
    "禽白血病": "禽",
    "禽呼肠孤": "禽",
    "禽痘": "禽",
    "禽脑脊髓炎": "禽",
    "狂犬病": "犬、猫",
    "犬": "犬",
    "猫": "猫",
    "兔": "兔",
    "布鲁氏菌": "牛、羊",
    "布氏菌病": "牛、羊",
    "棘球蚴": "牛、羊",
    "口蹄疫": "牛、猪、羊",
    "牛": "牛",
    "羊": "羊",
    "小反刍兽疫": "羊",
    "蓝舌病": "牛、羊",
    "山羊痘": "山羊",
    "绵羊痘": "绵羊",
    "羊痘": "羊",
    "牛结节性皮肤病": "牛",
    "牛病毒性腹泻": "牛",
    "牛传染性鼻气管炎": "牛",
    "赤羽病": "牛",
    "羊棘球蚴": "羊",
    "羊支原体": "羊",
    "鸭": "鸭",
    "鹅": "鹅",
    "水禽": "鸭、鹅",
    "鲤": "鱼",
    "草鱼": "鱼",
    "鲫鱼": "鱼",
    "大口黑鲈": "鱼",
    "大菱鲆": "鱼",
    "鲈鱼": "鱼",
    "鲑": "鱼",
    "鳟": "鱼",
    "石斑鱼": "鱼",
    "对虾": "虾",
    "虾": "虾",
    "蜜蜂": "蜜蜂",
    "蚕": "蚕",
    "鹿": "鹿",
    "狐狸": "狐",
    "貉": "貉",
    "貂": "貂",
    "水貂": "水貂",
    "毛皮动物": "毛皮动物",
    "宠物": "宠物",
    "格拉瑟病": "猪",
    "鸽": "鸽",
    "副黏病毒": "鸽",
    "动物A型流感": "动物",
}


def parse_species_indication(xmmc: str):
    """从项目名称(xmmc)解析靶动物与适应症（疾病/用途）。"""
    xmmc = xmmc.strip()
    s = re.sub(r"临床试验\s*$", "", xmmc)
    s = re.sub(r"[（(][^）)]+[）)]", "", s)

    # 1) 提取开头的动物序列
    species_parts = []
    rest = s
    pattern = "^(" + "|".join(re.escape(a) for a in ANIMALS) + r")([、，，]|\s*)"
    while True:
        m = re.match(pattern, rest)
        if not m:
            break
        species_parts.append(m.group(1))
        rest = rest[m.end():]
    if species_parts:
        species = "、".join(species_parts)
    else:
        # 2) 按疾病关键词推断动物
        species = ""
        for dis, anim in DISEASE_ANIMAL.items():
            if dis in s:
                species = anim
                break
        if not species:
            if "禽" in s:
                species = "禽"
            elif any(k in s for k in ("鲤", "草鱼", "鲫鱼", "大口黑鲈", "大菱鲆", "鲈鱼", "鲑", "鳟", "石斑鱼")):
                species = "鱼"
            elif "对虾" in s or "虾" in s:
                species = "虾"
        rest = s

    # 3) 适应症：去掉制剂/疫苗类型前缀与后缀
    ind = rest
    prefix_pattern = "^(" + "|".join(re.escape(p) for p in DRUG_PREFIXES) + r"|疫苗|药物|试剂|制品|注射液|口服液|粉|散|片|颗粒|溶液|胶囊|锭剂|软膏|栓剂|预混剂|饲料添加剂|消毒剂|杀虫剂|杀寄生虫药|诊断|试纸条|试剂盒|ELISA|PCR|荧光|检测|芯片|试条|试卡)+"
    ind = re.sub(prefix_pattern, "", ind)
    ind = re.sub(r"(疫苗|药物|试剂|制品|注射液|口服液|粉|散|片|颗粒|溶液|胶囊|锭剂|软膏|栓剂|预混剂|饲料添加剂|消毒剂|杀虫剂|杀寄生虫药)$", "", ind)
    ind = ind.strip("、，， ")
    return species, ind


def is_pet(species: str, drug_name: str) -> int:
    """根据靶动物或药名判断是否宠物相关。"""
    text = (species or "") + (drug_name or "")
    LIVESTOCK = ("猪","牛","羊","禽","鸡","鸭","鹅","马","鱼","虾","蟹","水产","经济动物","毛皮","水貂","狐","貉")
    if any(k in text for k in LIVESTOCK):
        return 0
    return 1 if any(k in text for k in ("猫", "犬", "狗", "宠", "兔")) else 0
    return 1 if any(k in text for k in ("猫", "犬", "狗", "宠", "兔")) else 0


def fetch_all():
    """从 vdts API 分页抓取全部临床审批记录。"""
    if os.path.exists(JSON_PATH):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(JSON_PATH))
        age = datetime.datetime.now() - mtime
        if age.total_seconds() < 3600 * 24:
            print(f"[fetch] 使用缓存 {JSON_PATH}（{(age.total_seconds()/60):.0f} 分钟前抓取）")
            return json.load(open(JSON_PATH, encoding="utf-8"))

    all_rows = []
    page = 1
    rows_per_page = 100
    while True:
        payload = {"page": page, "rows": rows_per_page, "conditionItems": []}
        r = requests.post(API_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        total = data.get("records", 0)
        rows = data.get("rows", [])
        print(f"[fetch] page {page}: {len(rows)} rows, total {total}")
        if not rows:
            break
        all_rows.extend(rows)
        if len(all_rows) >= total:
            break
        page += 1
        time.sleep(0.3)

    out = {"records": len(all_rows), "rows": all_rows, "fetched_at": datetime.datetime.now().isoformat()}
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def import_to_db(data):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = data.get("rows", [])
    added = 0
    skipped = 0
    for r in rows:
        xmmc = (r.get("xmmc") or "").strip()
        species, indication = parse_species_indication(xmmc)
        approval_no = (r.get("pjh") or "").strip()
        org = (r.get("sqdwmc") or "").strip()
        if not approval_no or not org:
            skipped += 1
            continue
        exists = c.execute(
            "SELECT 1 FROM clinical_approval WHERE approval_no=? AND org=?",
            (approval_no, org),
        ).fetchone()
        if exists:
            skipped += 1
            continue
        approve_date = r.get("shrq") or ""
        if approve_date:
            # 2026/07/09 -> 2026-07-09
            approve_date = approve_date.replace("/", "-")
        c.execute(
            """INSERT INTO clinical_approval
               (reg_type,drug_name,org,species,indication,approval_no,accept_no,
                approve_date,status,is_pet,source_name,source_url,note,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "domestic",
                xmmc,
                org,
                species,
                indication,
                approval_no,
                (r.get("slh") or "").strip(),
                approve_date,
                "同意临床试验",
                is_pet(species, xmmc),
                "国家兽药基础数据库",
                VDTS_URL,
                f"数据截止日期：2026-07-09；有效期限：{r.get('yxqx') or ''}",
                datetime.date.today().isoformat(),
            ),
        )
        added += 1
    c.commit()
    total = c.execute("SELECT COUNT(*) FROM clinical_approval").fetchone()[0]
    c.execute(
        """INSERT INTO update_log (ts,domain,source,note,added,total)
           VALUES (?,?,?,?,?,?)""",
        (
            datetime.date.today().isoformat(),
            "clinical",
            "vdts",
            f"从国家兽药基础数据库 {VDTS_URL} 全量导入临床试验审批数据（数据更新截止 2026-07-09），原始记录 {len(rows)} 条。",
            added,
            total,
        ),
    )
    c.commit()
    c.close()
    print(f"[import] 新增 {added} 条，跳过/重复 {skipped} 条，clinical_approval 累计 {total} 条")


if __name__ == "__main__":
    data = fetch_all()
    import_to_db(data)
