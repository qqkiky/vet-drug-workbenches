#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_web.py — 生成「兽药注册与审批数据查询工作台」自包含静态网页。
输出: workbench/web/index.html  (数据内嵌 JSON, 纯前端, 无需后端)

两大域:
  1) 注册审批  (drugs 表: 农业农村部公告 国产/进口兽药注册审批目录)
  2) 临床审批  (clinical_approval 表: 兽药临床试验审批, 主数据源 vdts.ivdc.org.cn,
               官方未及时更新时由企业新闻补充, 见 update_log 更新动态)

特性:
  - 查询类型: 国产新兽药注册 / 进口新兽药注册
  - 点击「搜索」按钮 -> 页面实时展示结果 (无需导出 CSV)
  - 临床审批域展示「更新动态」与「来源说明」
部署: workbuddy_cloudstudio_deploy 部署 workbench/web 目录。
"""
import sqlite3
import json
import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "drugs.db")
OUT_DIR = os.path.join(HERE, "web")
OUT = os.path.join(OUT_DIR, "index.html")

# ---- PWA：移动端可安装 + 与 PC 端同源同步 ----
# PC 与移动端共用同一份 web/index.html（数据内嵌）。移动端通过 manifest + service
# worker 可“添加到主屏幕”，并与 PC 共享同一部署地址；任一端（后台重建+部署）更新后，
# 已打开的页面通过 version.json 轮询与 SW 更新检测自动刷新，保证两端实时一致。
PWA_INLINE_JS = r'''
<script>
(function(){
  var BUILD="__BUILD__";
  function checkVersion(){
    fetch('version.json?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){
      if(j&&j.build&&j.build!==BUILD){ window.location.reload(); }
    }).catch(function(){});
  }
  setInterval(checkVersion, 60000);
  document.addEventListener('visibilitychange', function(){ if(!document.hidden) checkVersion(); });
  if('serviceWorker' in navigator){
    window.addEventListener('load', function(){
      navigator.serviceWorker.register('sw.js').then(function(reg){
        function up(){ try{reg.update();}catch(e){} }
        setInterval(up, 60000);
        document.addEventListener('visibilitychange', function(){ if(!document.hidden) up(); });
        reg.addEventListener('updatefound', function(){
          var nw=reg.installing; if(!nw) return;
          nw.addEventListener('statechange', function(){
            if(nw.state==='installed' && navigator.serviceWorker.controller){ window.location.reload(); }
          });
        });
      }).catch(function(){});
    });
    navigator.serviceWorker.addEventListener('controllerchange', function(){ window.location.reload(); });
  }
})();
</script>
'''

PWA_MANIFEST = '''{
  "name": "兽药注册与审批数据查询工作台",
  "short_name": "兽药工作台",
  "description": "宠物药/兽药注册审批与临床审批数据查询工作台（PC 与移动端同源同步）",
  "lang": "zh-CN",
  "start_url": ".",
  "scope": ".",
  "display": "standalone",
  "display_override": ["standalone", "minimal-ui"],
  "background_color": "#1b5fa8",
  "theme_color": "#1b5fa8",
  "orientation": "portrait-primary",
  "icons": [
    {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
    {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
  ]
}'''

PWA_SW = r'''
const BUILD = "__BUILD__";
const SHELL = ['index.html','manifest.json','icon-192.png','icon-512.png','version.json'];
const CACHE = 'wb-shell-' + BUILD;
self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(SHELL);}).catch(function(){}));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){return k!==CACHE;}).map(function(k){return caches.delete(k);}));
  }).then(function(){return self.clients.claim();}));
});
self.addEventListener('fetch', function(e){
  var req = e.request;
  if(req.method !== 'GET') return;
  var url = new URL(req.url);
  if(url.pathname.endsWith('version.json')){
    e.respondWith(fetch(req, {cache:'no-store'}).catch(function(){return caches.match(req);}));
    return;
  }
  if(req.mode === 'navigate'){
    e.respondWith(fetch(req).then(function(res){
      var cp = res.clone(); caches.open(CACHE).then(function(c){c.put(req, cp);});
      return res;
    }).catch(function(){return caches.match(req).then(function(r){return r || caches.match('index.html');});}));
    return;
  }
  e.respondWith(caches.match(req).then(function(r){
    return r || fetch(req).then(function(res){
      var cp = res.clone(); caches.open(CACHE).then(function(c){c.put(req, cp);});
      return res;
    }).catch(function(){return r;});
  }));
});
'''

def ensure_icons():
    """生成 PWA 图标（若缺失）。蓝底白十字，简洁 recognizable。"""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    for size in (192, 512):
        p = os.path.join(OUT_DIR, "icon-%d.png" % size)
        if os.path.exists(p):
            continue
        img = Image.new("RGBA", (size, size), (27, 95, 168, 255))
        d = ImageDraw.Draw(img)
        m = size // 2
        t = max(8, size // 7)
        L = size // 2 - size // 4
        d.rectangle([m - t // 2, m - L, m + t // 2, m + L], fill=(255, 255, 255, 255))
        d.rectangle([m - L, m - t // 2, m + L, m + t // 2], fill=(255, 255, 255, 255))
        img.save(p)

def write_pwa_assets(build_id, gen_date):
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(PWA_MANIFEST)
    with open(os.path.join(OUT_DIR, "sw.js"), "w", encoding="utf-8") as f:
        f.write(PWA_SW.replace("__BUILD__", build_id))
    with open(os.path.join(OUT_DIR, "version.json"), "w", encoding="utf-8") as f:
        f.write('{"build":"%s","generated":"%s"}' % (build_id, gen_date))
    ensure_icons()

VDTS_URL = "http://vdts.ivdc.org.cn:8099/cx/#/"

REG_TYPE_MAP = {
    "new_drug": "国产新兽药注册",
    "import_drug": "进口新兽药注册",
    "change": "变更注册",
}
CLIN_REG_MAP = {
    "domestic": "国产新兽药注册",
    "import": "进口新兽药注册",
}


def load_registration():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        """SELECT ann_num, ann_date, ann_title, table_type, drug_type, drug_name,
                  org, country, cert_no, category, change_item, indication,
                  is_pet, source_url
           FROM drugs ORDER BY ann_date DESC, ann_num DESC, id DESC"""
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        tt = r["table_type"] or ""
        reg = REG_TYPE_MAP.get(tt, tt)
        country = (r["country"] or "").strip()
        if not country:
            country = "中国" if tt != "import_drug" else "进口"
        out.append({
            "annNum": r["ann_num"] or "",
            "annDate": r["ann_date"] or "",
            "annTitle": r["ann_title"] or "",
            "regType": reg,                 # 新兽药注册 / 进口注册 / 变更注册
            "drugType": r["drug_type"] or "",
            "drugName": r["drug_name"] or "",
            "org": r["org"] or "",
            "country": country,
            "certNo": r["cert_no"] or "",
            "category": r["category"] or "",
            "changeItem": r["change_item"] or "",
            "indication": r["indication"] or "",
            "isPet": int(r["is_pet"] or 0),
            "sourceUrl": r["source_url"] or "",
        })
    return out


def load_clinical():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        """SELECT reg_type, drug_name, org, species, indication, approval_no,
                  accept_no, approve_date, status, is_pet, source_name,
                  source_url, note, updated_at
           FROM clinical_approval ORDER BY approve_date DESC, id DESC"""
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        rt = r["reg_type"] or "domestic"
        out.append({
            "regType": CLIN_REG_MAP.get(rt, rt),   # 国产新兽药注册 / 进口新兽药注册
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
    return out


def load_update_log():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT ts, domain, source, note, added, total FROM update_log "
        "ORDER BY id DESC"
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        out.append({
            "ts": r["ts"] or "",
            "domain": r["domain"] or "",
            "source": r["source"] or "",
            "note": r["note"] or "",
            "added": r["added"] if r["added"] is not None else 0,
            "total": r["total"] if r["total"] is not None else 0,
        })
    return out


def build_html(reg, clin, logs):
    reg_json = json.dumps(reg, ensure_ascii=False).replace("</", "<\\/")
    clin_json = json.dumps(clin, ensure_ascii=False).replace("</", "<\\/")
    log_json = json.dumps(logs, ensure_ascii=False).replace("</", "<\\/")
    gen_date = datetime.date.today().isoformat()
    build_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    reg_total = len(reg)
    reg_dom = sum(1 for x in reg if x["regType"] == "国产新兽药注册")
    reg_imp = sum(1 for x in reg if x["regType"] == "进口新兽药注册")
    reg_pet = sum(1 for x in reg if x["isPet"] == 1)
    clin_total = len(clin)
    clin_dom = sum(1 for x in clin if x["regType"] == "国产新兽药注册")
    clin_pet = sum(1 for x in clin if x["isPet"] == 1)

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>兽药注册与审批数据查询工作台</title>
  <link rel="manifest" href="manifest.json">
  <meta name="theme-color" content="#1b5fa8">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="mobile-web-app-capable" content="yes">
  <link rel="apple-touch-icon" href="icon-192.png">
  <link rel="icon" href="icon-192.png">
<style>
  :root{
    --bg:#f5f7fa; --card:#ffffff; --ink:#1f2933; --muted:#6b7280;
    --line:#e5e7eb; --brand:#1b5fa8; --brand2:#2d7dd2;
    --chip:#eef6ff; --pet:#fff4e5; --petink:#b45309;
    --tab:#e8eef6; --tabon:#1b5fa8;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
       background:var(--bg);color:var(--ink);font-size:14px;line-height:1.5}
  header{background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;padding:16px 16px 14px}
  header h1{margin:0;font-size:19px;font-weight:700}
  header .sub{margin-top:4px;font-size:12px;opacity:.9}
  .stats{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
  .stat{flex:1;min-width:72px;background:rgba(255,255,255,.15);border-radius:10px;padding:8px 6px;text-align:center}
  .stat b{display:block;font-size:18px}
  .stat span{font-size:11px;opacity:.92}
  .wrap{padding:14px 12px 40px;max-width:1180px;margin:0 auto}
  .tabs{display:flex;gap:8px;margin-bottom:12px}
  .tab{flex:1;text-align:center;padding:11px 8px;border-radius:11px;background:var(--tab);
       color:var(--brand);font-weight:600;cursor:pointer;border:1px solid var(--line);font-size:14px}
  .tab.active{background:var(--tabon);color:#fff;border-color:var(--tabon)}
  .panel{display:none}
  .panel.active{display:block}
  .filters{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;
           position:sticky;top:0;z-index:5;box-shadow:0 2px 8px rgba(0,0,0,.04)}
  .frow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
  select,input[type=text]{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:9px;
       background:#fff;color:var(--ink);min-width:120px}
  input[type=text]{flex:1;min-width:160px}
  label.pet{display:inline-flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;
            background:var(--pet);color:var(--petink);padding:7px 10px;border-radius:9px;border:1px solid #fcd9a8}
  .btn{font:inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--brand);cursor:pointer}
  .btn.primary{background:var(--brand);color:#fff;border-color:var(--brand)}
  .btn.ghost{background:#f3f6fa}
  .count{font-size:13px;color:var(--muted);margin:12px 2px}
  .tablecard{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
  .scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:13px;min-width:780px}
  th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
  th{background:#f0f4f8;color:var(--muted);font-weight:600;position:sticky;top:0;white-space:nowrap}
  tbody tr:hover{background:#f8fbff}
  .src a{color:var(--brand);text-decoration:none;border-bottom:1px solid var(--brand2)}
  .clin-row{cursor:pointer}
  .clin-row:hover{background:#eef6ff}
  .tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;background:var(--chip);color:var(--brand);white-space:nowrap}
  .tag.chg{background:#fdeef0;color:#b91c1c}
  .tag.imp{background:#eafaf1;color:#047857}
  .tag.pet{background:var(--pet);color:var(--petink)}
  .tag.dom{background:#eef6ff;color:#1b5fa8}
  .tag.ok{background:#eafaf1;color:#047857}
  .pager{display:flex;gap:10px;align-items:center;justify-content:center;margin-top:14px}
  .foot{text-align:center;color:var(--muted);font-size:12px;margin-top:18px}
  /* 临床审批专属 */
  .note-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin-bottom:12px}
  .note-card h3{margin:0 0 8px;font-size:14px;color:var(--brand)}
  .note-card p{margin:6px 0;font-size:13px;color:var(--ink)}
  .note-card .src{color:var(--brand);word-break:break-all}
  .log{list-style:none;margin:0;padding:0}
  .log li{border-left:3px solid var(--brand2);padding:6px 0 6px 12px;margin-bottom:8px;background:#f8fbff;border-radius:0 8px 8px 0}
  .log .ts{font-weight:600;color:var(--brand)}
  .log .meta{font-size:11px;color:var(--muted)}
  .badge{display:inline-block;font-size:11px;padding:0 6px;border-radius:6px;background:var(--chip);color:var(--brand);margin-left:4px}
  @media(max-width:640px){
    header{padding:12px 12px 10px}
    header h1{font-size:17px}
    .stats{gap:6px}
    .stat{min-width:0;flex:1 1 28%;padding:7px 4px}
    .stat b{font-size:15px}
    .stat span{font-size:10px}
    .wrap{padding:10px 8px 32px}
    .tabs{gap:6px}
    .tab{padding:10px 6px;font-size:13px}
    .filters{padding:10px;position:static;top:auto}
    .frow{gap:6px}
    select,input[type=text]{min-width:0;flex:1 1 100%}
    .btn,.tab{flex:1 1 auto}
    .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
    table{min-width:680px}
    th,td{padding:8px 8px}
    .foot{font-size:11px}
  }
  @media(max-width:560px){
    #panelReg table th:nth-child(1),#panelReg table td:nth-child(1),
    #panelReg table th:nth-child(8),#panelReg table td:nth-child(8),
    #panelReg table th:nth-child(9),#panelReg table td:nth-child(9),
    #panelReg table th:nth-child(10),#panelReg table td:nth-child(10){display:none}
    #panelClin table th:nth-child(1),#panelClin table td:nth-child(1),
    #panelClin table th:nth-child(8),#panelClin table td:nth-child(8),
    #panelClin table th:nth-child(9),#panelClin table td:nth-child(9),
    #panelClin table th:nth-child(10),#panelClin table td:nth-child(10){display:none}
    .stat{flex:1 1 45%}
  }
</style>
</head>
<body>
<header>
  <h1>兽药注册与审批数据查询工作台</h1>
  <div class="sub">注册审批（农业农村部公告）· 临床审批（兽药临床试验批件）</div>
  <div class="stats">
    <div class="stat"><b>__REG_TOTAL__</b><span>注册审批总记录</span></div>
    <div class="stat"><b>__REG_DOM__</b><span>国产新兽药</span></div>
    <div class="stat"><b>__REG_IMP__</b><span>进口注册</span></div>
    <div class="stat"><b>__REG_PET__</b><span>宠物相关</span></div>
    <div class="stat"><b>__CLIN_TOTAL__</b><span>临床审批记录</span></div>
  </div>
</header>
<div class="wrap">
  <div class="tabs">
    <div class="tab active" data-tab="reg" id="tabReg">注册审批查询</div>
    <div class="tab" data-tab="clin" id="tabClin">临床审批动态</div>
  </div>

  <!-- ============ 注册审批 ============ -->
  <div class="panel active" id="panelReg">
    <div class="filters">
      <div class="frow">
        <select id="regType">
          <option value="">全部查询类型</option>
          <option value="国产新兽药注册">国产新兽药注册</option>
          <option value="进口新兽药注册">进口新兽药注册</option>
          <option value="变更注册">变更注册</option>
        </select>
        <select id="regDrug">
          <option value="">全部药品类型</option>
          <option value="化药">化药</option>
          <option value="生物制品">生物制品</option>
          <option value="诊断制品">诊断制品</option>
        </select>
        <select id="regYear"><option value="">全部年份</option></select>
        <label class="pet"><input type="checkbox" id="regPet"> 仅宠物用药</label>
      </div>
      <div class="frow">
        <input type="text" id="regQ" placeholder="搜索：药品名称 / 企业 / 公告号 / 证书号">
        <button class="btn primary" id="regSearch">搜索</button>
        <button class="btn ghost" id="regExp">导出 CSV</button>
      </div>
    </div>
    <div class="count" id="regCount"></div>
    <div class="tablecard"><div class="scroll">
      <table>
        <thead><tr>
          <th>公告号</th><th>公告日期</th><th>注册类型</th><th>药品类型</th>
          <th>药品名称</th><th>生产企业</th><th>适应症</th><th>国别</th><th>证书号</th><th>来源</th>
        </tr></thead>
        <tbody id="regBody"></tbody>
      </table>
    </div></div>
    <div class="pager">
      <button class="btn" id="regPrev">上一页</button>
      <span id="regPage" class="count" style="margin:0"></span>
      <button class="btn" id="regNext">下一页</button>
    </div>
  </div>

  <!-- ============ 临床审批 ============ -->
  <div class="panel" id="panelClin">
    <div class="note-card">
      <h3>来源说明</h3>
      <p><b>主数据源：</b><span class="src">__VDTS__</span>（中国兽医药品监察所 兽药注册审批查询系统）</p>
      <p><b>补充机制：</b>当主管网站数据未及时更新时，从各企业公告 / 公开新闻中补充核查，并将新增记录写入本地数据库，同时在下方「更新动态」中标注来源与日期。</p>
      <p>当前共 <b>__CLIN_TOTAL__</b> 条临床审批记录，其中国产新兽药注册临床 <b>__CLIN_DOM__</b> 条、宠物相关 <b>__CLIN_PET__</b> 条。</p>
    </div>
    <div class="filters">
      <div class="frow">
        <select id="clinType">
          <option value="">全部查询类型</option>
          <option value="国产新兽药注册">国产新兽药注册</option>
          <option value="进口新兽药注册">进口新兽药注册</option>
        </select>
        <select id="clinYear"><option value="">全部年份</option></select>
        <label class="pet"><input type="checkbox" id="clinPet"> 仅宠物用药</label>
      </div>
      <div class="frow">
        <input type="text" id="clinQ" placeholder="搜索：药品名称 / 企业 / 批件号 / 适应症">
        <button class="btn primary" id="clinSearch">搜索</button>
        <button class="btn ghost" id="clinExp">导出 CSV</button>
      </div>
    </div>
    <div class="count" id="clinCount"></div>
    <div class="tablecard"><div class="scroll">
      <table>
        <thead><tr>
          <th>审批类型</th><th>药品名称</th><th>申请/生产企业</th><th>靶动物</th>
          <th>适应症</th><th>临床批件号</th><th>受理号</th><th>批准日期</th><th>结论</th><th>来源</th>
        </tr></thead>
        <tbody id="clinBody"></tbody>
      </table>
    </div></div>
    <div class="pager">
      <button class="btn" id="clinPrev">上一页</button>
      <span id="clinPage" class="count" style="margin:0"></span>
      <button class="btn" id="clinNext">下一页</button>
    </div>

    <div class="note-card" style="margin-top:16px">
      <h3>更新动态</h3>
      <ul class="log" id="logList"></ul>
    </div>
  </div>

  <div class="foot">静态快照 · 生成日期 __DATE__ · 注册数据来源：中国兽药信息网 / 农业农村部公告；临床数据主源：中国兽医药品监察所 vdts.ivdc.org.cn</div>
</div>

<script id="payloadReg" type="application/json">__REG__</script>
<script id="payloadClin" type="application/json">__CLIN__</script>
<script id="payloadLog" type="application/json">__LOG__</script>
<script>
const REG = JSON.parse(document.getElementById('payloadReg').textContent);
const CLIN = JSON.parse(document.getElementById('payloadClin').textContent);
const LOG = JSON.parse(document.getElementById('payloadLog').textContent);
const PAGE = 50;

/* ---------- 通用工具 ---------- */
function regTag(t){
  if(t==='进口新兽药注册') return '<span class="tag imp">'+t+'</span>';
  if(t==='变更注册') return '<span class="tag chg">'+t+'</span>';
  return '<span class="tag dom">'+t+'</span>';
}
function clinTag(t){
  if(t==='进口新兽药注册') return '<span class="tag imp">'+t+'</span>';
  return '<span class="tag dom">'+t+'</span>';
}
function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function srcCell(url,label){
  if(url) return '<span class="src"><a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label||'官方↗')+'</a></span>';
  return '<span class="muted">—</span>';
}
function openExternal(url){
  if(!url) return;
  var a=document.createElement('a');
  a.href=url; a.target='_blank'; a.rel='noopener noreferrer';
  document.body.appendChild(a); a.click(); a.remove();
}
function openClin(url){ openExternal(url); }

/* ---------- 注册审批 ---------- */
let regPage=1, regView=[];
function regFilter(){
  const type=document.getElementById('regType').value;
  const drug=document.getElementById('regDrug').value;
  const pet=document.getElementById('regPet').checked;
  const q=document.getElementById('regQ').value.trim().toLowerCase();
  const yr=document.getElementById('regYear').value;
  return REG.filter(r=>{
    if(type && r.regType!==type) return false;
    if(drug && r.drugType!==drug) return false;
    if(pet && r.isPet!==1) return false;
    if(yr && !(r.annDate||'').includes(yr)) return false;
    if(q){
      const hay=(r.drugName+' '+r.org+' '+r.annNum+' '+r.certNo+' '+r.indication).toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
}
function renderReg(){
  regView=regFilter();
  const total=regView.length;
  const pages=Math.max(1,Math.ceil(total/PAGE));
  if(regPage>pages) regPage=pages;
  const start=(regPage-1)*PAGE;
  const slice=regView.slice(start,start+PAGE);
  const body=document.getElementById('regBody');
  body.innerHTML = slice.length ? slice.map(r=>{
    const pet = r.isPet===1 ? ' <span class="tag pet">宠</span>' : '';
    return '<tr>'+
      '<td>'+esc(r.annNum)+'</td>'+
      '<td>'+esc(r.annDate)+'</td>'+
      '<td>'+regTag(r.regType)+pet+'</td>'+
      '<td>'+esc(r.drugType)+'</td>'+
      '<td>'+esc(r.drugName)+'</td>'+
      '<td>'+esc(r.org)+'</td>'+
      '<td>'+esc(r.indication)+'</td>'+'<td>'+esc(r.country)+'</td>'+
      
      '<td>'+esc(r.certNo)+'</td>'+
      '<td>'+srcCell(r.sourceUrl)+'</td>'+
    '</tr>';
  }).join('') : '<tr><td colspan="10" style="text-align:center;color:var(--muted);padding:24px">无匹配数据</td></tr>';
  document.getElementById('regCount').textContent='共 '+total+' 条结果';
  document.getElementById('regPage').textContent='第 '+regPage+' / '+pages+' 页';
}
document.getElementById('regSearch').onclick=()=>{regPage=1;renderReg();};
document.getElementById('regQ').addEventListener('keydown',e=>{if(e.key==='Enter'){regPage=1;renderReg();}});
document.getElementById('regType').onchange=()=>{regPage=1;renderReg();};
document.getElementById('regDrug').onchange=()=>{regPage=1;renderReg();};
document.getElementById('regPet').onchange=()=>{regPage=1;renderReg();};
document.getElementById('regYear').onchange=()=>{regPage=1;renderReg();};
document.getElementById('regPrev').onclick=()=>{if(regPage>1){regPage--;renderReg();}};
document.getElementById('regNext').onclick=()=>{regPage++;renderReg();};
document.getElementById('regExp').onclick=()=>exportCSV(regView,'注册审批数据.csv',
  ['annNum','annDate','regType','drugType','drugName','org','country','certNo','sourceUrl'],
  ['公告号','公告日期','注册类型','药品类型','药品名称','企业','国别','证书号','来源']);

/* ---------- 临床审批 ---------- */
let clinPage=1, clinView=[];
function clinFilter(){
  const type=document.getElementById('clinType').value;
  const pet=document.getElementById('clinPet').checked;
  const q=document.getElementById('clinQ').value.trim().toLowerCase();
  const yr=document.getElementById('clinYear').value;
  return CLIN.filter(r=>{
    if(type && r.regType!==type) return false;
    if(pet && r.isPet!==1) return false;
    if(yr && !(r.approveDate||'').includes(yr)) return false;
    if(q){
      const hay=(r.drugName+' '+r.org+' '+r.approvalNo+' '+r.indication+' '+r.species).toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
}
function renderClin(){
  clinView=clinFilter();
  const total=clinView.length;
  const pages=Math.max(1,Math.ceil(total/PAGE));
  if(clinPage>pages) clinPage=pages;
  const start=(clinPage-1)*PAGE;
  const slice=clinView.slice(start,start+PAGE);
  const body=document.getElementById('clinBody');
  body.innerHTML = slice.length ? slice.map(r=>{
    const pet = r.isPet===1 ? ' <span class="tag pet">宠</span>' : '';
    const clickAttr = r.sourceUrl ? ' onclick="openClin(&#39;'+esc(r.sourceUrl).replace(/'/g,'&#39;')+'&#39;)"' : '';
    return '<tr class="clin-row"'+clickAttr+'>'+
      '<td>'+clinTag(r.regType)+pet+'</td>'+
      '<td>'+esc(r.drugName)+'</td>'+
      '<td>'+esc(r.org)+'</td>'+
      '<td>'+esc(r.species)+'</td>'+
      '<td>'+esc(r.indication)+'</td>'+
      '<td>'+esc(r.approvalNo)+'</td>'+
      '<td>'+esc(r.acceptNo)+'</td>'+
      '<td>'+esc(r.approveDate)+'</td>'+
      '<td><span class="tag ok">'+esc(r.status||'同意临床试验')+'</span></td>'+
      '<td>'+srcCell(r.sourceUrl, r.sourceName?('来源↗'):'官方↗')+'</td>'+
    '</tr>';
  }).join('') : '<tr><td colspan="10" style="text-align:center;color:var(--muted);padding:24px">无匹配数据</td></tr>';
  document.getElementById('clinCount').textContent='共 '+total+' 条结果';
  document.getElementById('clinPage').textContent='第 '+clinPage+' / '+pages+' 页';
}
document.getElementById('clinSearch').onclick=()=>{clinPage=1;renderClin();};
document.getElementById('clinQ').addEventListener('keydown',e=>{if(e.key==='Enter'){clinPage=1;renderClin();}});
document.getElementById('clinType').onchange=()=>{clinPage=1;renderClin();};
document.getElementById('clinPet').onchange=()=>{clinPage=1;renderClin();};
document.getElementById('clinYear').onchange=()=>{clinPage=1;renderClin();};
document.getElementById('clinPrev').onclick=()=>{if(clinPage>1){clinPage--;renderClin();}};
document.getElementById('clinNext').onclick=()=>{clinPage++;renderClin();};
document.getElementById('clinExp').onclick=()=>exportCSV(clinView,'临床审批数据.csv',
  ['regType','drugName','org','species','indication','approvalNo','acceptNo','approveDate','status','sourceName','sourceUrl','note'],
  ['审批类型','药品名称','企业','靶动物','适应症','批件号','受理号','批准日期','结论','来源名称','来源链接','备注']);

/* ---------- 更新动态 ---------- */
function renderLog(){
  const domName={clinical:'临床审批',registration:'注册审批'};
  const srcName={vdts:'主管网站',enterprise_news:'企业新闻补充',manual:'人工核查'};
  document.getElementById('logList').innerHTML = LOG.map(l=>{
    return '<li>'+
      '<div class="ts">'+esc(l.ts)+(domName[l.domain]?('<span class="badge">'+esc(domName[l.domain])+'</span>'):'')+'</div>'+
      '<div class="meta">来源：'+(srcName[l.source]||esc(l.source))+' · 新增 '+l.added+' 条 · 累计 '+l.total+' 条</div>'+
      '<div>'+esc(l.note)+'</div>'+
    '</li>';
  }).join('') || '<li>暂无更新记录</li>';
}

/* ---------- Tab 切换 ---------- */
document.querySelectorAll('.tab').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel'+(t.dataset.tab==='reg'?'Reg':'Clin')).classList.add('active');
    if(t.dataset.tab==='clin'){renderClin();renderLog();}
  };
});

/* ---------- CSV 导出 ---------- */
function exportCSV(rows,filename,keys,headers){
  if(!rows.length){alert('当前没有可导出的数据');return;}
  const esc=v=>`"${(v==null?'':String(v)).replace(/"/g,'""')}"`;
  const lines=[headers.map(esc).join(',')];
  rows.forEach(r=>lines.push(keys.map(k=>esc(r[k])).join(',')));
  const blob=new Blob(['\uFEFF'+lines.join('\\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download=filename;
  a.click();
}

/* 年份筛选下拉填充 */
function fillYearSelect(sel, rows, key){
  var set={};
  rows.forEach(function(r){var m=String(r[key]||'').match(/[0-9]{4}/); if(m) set[m[0]]=1;});
  var years=Object.keys(set).sort(function(a,b){return b-a;});
  sel.innerHTML='<option value="">全部年份</option>'+years.map(function(y){return '<option value="'+y+'">'+y+'</option>';}).join('');
}
fillYearSelect(document.getElementById('regYear'), REG, 'annDate');
fillYearSelect(document.getElementById('clinYear'), CLIN, 'approveDate');
/* 初始渲染 */
renderReg();
</script>
</body>
</html>
"""
    html = (html
            .replace("__REG_TOTAL__", str(reg_total))
            .replace("__REG_DOM__", str(reg_dom))
            .replace("__REG_IMP__", str(reg_imp))
            .replace("__REG_PET__", str(reg_pet))
            .replace("__CLIN_TOTAL__", str(clin_total))
            .replace("__CLIN_DOM__", str(clin_dom))
            .replace("__CLIN_PET__", str(clin_pet))
            .replace("__VDTS__", VDTS_URL)
            .replace("__DATE__", gen_date)
            .replace("__REG__", reg_json)
            .replace("__CLIN__", clin_json)
            .replace("__LOG__", log_json))
    # 注入 PWA 自动同步脚本：检测 version.json 变化即刷新，保证移动端与 PC 端同源实时一致
    pwa_js = PWA_INLINE_JS.replace("__BUILD__", build_id)
    html = html.replace("</body>", pwa_js + "\n</body>")
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    write_pwa_assets(build_id, gen_date)
    print(f"生成 {OUT} | 注册 {reg_total} 条, 临床 {clin_total} 条, 更新动态 {len(logs)} 条 | PWA 构建 {build_id}")


if __name__ == "__main__":
    build_html(load_registration(), load_clinical(), load_update_log())
