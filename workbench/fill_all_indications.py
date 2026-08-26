#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_all_indications.py — 为 drugs 表中全部注册审批记录补充适应症(indication)。

覆盖策略（按优先级）：
  1. 已有适应症且非空 -> 保留（如已有 indication_src 则保留，否则标为 ref）。
  2. 诊断制品/疫苗 -> 从药名推导（derived）。
  3. 化药/中药 -> 匹配 indication_online.json + indication_extra.json 成分映射（online）。
  4. 仍为空 -> 按药品类型生成通用参考描述（inferred）。

运行后重写生成 web/index.html。
"""
import sqlite3
import os
import json
import re
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "drugs.db")
ONLINE_JSON = os.path.join(HERE, "indication_online.json")
EXTRA_JSON = os.path.join(HERE, "indication_extra.json")
sys.path.insert(0, HERE)
import build_web as bw


def load_maps():
    online = json.load(open(ONLINE_JSON, encoding="utf-8")) if os.path.exists(ONLINE_JSON) else {}
    extra = json.load(open(EXTRA_JSON, encoding="utf-8")) if os.path.exists(EXTRA_JSON) else {}
    merged = {}
    for d in (online, extra):
        for k, v in d.items():
            if k.startswith("_"):
                continue
            merged[k] = v
    return merged


def classify_kind(name):
    n = name or ""
    if any(k in n for k in ["试纸条", "检测", "试剂盒", "ELISA", "PCR", "胶体金", "诊断", "抗体检测"]):
        return "diag"
    if any(k in n for k in ["疫苗", "亚单位", "灭活", "活疫苗", "重组", "基因工程", "瘤苗",
                            "抗血清", "免疫球蛋白", "卵黄抗体", "病毒样", "mRNA"]):
        return "vaccine"
    return "thera"


def derive_indication(name, kind):
    """对诊断试剂/疫苗，从药名推导适应症。"""
    n = name or ""
    if kind == "diag":
        body = n
        for sfx in ["胶体金检测试纸条", "检测试纸条", "ELISA抗体检测试剂盒", "抗体检测试剂盒",
                    "荧光定量PCR检测试剂盒", "检测试剂盒", "试纸条", "试剂盒", "抗体检测",
                    "ELISA Kit", "Detection Kit", "Real-time PCR"]:
            body = re.sub(re.escape(sfx) + r"$", "", body)
            body = body.replace(sfx, "")
        body = re.sub(r"[A-Za-z\s,/()]+$", "", body).rstrip(" ")
        return "用于检测" + body if body else "用于相关病原/抗体检测（诊断制品）"
    if kind == "vaccine":
        cut = n.find("疫苗")
        body = n[:cut] if cut > 0 else n
        body = re.sub(r"(四联活|三联活|二联活|二价灭活|三价灭活|二价|三联|四联|二联|灭活|活)$", "", body)
        body = re.sub(r"[A-Za-z\s,/()]+$", "", body).rstrip("、- ")
        return "用于预防" + body if body else "用于相关疫病预防（疫苗）"
    return ""


def match_therapeutic(name, ind_map):
    """对化药/治疗药，按成分关键词匹配适应症。取最长匹配键，避免短键覆盖长键。"""
    hits = [k for k in ind_map if k in name]
    hits = [k for k in hits if not any(k != k2 and k in k2 for k2 in hits)]
    if not hits:
        return ""
    inds = []
    for k in hits:
        if ind_map[k] not in inds:
            inds.append(ind_map[k])
    return "；".join(inds)


def fallback_indication(drug_type, name):
    """无法匹配时的兜底描述。"""
    if drug_type == "诊断制品":
        return "用于病原/抗体检测（诊断制品）"
    if drug_type == "生物制品":
        return "用于相关疫病预防或免疫治疗（生物制品）"
    if drug_type == "化药":
        return "用于相关疾病的治疗或预防（化药）"
    return "用于相关适应症的辅助治疗"


def fill(stats_only=False):
    ind_map = load_maps()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "SELECT id, drug_name, drug_type, indication, indication_src FROM drugs"
    ))
    c_online = c_derived = c_inferred = c_preserved = c_empty = 0
    updates = []
    for r in rows:
        rid = r["id"]
        name = r["drug_name"] or ""
        dtype = r["drug_type"] or ""
        existing = (r["indication"] or "").strip()
        src = (r["indication_src"] or "").strip()

        kind = classify_kind(name)

        # 若已有值且非 derived 来源，保留不动；derived 来源可重新推导以利用改进逻辑
        if existing and src not in ("", "derived"):
            c_preserved += 1
            continue
        if existing and not src:
            updates.append((existing, "ref", rid))
            c_preserved += 1
            continue

        ind, new_src = "", ""
        if kind in ("diag", "vaccine"):
            ind = derive_indication(name, kind)
            new_src = "derived"
            c_derived += 1
        else:
            ind = match_therapeutic(name, ind_map)
            if ind:
                new_src = "online"
                c_online += 1
            else:
                ind = fallback_indication(dtype, name)
                new_src = "inferred"
                c_inferred += 1

        if not ind:
            c_empty += 1
            continue
        updates.append((ind, new_src, rid))

    if not stats_only:
        con.executemany(
            "UPDATE drugs SET indication=?, indication_src=? WHERE id=?",
            updates
        )
        con.commit()
    con.close()

    total = len(rows)
    print(f"总记录: {total}")
    print(f"  保留已有: {c_preserved}")
    print(f"  联网/映射(online): {c_online}")
    print(f"  药名推导(derived): {c_derived}")
    print(f"  兜底推断(inferred): {c_inferred}")
    print(f"  仍为空(empty): {c_empty}")
    return {
        "total": total,
        "preserved": c_preserved,
        "online": c_online,
        "derived": c_derived,
        "inferred": c_inferred,
        "empty": c_empty,
    }


def rebuild_web():
    reg = bw.load_registration()
    print(f"[rebuild] 注册审批 {len(reg)} 条")
    # clinical_approval 通过 bw 的 DB 读取
    import init_clinical, ingest_clinical  # ensure tables exist and supplements loaded
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    clin_rows = con.execute(
        """SELECT reg_type, drug_name, org, species, indication, approval_no,
                  accept_no, approve_date, status, is_pet, source_name,
                  source_url, note, updated_at
           FROM clinical_approval ORDER BY approve_date DESC, id DESC"""
    ).fetchall()
    log_rows = con.execute(
        "SELECT ts, domain, source, note, added, total FROM update_log ORDER BY id DESC"
    ).fetchall()
    con.close()

    clin = []
    for r in clin_rows:
        rt = r["reg_type"] or "domestic"
        clin.append({
            "regType": bw.CLIN_REG_MAP.get(rt, rt),
            "drugName": r["drug_name"] or "",
            "org": r["org"] or "",
            "species": r["species"] or "",
            "indication": r["indication"] or "",
            "approvalNo": r["approval_no"] or "",
            "acceptNo": r["accept_no"] or "",
            "approveDate": r["approve_date"] or "",
            "status": r["status"] or "",
            "isPet": int(r["is_pet"] or 0),
            "sourceName": r["source_name"] or "",
            "sourceUrl": r["source_url"] or "",
            "note": r["note"] or "",
            "updatedAt": r["updated_at"] or "",
        })
    logs = []
    for r in log_rows:
        logs.append({
            "ts": r["ts"] or "",
            "domain": r["domain"] or "",
            "source": r["source"] or "",
            "note": r["note"] or "",
            "added": r["added"] if r["added"] is not None else 0,
            "total": r["total"] if r["total"] is not None else 0,
        })
    bw.build_html(reg, clin, logs)
    print(f"[rebuild] 已生成 {bw.OUT}")


if __name__ == "__main__":
    stats_only = "--stats" in sys.argv
    fill(stats_only=stats_only)
    if not stats_only:
        rebuild_web()
        print("\n提示：如需重新部署网页，请运行 workbuddy_cloudstudio_deploy 部署 workbench/web 目录。")
