#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地移动端 PWA 验证：用 Playwright（Edge）以 iPhone 视口加载 web/，
检查：无控制台报错、manifest/sw/version 可访问、service worker 注册成功、数据渲染。"""
import json
import os
import sys
import threading
import http.server
import socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
PORT = 8731


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    def log_message(self, *a):
        pass


def start_server():
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def main():
    from playwright.sync_api import sync_playwright

    httpd = start_server()
    base = f"http://127.0.0.1:{PORT}/"
    errors = []
    try:
        with sync_playwright() as p:
            iphone = p.devices["iPhone 12"]
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(**iphone)
            page = context.new_page()
            page.on("console", lambda m: errors.append((m.type, m.text)) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(("pageerror", str(e))))
            page.goto(base, wait_until="networkidle")
            page.wait_for_timeout(3500)  # 等 SW 注册 + 初始渲染

            # manifest 可访问且合法
            m = page.evaluate("""async () => {
                const l = document.querySelector('link[rel=manifest]');
                if(!l) return {ok:false, reason:'no manifest link'};
                const r = await fetch(l.href); const j = await r.json();
                return {ok:true, status:r.status, name:j.name, start:j.start_url, icons:(j.icons||[]).length};
            }""")
            # 数据渲染
            reg_rows = page.eval_on_selector_all("#regBody tr", "els => els.length")
            clin_rows = page.eval_on_selector_all("#clinBody tr", "els => els.length")
            # service worker 注册状态
            sw = page.evaluate("""async () => {
                if(!('serviceWorker' in navigator)) return {supported:false};
                try {
                  const reg = await navigator.serviceWorker.getRegistration();
                  return {supported:true, registered: !!reg, controlling: !!navigator.serviceWorker.controller, scope: reg? reg.scope : null};
                } catch(e){ return {supported:true, error:String(e)}; }
            }""")
            # version.json 可访问
            ver = page.evaluate("""async () => {
                const r = await fetch('version.json?_='+Date.now(), {cache:'no-store'});
                const j = await r.json(); return {status:r.status, build:j.build};
            }""")
            # 移动端布局：切换到临床 tab 并搜索“猫”
            page.click("#tabClin")
            page.fill("#clinQ", "猫")
            page.click("#clinSearch")
            page.wait_for_timeout(800)
            clin_cat = page.eval_on_selector_all("#clinBody tr", "els => els.length")

            page.screenshot(path=os.path.join(HERE, "web_verify_mobile.png"), full_page=False)

            print("MANIFEST:", json.dumps(m, ensure_ascii=False))
            print("SW:", json.dumps(sw, ensure_ascii=False))
            print("VERSION:", json.dumps(ver, ensure_ascii=False))
            print("REG_ROWS(page1):", reg_rows, "| CLIN_ROWS(page1):", clin_rows, "| CLIN_猫:", clin_cat)
            print("CONSOLE_ERRORS:", len(errors))
            for e in errors[:20]:
                print("  ", e)
            ok = m.get("ok") and sw.get("supported") and ver.get("status") == 200 and reg_rows > 0
            print("RESULT:", "PASS" if ok else "FAIL")
            browser.close()
            return 0 if ok else 2
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(main())
