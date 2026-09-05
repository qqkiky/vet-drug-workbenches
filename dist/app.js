/* Veterinary Biologics Tracking Workbench - frontend logic */
'use strict';

const I18N = {
  zh: {
    title: "国际兽用生物制品监管追踪工作台",
    subtitle: "美国 USDA/CVB · 欧盟 EMA/CVMP 获批产品",
    update: "同步数据", excel: "Excel", pdf: "PDF",
    live: "数据源状态", replace: "替换示例", updating: "更新中…",
    notifications: "通知", markRead: "全部已读",
    region: "地区", species: "物种", type: "产品类型", status: "状态", source: "资料来源",
    search: "搜索 产品/企业/适应症…", reset: "重置",
    trend: "历年获批数量", companies: "Top 10 生产企业",
    types: "产品类型分布", statusDist: "状态分布",
    products: "获批产品", changes: "变更记录",
    noChanges: "暂无变更记录", noNotif: "暂无通知",
    allRead: "已全部标记为已读", results: "条",
    kpiTotal: "总获批", kpiUS: "美国", kpiEU: "欧盟",
    kpiVaccine: "疫苗", kpiDiag: "诊断试剂", kpiThera: "治疗性",
    ingested: "数据已更新", new: "新增", updated: "信息更新",
    statusChange: "状态变更", withdrawn: "撤回",
    from: "原值", to: "新值", field: "字段",
    toastNew: "条新通知", exporting: "正在导出…",
    dateUnknown: "未知",
    liveUpdate: "🔄 同步数据",
    updatingData: "正在抓取 USDA / EMA 数据…",
    updateTitle: "同步进度",
    updateDone: "✅ 同步完成",
    updateFailed: "❌ 同步失败",
    publishHint: "更新已入库；本站由 GitHub Pages 自动发布，推送后约 1–3 分钟自动生效。",
    trendNote: "美国 USDA/CVB 官方目录未公开逐产品获批日期，趋势图仅统计有获批日期的记录（{n} 条美国产品日期未知）。",
    noMatchTitle: "未找到匹配的产品",
    noMatchHint: "请调整筛选条件或搜索关键词后重试。",
    snapshotBanner: "📅 数据快照{d} · 每日自动更新",
  },
  en: {
    title: "Veterinary Biologics Regulatory Tracker",
    subtitle: "USDA/CVB · EMA/CVMP approved products",
    update: "Sync Data", excel: "Excel", pdf: "PDF",
    live: "Source status", replace: "Replace sample", updating: "Updating…",
    notifications: "Notifications", markRead: "Mark all read",
    region: "Region", species: "Species", type: "Product Type", status: "Status", source: "Source",
    search: "Search products/companies/indications…", reset: "Reset",
    trend: "Approvals by Year", companies: "Top 10 Manufacturers",
    types: "Product Type Breakdown", statusDist: "Status Breakdown",
    products: "Approved Products", changes: "Change Log",
    noChanges: "No changes yet.", noNotif: "No notifications yet.",
    allRead: "All marked as read", results: "results",
    kpiTotal: "Total", kpiUS: "US", kpiEU: "EU",
    kpiVaccine: "Vaccine", kpiDiag: "Diagnostic", kpiThera: "Therapeutic",
    ingested: "Data updated", new: "NEW", updated: "UPDATED",
    statusChange: "STATUS CHANGE", withdrawn: "WITHDRAWN",
    from: "from", to: "to", field: "field",
    toastNew: "new notifications", exporting: "Exporting…",
    dateUnknown: "Unknown",
    liveUpdate: "🔄 Sync Data",
    updatingData: "Fetching USDA / EMA data…",
    updateTitle: "Sync Progress",
    updateDone: "✅ Sync complete",
    updateFailed: "❌ Sync failed",
    publishHint: "Stored. This page is auto-published to GitHub Pages and goes live ~1\u20133 min after each update is pushed.",
    trendNote: "The USDA/CVB catalog does not publish per-product approval dates, so the trend covers only records with a known date ({n} US products are undated).",
    noMatchTitle: "No matching products",
    noMatchHint: "Try adjusting the filters or search keywords.",
    snapshotBanner: "📅 Snapshot{d} · auto-updated daily",
  }
};

// Category label maps
const LABELS = {
  region: { zh: { US: "美国", EU: "欧盟" }, en: { US: "US", EU: "EU" } },
  species: { zh: { Cat: "猫", Dog: "犬", Both: "猫犬" }, en: { Cat: "Cat", Dog: "Dog", Both: "Cat & Dog" } },
  type: { zh: { Vaccine: "疫苗", Diagnostic: "诊断试剂", Therapeutic: "治疗性生物制品" },
          en: { Vaccine: "Vaccine", Diagnostic: "Diagnostic", Therapeutic: "Therapeutic" } },
  status: { zh: { Active: "有效", Suspended: "暂停", Withdrawn: "撤回" },
            en: { Active: "Active", Suspended: "Suspended", Withdrawn: "Withdrawn" } },
  change: { zh: { NEW: "新增", UPDATED: "信息更新", STATUS_CHANGE: "状态变更", WITHDRAWN: "撤回" },
            en: { NEW: "NEW", UPDATED: "UPDATED", STATUS_CHANGE: "STATUS CHANGE", WITHDRAWN: "WITHDRAWN" } },
};

let LANG = localStorage.getItem("vbt_lang") || "zh";
let META = { regions: ["US", "EU"], species: ["Cat", "Dog", "Both"],
             product_types: ["Vaccine", "Diagnostic", "Therapeutic"],
             statuses: ["Active", "Suspended", "Withdrawn"] };
const charts = {};
let lastNotifCount = 0;
let firstNotifLoad = true;
let STATIC_DATA = null;  // populated in static-deploy mode

const $ = (id) => document.getElementById(id);
const t = (k) => (I18N[LANG][k] ?? k);
const lbl = (cat, v) => (LABELS[cat]?.[LANG]?.[v] ?? v);

async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function applyLang() {
  document.documentElement.lang = LANG;
  const dict = I18N[LANG];
  const setText = (id, text) => { const el = $(id); if (el) el.textContent = text; };
  setText("app-title", dict.title);
  setText("app-subtitle", dict.subtitle);
  setText("lbl-update", dict.liveUpdate);
  setText("lbl-update-title", dict.updateTitle);
  setText("lbl-live", dict.live);
  setText("lbl-replace", dict.replace);
  setText("btn-excel", dict.excel);
  setText("btn-pdf", dict.pdf);
  setText("lbl-notif-title", dict.notifications);
  setText("lbl-notif-read", dict.markRead);
  setText("lbl-reset", dict.reset);
  setText("lbl-trend", dict.trend);
  setText("lbl-companies", dict.companies);
  setText("lbl-types", dict.types);
  setText("lbl-status", dict.statusDist);
  setText("lbl-products", dict.products);
  setText("lbl-changes", dict.changes);
  if ($("f-q")) $("f-q").placeholder = dict.search;
  // table headers
  $("h-region").textContent = dict.region;
  $("h-species").textContent = dict.species;
  $("h-type").textContent = dict.type;
  $("h-name").textContent = (LANG === "zh" ? "产品名称" : "Product");
  $("h-no").textContent = (LANG === "zh" ? "获批编号" : "Approval No.");
  $("h-mfr").textContent = (LANG === "zh" ? "生产企业" : "Manufacturer");
  $("h-ind").textContent = (LANG === "zh" ? "适应症" : "Indication");
  $("h-form").textContent = (LANG === "zh" ? "剂型" : "Dosage Form");
  $("h-strength").textContent = (LANG === "zh" ? "规格" : "Strength");
  $("h-date").textContent = (LANG === "zh" ? "获批日期" : "Approval Date");
  $("h-status").textContent = dict.status;
  $("h-source").textContent = dict.source;
  // selects placeholders
  fillSelect("f-region", META.regions, dict.region, "region");
  fillSelect("f-species", META.species, dict.species, "species");
  fillSelect("f-type", META.product_types, dict.type, "type");
  fillSelect("f-status", META.statuses, dict.status, "status");
  $("btn-lang").textContent = LANG === "zh" ? "EN" : "中";
  try { window.dispatchEvent(new Event("vbt-langchange")); } catch (e) {}
}

function fillSelect(id, values, placeholder, cat) {
  const cur = $(id).value;
  $(id).innerHTML = `<option value="">${placeholder}</option>` +
    values.map(v => `<option value="${v}">${lbl(cat, v)}</option>`).join("");
  $(id).value = cur;
}

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 4000);
}

// ---- data loading ----
function currentFilters() {
  return {
    region: $("f-region").value, species: $("f-species").value,
    product_type: $("f-type").value, status: $("f-status").value,
    q: $("f-q").value.trim(),
  };
}

function showEmptyState() {
  const tb = $("tbl-products").querySelector("tbody");
  tb.innerHTML = `<tr><td colspan="12" class="empty-state">
    <div class="empty-title">${t("noMatchTitle")}</div>
    <div class="empty-hint">${t("noMatchHint")}</div>
  </td></tr>`;
  $("result-count").textContent = "0 " + t("results");
}

function renderProducts(rows) {
  const tb = $("tbl-products").querySelector("tbody");
  if (!Array.isArray(rows) || rows.length === 0) {
    showEmptyState();
    return;
  }
  tb.innerHTML = rows.map(r => `
    <tr>
      <td><span class="tag tag-${r.region.toLowerCase()}">${lbl("region", r.region)}</span></td>
      <td><span class="tag tag-${r.species.toLowerCase()}">${lbl("species", r.species)}</span></td>
      <td>${lbl("type", r.product_type)}</td>
      <td>${esc(r.product_name)}</td>
      <td>${esc(r.approval_number)}</td>
      <td>${esc(r.manufacturer || "")}</td>
      <td>${esc(r.indication || "")}</td>
      <td>${esc(r.dosage_form || "")}</td>
      <td>${esc(r.strength || "")}</td>
      <td>${r.approval_date ? esc(r.approval_date) : t("dateUnknown")}</td>
      <td class="status-${r.status}">${lbl("status", r.status)}</td>
      <td>${r.source_url
        ? `<a class="src-link" href="${esc(r.source_url)}" target="_blank" rel="noopener" title="${esc(r.source_url)}">${esc(r.source || "官方来源")} ↗</a>`
        : esc(r.source || "")}</td>
    </tr>`).join("");
  $("result-count").textContent = rows.length + " " + t("results");
}

async function loadProducts() {
  const f = currentFilters();
  const qs = new URLSearchParams(f).toString();
  const rows = await api("/api/products?" + qs);
  renderProducts(rows);
}

function renderStats(s) {
  // KPIs
  const count = (arr, key, val) => (arr.find(x => x.key === val)?.count) || 0;
  const kpis = [
    [t("kpiTotal"), s.total],
    [t("kpiUS"), count(s.by_region, "key", "US")],
    [t("kpiEU"), count(s.by_region, "key", "EU")],
    [t("kpiVaccine"), count(s.by_type, "key", "Vaccine")],
    [t("kpiDiag"), count(s.by_type, "key", "Diagnostic")],
    [t("kpiThera"), count(s.by_type, "key", "Therapeutic")],
  ];
  $("kpis").innerHTML = kpis.map(([l, n]) =>
    `<div class="kpi"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("");

  // Annual trend (line, per region)
  const years = new Set();
  Object.values(s.annual_trend).forEach(o => Object.keys(o).forEach(y => years.add(y)));
  const ylist = [...years].filter(y => /^\d{4}$/.test(y)).sort();
  const ds = (META.regions).map((reg, i) => ({
    label: lbl("region", reg),
    data: ylist.map(y => s.annual_trend[reg]?.[y] || 0),
    borderColor: i === 0 ? "#1f4e78" : "#2e9e5b",
    backgroundColor: i === 0 ? "rgba(31,78,120,.15)" : "rgba(46,158,91,.15)",
    tension: 0.3, fill: true,
  }));
  renderChart("chart-trend", "line", { labels: ylist, datasets: ds },
    { plugins: { legend: { position: "bottom" } } });

  // Explain why a region may be missing from the trend (e.g. USDA codebook
  // has no per-product approval date).
  const note = $("trend-note");
  if (note) {
    const usUndated = (s.undated_by_region && s.undated_by_region.US) || 0;
    if (usUndated > 0) {
      note.textContent = t("trendNote").replace("{n}", usUndated);
      note.classList.remove("hidden");
    } else {
      note.textContent = "";
      note.classList.add("hidden");
    }
  }

  // Companies (horizontal bar, top 10)
  const comp = s.companies.slice(0, 10);
  renderChart("chart-companies", "bar",
    { labels: comp.map(c => c.name), datasets: [{ label: t("companies"),
        data: comp.map(c => c.count), backgroundColor: "#2e6da4" }] },
    { indexAxis: "y", plugins: { legend: { display: false } } });

}

async function loadStats() {
  const s = await api("/api/stats");
  renderStats(s);
}

function renderChart(id, type, data, options) {
  const canvas = $(id);
  if (typeof Chart === "undefined") {
    canvas.outerHTML = `<div class="cmeta">图表库未加载（需要联网加载 Chart.js CDN）。数据表格与导出功能不受影响。</div>`;
    return;
  }
  if (charts[id]) charts[id].destroy();
  const ctx = canvas.getContext("2d");
  charts[id] = new Chart(ctx, { type, data, options: Object.assign(
    { responsive: true, maintainAspectRatio: false }, options) });
}

function renderChanges(ch) {
  const box = $("changes-list");
  if (!ch.length) { box.innerHTML = `<div class="cmeta">${t("noChanges")}</div>`; return; }
  box.innerHTML = ch.map(c => {
    const ct = c.change_type;
    let detail = "";
    if (c.field && c.prev_value !== null) {
      detail = `${t("field")}: ${esc(c.field || "")}<br>${t("from")}: ${esc(c.prev_value || "—")} → ${t("to")}: ${esc(c.new_value || "—")}`;
    } else if (ct === "WITHDRAWN") {
      detail = `${lbl("status", "Withdrawn")}`;
    } else {
      detail = `${lbl("region", c.region)} · ${esc(c.approval_number)}`;
    }
    return `<div class="change-item">
      <span class="cbadge c-${ct}">${lbl("change", ct)}</span>
      <div class="cbody"><strong>${esc(c.product_name)}</strong>
        <div class="cmeta">${detail} · ${esc(c.change_date)}</div></div>
    </div>`;
  }).join("");
}

async function loadChanges() {
  const ch = await api("/api/changes?limit=200");
  renderChanges(ch);
}

async function loadNotifications(unreadOnly = false) {
  const q = unreadOnly ? "?unread=1" : "";
  const list = await api("/api/notifications" + q);
  const box = $("notif-list");
  if (!list.length) { box.innerHTML = `<div class="notif-item">${t("noNotif")}</div>`; }
  else {
    box.innerHTML = list.map(c => `
      <div class="notif-item">
        <span class="cbadge c-${c.change_type}">${lbl("change", c.change_type)}</span>
        <span style="margin-left:6px">${esc(c.product_name)}</span>
        <div class="meta">${lbl("region", c.region)} · ${esc(c.approval_number)} · ${esc(c.change_date)}</div>
      </div>`).join("");
  }
  return list.length;
}

async function refreshAll() {
  await Promise.all([loadProducts(), loadStats(), loadChanges()]);
}

// ---- events ----
function wire() {
  // Static deploy mode: no backend, so hide live-update / export controls.
  if (window.__STATIC__) {
    ["btn-update", "btn-excel", "btn-pdf", "btn-bell"].forEach(id => {
      const el = $(id);
      if (el) el.style.display = "none";
    });
    const liveToggle = $("chk-live");
    if (liveToggle && liveToggle.closest) liveToggle.closest(".live-toggle").style.display = "none";
    const wrapReplace = $("wrap-replace");
    if (wrapReplace) wrapReplace.style.display = "none";
    const csvBtn = $("btn-csv");
    if (csvBtn) { csvBtn.classList.remove("hidden"); csvBtn.onclick = exportCSV; }
  }
  $("btn-lang").onclick = () => {
    LANG = LANG === "zh" ? "en" : "zh";
    localStorage.setItem("vbt_lang", LANG);
    applyLang();
    if (window.__STATIC__) renderStaticAll(); else refreshAll();
  };
  const onFilter = window.__STATIC__
    ? () => renderProducts(filteredProducts())
    : loadProducts;
  ["f-region", "f-species", "f-type", "f-status"].forEach(id =>
    $(id).onchange = onFilter);
  let to;
  $("f-q").oninput = () => { clearTimeout(to); to = setTimeout(onFilter, 250); };
  $("btn-reset").onclick = () => {
    ["f-region", "f-species", "f-type", "f-status"].forEach(id => $(id).value = "");
    $("f-q").value = ""; onFilter();
  };
  $("btn-update").onclick = async () => {
    const btn = $("btn-update");
    const lbl = $("lbl-update");
    const panel = $("update-panel");
    const logEl = $("update-log");
    panel.classList.remove("hidden");
    logEl.innerHTML = "";
    const appendLog = (msg, cls) => {
      const d = document.createElement("div");
      d.className = "log-line" + (cls ? " " + cls : "");
      d.textContent = msg;
      logEl.appendChild(d);
      logEl.scrollTop = logEl.scrollHeight;
    };
    btn.disabled = true;
    const prevLabel = lbl.textContent;
    lbl.textContent = t("updatingData");
    try {
      const replace = $("chk-replace").checked;
      const res = await api("/api/update", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ live: true, replace }) });
      const jobId = res.job_id;
      appendLog("▶ 已提交实时更新任务（" + jobId + "），开始抓取 USDA / EMA…");
      let lastLen = 0;
      while (true) {
        await new Promise(r => setTimeout(r, 1500));
        const st = await api("/api/update/" + jobId);
        st.logs.slice(lastLen).forEach(l =>
          appendLog(l, st.status === "failed" ? "err" : ""));
        lastLen = st.logs.length;
        if (st.status === "done") {
          appendLog(t("updateDone"), "ok");
          if (st.summary && st.summary.meta && st.summary.meta.fallbacks &&
              st.summary.meta.fallbacks.length) {
            appendLog("⚠ 部分数据源抓取失败，已保留原有数据：" +
              st.summary.meta.fallbacks.join(", "), "warn");
          }
          appendLog(t("publishHint"), "hint");
          break;
        } else if (st.status === "failed") {
          appendLog(t("updateFailed") + (st.error ? "：" + st.error : ""), "err");
          break;
        }
      }
      await refreshAll();
      await updateBadge();
    } catch (e) {
      appendLog("Error: " + e.message, "err");
    } finally {
      btn.disabled = false;
      lbl.textContent = prevLabel;
    }
  };
  if ($("btn-update-close")) $("btn-update-close").onclick = () =>
    $("update-panel").classList.add("hidden");
  // enable the "replace" sub-toggle only when live is on
  const syncReplace = () => {
    const on = $("chk-live").checked;
    $("wrap-replace").classList.toggle("active", on);
    $("chk-replace").disabled = !on;
  };
  $("chk-live").onchange = syncReplace;
  $("chk-replace").onchange = syncReplace;
  syncReplace();
  $("btn-excel").onclick = () => {
    toast(t("exporting"));
    window.location = "/api/export/excel?lang=" + LANG + "&" +
      new URLSearchParams(currentFilters()).toString();
  };
  $("btn-pdf").onclick = () => {
    toast(t("exporting"));
    window.location = "/api/export/pdf?lang=" + LANG + "&" +
      new URLSearchParams(currentFilters()).toString();
  };
  $("btn-bell").onclick = async (e) => {
    e.stopPropagation();
    const p = $("notif-panel");
    p.classList.toggle("hidden");
    if (!p.classList.contains("hidden")) {
      await loadNotifications(false);
    }
  };
  $("btn-notif-read").onclick = async () => {
    await api("/api/notifications/read", { method: "POST" });
    await updateBadge();
    await loadNotifications(false);
    toast(t("allRead"));
  };
  document.addEventListener("click", (e) => {
    if (!$(e.target).closest("#notif-panel") && e.target.id !== "btn-bell")
      $("notif-panel").classList.add("hidden");
  });
}

async function updateBadge() {
  const n = await api("/api/notifications?unread=1");
  const cnt = n.length;
  const badge = $("notif-badge");
  if (cnt > 0) { badge.textContent = cnt; badge.classList.remove("hidden"); }
  else badge.classList.add("hidden");
  if (!firstNotifLoad && cnt > lastNotifCount) {
    toast(`${cnt - lastNotifCount} ${t("toastNew")}`);
  }
  firstNotifLoad = false;
  lastNotifCount = cnt;
}

function showStaticBanner() {
  const m = document.querySelector("main");
  if (!m) return;
  const d = window.__SNAPSHOT_DATE__ || "";
  const banner = document.createElement("div");
  banner.className = "static-banner";
  banner.innerHTML = t("snapshotBanner").replace("{d}", d ? "（" + d + "）" : "");
  m.insertBefore(banner, m.firstChild);
}

// Local filtering for static-deploy mode (no backend to query).
function filteredProducts() {
  const f = currentFilters();
  const q = (f.q || "").toLowerCase();
  return (STATIC_DATA ? STATIC_DATA.products : []).filter(p =>
    (!f.region || p.region === f.region) &&
    (!f.species || p.species === f.species) &&
    (!f.product_type || p.product_type === f.product_type) &&
    (!f.status || p.status === f.status) &&
    (!q || ("" + (p.product_name || "") + " " + (p.manufacturer || "") + " " +
            (p.indication || "") + " " + (p.approval_number || "")).toLowerCase().includes(q))
  );
}

function renderStaticAll() {
  renderProducts(filteredProducts());
  renderStats(STATIC_DATA.stats);
  renderChanges(STATIC_DATA.changes);
}

function exportCSV() {
  const rows = filteredProducts();
  if (!rows.length) { toast(t("noMatchHint")); return; }
  const zh = LANG === "zh";
  const cols = [
    [t("region"), r => lbl("region", r.region)],
    [t("species"), r => lbl("species", r.species)],
    [t("type"), r => lbl("type", r.product_type)],
    [zh ? "产品名称" : "Product", r => r.product_name],
    [zh ? "获批编号" : "Approval No.", r => r.approval_number],
    [zh ? "生产企业" : "Manufacturer", r => r.manufacturer || ""],
    [zh ? "适应症" : "Indication", r => r.indication || ""],
    [zh ? "剂型" : "Dosage Form", r => r.dosage_form || ""],
    [zh ? "规格" : "Strength", r => r.strength || ""],
    [zh ? "获批日期" : "Approval Date", r => r.approval_date || ""],
    [zh ? "状态" : "Status", r => lbl("status", r.status)],
    [zh ? "资料来源" : "Source", r => r.source || ""],
  ];
  const csv = rows.map(row => cols.map(([, get]) => {
    const v = String(get(row) == null ? "" : get(row));
    return '"' + v.replace(/"/g, '""') + '"';
  }).join(","));
  csv.unshift(cols.map(c => c[0]).join(","));
  const blob = new Blob(["\ufeff" + csv.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "vet-biologics-" + new Date().toISOString().slice(0, 10) + ".csv";
  document.body.appendChild(a); a.click(); a.remove();
  toast(t("exporting"));
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- init ----
function showFatal(msg) {
  let el = $("fatal");
  if (!el) {
    el = document.createElement("div");
    el.id = "fatal";
    el.className = "fatal";
    document.querySelector("main").prepend(el);
  }
  el.innerHTML = msg;
}

(async function init() {
  const initial = window.__INITIAL_DATA__;
  if (initial) {
    // Server embedded the dataset directly in the page (works in sandboxed
    // preview panels that cannot perform their own fetch()).
    try {
      META = initial.meta || META;
      applyLang();
      wire();
      renderProducts(initial.products || []);
      renderStats(initial.stats || {});
      renderChanges(initial.changes || []);
      const n = (initial.notifications || []).length;
      const badge = $("notif-badge");
      if (n > 0) { badge.textContent = n; badge.classList.remove("hidden"); }
      else badge.classList.add("hidden");
      lastNotifCount = n;
      STATIC_DATA = initial;
      if (window.__STATIC__) showStaticBanner();
    } catch (e) {
      showFatal("⚠ 页面初始化渲染失败（" + e.message + "）。<br>" +
        "请按 <b>Ctrl+Shift+R</b> 硬刷新，或复制地址到 Chrome/Edge 打开。");
      console.error(e);
    }
    delete window.__INITIAL_DATA__;
  } else {
    try { META = await api("/api/meta"); } catch (e) {}
    applyLang();
    wire();
    try {
      await refreshAll();
      await updateBadge();
    } catch (e) {
      showFatal("⚠ 无法从数据接口加载数据（" + e.message +
        "）。<br>请确认服务已启动，并用 <b>外部浏览器</b>（Chrome/Edge）打开 " +
        "<code>http://127.0.0.1:5000</code>，而非软件内预览面板。");
    }
  }
  if (!window.__STATIC__) {
    setInterval(async () => {
      try { await updateBadge(); } catch (e) {}
    }, 30000);  // poll notifications every 30s
  }
})();
