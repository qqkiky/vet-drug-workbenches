# -*- coding: utf-8 -*-
"""Sniff the XHR endpoints used by the EMA veterinary medicines portal."""
import json
from playwright.sync_api import sync_playwright

CAPTURED = []


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        pg = b.new_page()

        def on_resp(r):
            u = r.url
            ct = (r.headers.get("content-type") or "")
            if "json" in ct and "medicines" in u.lower():
                CAPTURED.append({"url": u, "status": r.status, "ct": ct})

        pg.on("response", on_resp)
        for url in ["https://medicines.health.europa.eu/veterinary",
                    "https://medicines.health.europa.eu/veterinary/en",
                    "https://medicines.health.europa.eu/veterinary/en/search?searchkeyword="]:
            try:
                pg.goto(url, wait_until="networkidle", timeout=60000)
                print("visited", url, "->", pg.title()[:70])
            except Exception as e:
                print("goto:", url, type(e).__name__, str(e)[:90])
            pg.wait_for_timeout(3000)
            if CAPTURED:
                break

        for c in CAPTURED[:15]:
            print(c["status"], c["ct"][:30], c["url"][:180])
        if not CAPTURED:
            print("no json xhr captured; title =", pg.title()[:120])
        b.close()

    with open("tools/ema_xhr.json", "w", encoding="utf-8") as f:
        json.dump(CAPTURED, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
