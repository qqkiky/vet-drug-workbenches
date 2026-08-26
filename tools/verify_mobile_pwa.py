#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the deployed mobile PWA: status bar, installability, no console errors."""
import sys
import json
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://0139e7901ac6450c8824425ec9ce15a3.bj7.agentos-app.net"

errors = []
logs = []

with sync_playwright() as p:
    # Mobile viewport (iPhone 12)
    device = p.devices["iPhone 12"]
    browser = p.chromium.launch(channel="msedge", args=["--no-sandbox"])
    context = browser.new_context(**device)
    page = context.new_page()
    page.on("console", lambda m: (logs.append(m.text),
                                  errors.append(m.text) if m.type == "error" else None))
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))

    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)

    # Title
    title = page.title()
    # Sync bar visibility + text
    bar_hidden = page.eval_on_selector("#sync-bar", "el => el.classList.contains('hidden')")
    sync_text = page.eval_on_selector("#sync-text", "el => el.textContent").strip()
    # Manifest installability
    manifest = page.eval_on_selector("link[rel=manifest]",
                                     "el => el.getAttribute('href')")
    sw_registered = page.evaluate("!!navigator.serviceWorker && "
                                  "navigator.serviceWorker.getRegistrations().then(r=>r.length>0)")
    # product count in table
    rows = page.eval_on_selector_all("#tbl-products tbody tr", "els => els.length")

    print(json.dumps({
        "url": URL,
        "title": title,
        "sync_bar_visible": not bar_hidden,
        "sync_text": sync_text,
        "manifest_href": manifest,
        "service_worker_active": bool(sw_registered),
        "product_rows": rows,
        "console_errors": errors[:10],
    }, ensure_ascii=False, indent=2))

    browser.close()

if errors:
    print("RESULT: CONSOLE_ERRORS=%d" % len(errors))
    sys.exit(2)
print("RESULT: OK")
