"""Flask backend for the Veterinary Biologics Tracking Workbench.

Serves the bilingual SPA, exposes a REST API for filtering / stats / changes /
notifications, runs periodic ingestion, and exports data to Excel & PDF.
"""
import io
import json
import os
import threading
import time
import uuid
from datetime import date, datetime

from flask import (Flask, request, jsonify, send_from_directory,
                   send_file, Response)

import db
import ingest
import regulatory
import build_static

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")

# Disable static-file caching so UI/JS updates are picked up immediately after
# a deploy (otherwise browsers keep the old app.js and the live toggle silently
# does nothing). Flask default is a 12h cache for static assets.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def no_cache(response):
    """Force revalidation for every response so cached HTML/JS/CSS never hides
    a fix."""
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0")
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# --- daily auto-update ------------------------------------------------
# One scheduled pull per day at 20:00 local time, followed by an email digest
# that is sent ONLY when something actually changed (notify_email.send_digest
# returns 0 on quiet days, so no mail is sent when there are no updates).
_DAILY_RAN = {"d": None}


def _scheduler_loop():
    while True:
        time.sleep(30)
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        # Fire once in the 20:00-20:14 window (resilient to the 30s tick).
        if now.hour == 20 and now.minute < 15 and _DAILY_RAN["d"] != today:
            try:
                import daily_sync
                status = daily_sync.persist_status(daily_sync.run_sync())
                app.logger.info("Daily 20:00 sync: %s",
                                daily_sync.format_feedback(status))
                try:
                    import notify_email
                    notify_email.send_digest()
                except Exception as ne:  # noqa: BLE001
                    app.logger.warning("digest failed: %s", ne)
            except Exception as e:  # noqa: BLE001
                app.logger.warning("Daily 20:00 update failed: %s", e)
            _DAILY_RAN["d"] = today


def _render_index_with_data():
    """Serve index.html with the current dataset embedded in the page.

    This makes the workbench usable even from sandboxed preview panels
    (e.g. WorkBuddy's built-in browser) that block or fail to run the
    page's own fetch() calls to the local API.
    """
    html_path = os.path.join(STATIC_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    initial = {
        "meta": {
            "regions": db.REGIONS,
            "species": db.SPECIES,
            "product_types": db.PRODUCT_TYPES,
            "statuses": db.STATUSES,
            "sources": ["USDA", "EMA"],
        },
        "products": db.get_products({}),
        "stats": db.get_stats(),
        "changes": db.get_changes(limit=300),
        "notifications": db.get_notifications(only_unread=True, limit=50),
    }
    script = "<script>window.__INITIAL_DATA__ = " + json.dumps(
        initial, ensure_ascii=False, default=str) + ";</script>"
    marker = '<script src="app.js?v=6" defer></script>'
    html = html.replace(marker, script + "\n  " + marker)
    return Response(html, mimetype="text/html")


@app.route("/")
def index():
    return _render_index_with_data()


@app.route("/api/meta")
def meta():
    return jsonify({
        "regions": db.REGIONS,
        "species": db.SPECIES,
        "product_types": db.PRODUCT_TYPES,
        "statuses": db.STATUSES,
        "sources": ["USDA", "EMA"],
    })


@app.route("/api/products")
def products():
    filters = {
        "region": request.args.get("region"),
        "species": request.args.get("species"),
        "product_type": request.args.get("product_type"),
        "status": request.args.get("status"),
        "q": request.args.get("q"),
    }
    filters = {k: v for k, v in filters.items() if v}
    return jsonify(db.get_products(filters))


@app.route("/api/stats")
def stats():
    return jsonify(db.get_stats())


@app.route("/api/sync-status")
def sync_status():
    """Latest daily_sync.py outcome (shared by desktop + mobile status bar)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "sync_state.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        latest = state.get("latest") or {}
        latest["history"] = state.get("history", [])[:14]
        return jsonify(latest)
    except Exception:
        return jsonify({})


@app.route("/api/changes")
def changes():
    limit = int(request.args.get("limit", 300))
    return jsonify(db.get_changes(limit))


@app.route("/api/notifications")
def notifications():
    unread = request.args.get("unread") == "1"
    return jsonify(db.get_notifications(only_unread=unread, limit=50))


@app.route("/api/notifications/read", methods=["POST"])
def mark_read():
    db.mark_notifications_read()
    return jsonify({"ok": True})


@app.route("/api/ingest", methods=["POST"])
def run_ingest():
    """Trigger a regulatory pull and diff.

    Body (optional JSON):
      ingest_date : override the effective pull date (ISO).
      live        : true -> use real regulator feeds (falls back per-source on
                    failure); false/omitted -> sample snapshot.
      replace     : true -> clear the live-source sample slices first (clean
                    switch to live data). Only honoured when live is true.
    """
    body = request.get_json(silent=True) or {}
    ingest_date = body.get("ingest_date")
    live = body.get("live")
    replace = body.get("replace")
    summary = ingest.pull_update(ingest_date=ingest_date, live=live,
                                 replace=replace)
    return jsonify({"ok": True, "summary": summary,
                    "generated_at": date.today().isoformat()})


# ---------------------------------------------------------------------------
# Async "live update" job: real-time USDA/EMA scrape + static rebuild
# ---------------------------------------------------------------------------
_UPDATE_JOBS = {}
_UPDATE_LOCK = threading.Lock()


class _UpdateJob:
    def __init__(self, job_id):
        self.id = job_id
        self.status = "running"      # running | done | failed
        self.logs = []
        self.summary = None
        self.error = None

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append("[%s] %s" % (ts, msg))


def _run_update_job(job, replace):
    try:
        job.log("▶ 开始实时抓取 USDA / CVB 与 EMA / CVMP 官方数据…")
        summary = ingest.pull_update(live=True, replace=replace)
        job.summary = summary
        job.log("✓ 抓取完成 — 新增 %d / 更新 %d / 状态变更 %d / 撤回 %d"
                % (summary.get("new", 0), summary.get("updated", 0),
                   summary.get("status_change", 0), summary.get("withdrawn", 0)))
        meta = summary.get("meta") or {}
        for src, sm in (meta.get("per_source") or {}).items():
            st = (sm.get("status")
                  or ("error: " + str(sm.get("error")) if sm.get("error") else "ok"))
            job.log("    · %s: %s" % (src, st))
        if meta.get("fallbacks"):
            job.log("⚠ 以下来源抓取失败，已保留原有数据: %s"
                    % ", ".join(meta["fallbacks"]))
        job.log("▶ 重建静态包 dist/（嵌入最新数据）…")
        build_static.build()
        job.log("✓ 静态包已重建 (snapshot=%s)" % date.today().isoformat())
        job.status = "done"
        job.log("✔ 全部完成。本地工作台已刷新；公网链接每日 20:00 自动发布，"
                "或回复“发布”立即推送。")
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error = str(e)
        job.log("✗ 更新失败: " + str(e))


@app.route("/api/update", methods=["POST"])
def start_update():
    """Kick off a real-time regulatory pull + static rebuild in the background.

    Returns a job id the client polls via /api/update/<job_id>.
    Body (optional JSON): {"replace": true} to clear sample slices first.
    """
    body = request.get_json(silent=True) or {}
    replace = bool(body.get("replace"))
    job_id = uuid.uuid4().hex[:8]
    job = _UpdateJob(job_id)
    with _UPDATE_LOCK:
        _UPDATE_JOBS[job_id] = job
    threading.Thread(target=_run_update_job, args=(job, replace),
                    daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/update/<job_id>")
def update_status(job_id):
    with _UPDATE_LOCK:
        job = _UPDATE_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "unknown job"}), 404
    return jsonify({"ok": True, "status": job.status, "logs": job.logs,
                    "summary": job.summary, "error": job.error})


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
def _export_rows():
    filters = {
        "region": request.args.get("region"),
        "species": request.args.get("species"),
        "product_type": request.args.get("product_type"),
        "status": request.args.get("status"),
        "q": request.args.get("q"),
    }
    filters = {k: v for k, v in filters.items() if v}
    return db.get_products(filters)


@app.route("/api/export/excel")
def export_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    lang = request.args.get("lang", "zh")
    rows = _export_rows()
    changes = db.get_changes(300)
    stats = db.get_stats()

    # i18n header labels
    if lang == "zh":
        headers = ["地区", "物种", "产品类型", "产品名称", "获批编号", "生产企业",
                   "适应症", "剂型", "规格", "获批日期", "状态", "数据来源"]
        ch_headers = ["变更日期", "产品名称", "地区", "获批编号", "变更类型",
                      "字段", "原值", "新值"]
    else:
        headers = ["Region", "Species", "Product Type", "Product Name",
                   "Approval No.", "Manufacturer", "Indication", "Dosage Form",
                   "Strength", "Approval Date", "Status", "Source"]
        ch_headers = ["Change Date", "Product", "Region", "Approval No.",
                      "Change Type", "Field", "Prev", "New"]

    wb = Workbook()
    # Products sheet
    ws = wb.active
    ws.title = "Products"
    ws.append(headers)
    hdr_fill = PatternFill("solid", fgColor="1F4E78")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for r in rows:
        ws.append([r["region"], r["species"], r["product_type"], r["product_name"],
                   r["approval_number"], r.get("manufacturer"), r.get("indication"),
                   r.get("dosage_form"), r.get("strength"), r.get("approval_date"),
                   r.get("status"), r.get("source")])
        # Make the "数据来源" cell a clickable hyperlink to the public resource.
        url = r.get("source_url")
        if url:
            c = ws.cell(row=ws.max_row, column=len(headers))
            c.hyperlink = url
            c.font = Font(color="0563C1", underline="single")
    widths = [8, 8, 12, 28, 16, 18, 34, 20, 14, 12, 10, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    # Changes sheet
    wc = wb.create_sheet("Changes")
    wc.append(ch_headers)
    for c in range(1, len(ch_headers) + 1):
        cell = wc.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = hdr_fill
    type_map = {"NEW": "新增", "UPDATED": "信息更新", "STATUS_CHANGE": "状态变更",
                "WITHDRAWN": "撤回"}
    for ch in changes:
        wc.append([ch["change_date"], ch["product_name"], ch["region"],
                   ch["approval_number"],
                   type_map.get(ch["change_type"], ch["change_type"]),
                   ch.get("field") or "", ch.get("prev_value") or "",
                   ch.get("new_value") or ""])

    # Stats sheet
    wst = wb.create_sheet("Stats")
    wst.append(["Metric", "Value"])
    wst.append(["Total products", stats["total"]])
    for d in stats["by_region"]:
        wst.append([f"Region: {d['key']}", d["count"]])
    for d in stats["by_species"]:
        wst.append([f"Species: {d['key']}", d["count"]])
    for d in stats["by_type"]:
        wst.append([f"Type: {d['key']}", d["count"]])
    for d in stats["by_status"]:
        wst.append([f"Status: {d['key']}", d["count"]])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"vet_biologics_{date.today().isoformat()}.xlsx"
    return send_file(buf, mimetype=("application/vnd.openxmlformats-officedocument"
                                    ".spreadsheetml.sheet"),
                     as_attachment=True, download_name=fname)


@app.route("/api/export/pdf")
def export_pdf():
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    lang = request.args.get("lang", "zh")
    rows = _export_rows()
    changes = db.get_changes(200)

    # Register a CJK font so Chinese headers/labels render.
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font = "STSong-Light"
    except Exception:
        font = "Helvetica"

    if lang == "zh":
        headers = ["地区", "物种", "类型", "产品名称", "获批编号", "企业",
                   "适应症", "剂型", "规格", "获批日期", "状态", "资料来源"]
        title = "兽用生物制品获批信息汇总"
        ch_title = "变更记录"
        type_map = {"NEW": "新增", "UPDATED": "更新", "STATUS_CHANGE": "状态变更",
                    "WITHDRAWN": "撤回"}
        ch_headers = ["变更日期", "产品", "地区", "编号", "类型", "字段", "原值", "新值"]
    else:
        headers = ["Region", "Species", "Type", "Product", "No.", "Mfr",
                   "Indication", "Form", "Strength", "Date", "Status", "Source"]
        title = "Veterinary Biologics Approval Report"
        ch_title = "Change Log"
        type_map = {}
        ch_headers = ["Date", "Product", "Region", "No.", "Type", "Field",
                      "Prev", "New"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=title)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"Generated: {date.today().isoformat()}  |  "
                           f"Records: {len(rows)}", styles["Normal"]))
    story.append(Spacer(1, 6))

    def _t(v):
        if v is None:
            return ""
        return str(v)

    def _safe(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    link_style = ParagraphStyle("link", parent=styles["Normal"],
                                fontSize=7, leading=9,
                                textColor=colors.HexColor("#1f4e78"))

    def _src(r):
        """Source cell: clickable hyperlink when a public URL exists."""
        url = r.get("source_url")
        label = _t(r.get("source") or "官方来源")
        if url:
            return Paragraph(f'<a href="{_safe(url)}">{_safe(label)}</a>',
                             link_style)
        return label

    data = [[_t(h) for h in headers]]
    for r in rows:
        data.append([r["region"], r["species"], r["product_type"],
                     r["product_name"], r["approval_number"],
                     r.get("manufacturer"), r.get("indication"),
                     r.get("dosage_form"), r.get("strength"),
                     r.get("approval_date"), r.get("status"),
                     _src(r)])
    tbl = Table(data, repeatRows=1,
                colWidths=[14*mm, 14*mm, 20*mm, 46*mm, 24*mm, 28*mm, 52*mm,
                           30*mm, 18*mm, 20*mm, 16*mm, 16*mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font, 7),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3F8")]),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))

    if changes:
        story.append(Paragraph(ch_title, styles["Heading2"]))
        cdata = [[_t(h) for h in ch_headers]]
        for ch in changes:
            cdata.append([ch["change_date"], ch["product_name"], ch["region"],
                          ch["approval_number"],
                          type_map.get(ch["change_type"], ch["change_type"]),
                          ch.get("field") or "", ch.get("prev_value") or "",
                          ch.get("new_value") or ""])
        ctbl = Table(cdata, repeatRows=1,
                     colWidths=[20*mm, 40*mm, 14*mm, 24*mm, 18*mm, 22*mm, 50*mm, 50*mm])
        ctbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), font, 7),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7B3F00")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F7F0E8")]),
        ]))
        story.append(ctbl)

    doc.build(story)
    buf.seek(0)
    fname = f"vet_biologics_{date.today().isoformat()}.pdf"
    return send_file(buf, mimetype="application/pdf",
                     as_attachment=True, download_name=fname)


if __name__ == "__main__":
    db.init_db()
    regulatory.setup_logging()
    ingest.ensure_seeded()
    # Clear any historical unread notifications so the FIRST scheduled email
    # only contains genuine new changes (not backlog from manual updates).
    db.mark_notifications_read()
    # Pre-warm the USDA/CVB catalog cache in the background so the first "live"
    # pull is fast (the official PDF is downloaded only once, then cached).
    def _warm_cache():
        try:
            regulatory.fetch_usda_cvb()
            regulatory.log().info("Startup cache warm: USDA catalog ready")
        except Exception as e:  # noqa: BLE001
            regulatory.log().warning("Startup cache warm failed: %s", e)
    threading.Thread(target=_warm_cache, daemon=True).start()
    # start periodic ingestion in background
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    # Default to localhost-only. Set HOST=0.0.0.0 (and expose the port) only
    # when you intentionally want the workbench reachable from the network.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    tz = datetime.now().astimezone().tzinfo
    app.logger.info("Daily auto-update scheduled at 20:00 local time (TZ=%s)", tz)
    app.run(host=host, port=port, debug=False)
