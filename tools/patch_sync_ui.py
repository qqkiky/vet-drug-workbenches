# -*- coding: utf-8 -*-
"""Inject the daily-sync status bar into static/index.html + styles.css.

Idempotent: re-running replaces the previously injected block instead of
appending a second one. Uses ASCII anchors only, because Chinese literals in
this codebase have proven unreliable as edit anchors.
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "static", "index.html")
CSS = os.path.join(ROOT, "static", "styles.css")

BEGIN = "<!-- SYNC-BAR:BEGIN -->"
END = "<!-- SYNC-BAR:END -->"

BAR = BEGIN + """
  <div id="sync-bar" class="sync-bar hidden">
    <span id="sync-dot" class="sync-dot"></span>
    <span id="sync-text" class="sync-text">正在读取同步状态…</span>
    <button id="sync-toggle" class="sync-link" type="button">详情</button>
  </div>
  <div id="sync-detail" class="sync-detail hidden"></div>
  <div id="sync-update" class="sync-update hidden">
    <span>检测到新的每日数据</span>
    <button id="sync-reload" class="sync-reload" type="button">立即刷新</button>
  </div>
  <script>
  (function () {
    var RESULT = {
      ok:      { cls: "ok",      label: "正常" },
      partial: { cls: "partial", label: "部分成功" },
      failed:  { cls: "failed",  label: "失败" }
    };

    function fmtDate(s) { return (s || "").replace("T", " ").slice(0, 16); }

    function render(st) {
      var bar = document.getElementById("sync-bar");
      if (!bar || !st || !st.last_sync_at) return;
      var meta = RESULT[st.result] || { cls: "partial", label: "未知" };
      var dot = document.getElementById("sync-dot");
      dot.className = "sync-dot " + meta.cls;

      var added = st.today_added != null ? st.today_added : (st.added || 0);
      var parts = ["每日同步 " + fmtDate(st.last_sync_at)];
      parts.push(added > 0 ? ("新增 " + added + " 条") : "无新增");
      if (st.new_recent_count) parts.push("新获批 " + st.new_recent_count + " 条");
      parts.push("在库 " + (st.total || 0) + " 条");
      document.getElementById("sync-text").textContent = parts.join(" · ");
      bar.classList.remove("hidden");

      var box = document.getElementById("sync-detail");
      var html = "";
      if (st.message) html += '<p class="sync-msg">' + st.message + "</p>";
      if (st.sources && st.sources.length) {
        html += '<ul class="sync-src">';
        st.sources.forEach(function (s) {
          html += "<li><span class=\\"sync-dot " + (s.ok ? "ok" : "failed") +
                  '"></span>' + s.label + " — " +
                  (s.ok ? (s.count + " 条记录") : ("不可用" + (s.error ? "：" + s.error : ""))) +
                  "</li>";
        });
        html += "</ul>";
      }
      if (st.new_items && st.new_items.length) {
        html += '<p class="sync-sub">本次新获批（' + st.new_items.length + " 条）</p><ol class=\\"sync-new\\">";
        st.new_items.slice(0, 10).forEach(function (p) {
          html += "<li>" + (p.product_name || "") + " <em>" + (p.region || "") +
                  " · " + (p.approval_date || "") + "</em></li>";
        });
        html += "</ol>";
      }
      if (st.history && st.history.length) {
        html += '<p class="sync-sub">最近同步记录</p><ul class="sync-hist">';
        st.history.slice(0, 7).forEach(function (h) {
          html += "<li>" + h.date + " · 新增 " + (h.added || 0) +
                  " · 变更 " + ((h.updated || 0) + (h.status_change || 0)) +
                  " · " + ((RESULT[h.result] || {}).label || h.result) + "</li>";
        });
        html += "</ul>";
      }
      box.innerHTML = html || "<p class=\\"sync-msg\\">暂无详情</p>";

      var btn = document.getElementById("sync-toggle");
      btn.onclick = function () {
        box.classList.toggle("hidden");
        btn.textContent = box.classList.contains("hidden") ? "详情" : "收起";
      };
    }

    function load() {
      if (window.__SYNC_STATUS__ && window.__SYNC_STATUS__.last_sync_at) {
        render(window.__SYNC_STATUS__);
        return;
      }
      var urls = ["sync_status.json", "/api/sync-status"];
      (function next(i) {
        if (i >= urls.length) return;
        fetch(urls[i] + "?t=" + Date.now(), { cache: "no-store" })
          .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
          .then(render)
          .catch(function () { next(i + 1); });
      })(0);
    }

    // Poll version.json so an installed PWA picks up the daily rebuild without
    // the user having to clear the app cache.
    function watchVersion() {
      var current = window.__BUILD_ID__ || null;
      if (!current) return;
      setInterval(function () {
        fetch("version.json?t=" + Date.now(), { cache: "no-store" })
          .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
          .then(function (v) {
            if (v.build && v.build !== current) {
              document.getElementById("sync-update").classList.remove("hidden");
            }
          })
          .catch(function () {});
      }, 15 * 60 * 1000);
      var rb = document.getElementById("sync-reload");
      if (rb) rb.onclick = function () {
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
          navigator.serviceWorker.getRegistrations().then(function (rs) {
            rs.forEach(function (r) { r.update(); });
            location.reload(true);
          });
        } else { location.reload(true); }
      };
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { load(); watchVersion(); });
    } else { load(); watchVersion(); }
  })();
  </script>
  """ + END


CSS_BEGIN = "/* SYNC-BAR:BEGIN */"
CSS_END = "/* SYNC-BAR:END */"
CSS_BLOCK = CSS_BEGIN + """
.sync-bar{display:flex;align-items:center;gap:8px;padding:8px 14px;margin:0;
  background:#eef4fd;border-bottom:1px solid #d6e3f7;font-size:13px;color:#20364f;}
.sync-bar.hidden,.sync-detail.hidden,.sync-update.hidden{display:none;}
.sync-text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.sync-dot{width:8px;height:8px;border-radius:50%;background:#9aa7b5;flex:0 0 auto;display:inline-block;}
.sync-dot.ok{background:#22a06b;}
.sync-dot.partial{background:#e2a02b;}
.sync-dot.failed{background:#d64545;}
.sync-link{background:none;border:none;color:#1e6fd9;font-size:13px;cursor:pointer;padding:0 2px;flex:0 0 auto;}
.sync-detail{padding:10px 14px;background:#f7fafe;border-bottom:1px solid #e2eaf5;font-size:13px;color:#2b3d52;}
.sync-detail .sync-msg{margin:0 0 6px;}
.sync-detail .sync-sub{margin:10px 0 4px;font-weight:600;color:#1b2c3f;}
.sync-src,.sync-new,.sync-hist{margin:0;padding-left:18px;line-height:1.7;}
.sync-src{list-style:none;padding-left:0;}
.sync-src li{display:flex;align-items:center;gap:6px;}
.sync-new em{color:#6b7b8d;font-style:normal;font-size:12px;}
.sync-update{display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:8px 14px;background:#fff6e5;border-bottom:1px solid #f0dcb4;font-size:13px;color:#6b4c12;}
.sync-reload{background:#1e6fd9;color:#fff;border:none;border-radius:6px;padding:5px 12px;font-size:13px;cursor:pointer;}
@media (max-width:640px){
  .sync-bar{font-size:12px;padding:7px 10px;}
  .sync-text{white-space:normal;}
  .sync-detail{font-size:12px;padding:8px 10px;}
}
""" + CSS_END


def inject(path, begin, end, block, anchor=None):
    src = io.open(path, encoding="utf-8").read()
    if begin in src:
        src = re.sub(re.escape(begin) + r".*?" + re.escape(end), block, src, flags=re.S)
    elif anchor:
        assert anchor in src, "anchor not found in %s" % path
        src = src.replace(anchor, block + "\n\n  " + anchor, 1)
    else:
        src = src.rstrip() + "\n\n" + block + "\n"
    io.open(path, "w", encoding="utf-8").write(src)
    return len(src)


def main():
    n1 = inject(HTML, BEGIN, END, BAR, anchor="<main>")
    n2 = inject(CSS, CSS_BEGIN, CSS_END, CSS_BLOCK)
    print("index.html -> %d bytes, styles.css -> %d bytes" % (n1, n2))


if __name__ == "__main__":
    main()
