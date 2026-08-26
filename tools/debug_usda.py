#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug USDA PDF layout to understand why the parser yields 0 records."""
import io
import re
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)
import regulatory as reg

PDF = os.path.join(ROOT, "data", "usda_catalog.pdf")
with open(PDF, "rb") as f:
    raw = f.read()
print("PDF bytes:", len(raw), "magic:", raw[:4])

import pdfplumber
pdf = pdfplumber.open(io.BytesIO(raw))
print("pages:", len(pdf.pages))

# 1) Look at the section title candidates on each page
section_hits = 0
pcn_hits = 0
for i, page in enumerate(pdf.pages):
    text = page.extract_text() or ""
    for line in text.splitlines():
        s = line.strip()
        if reg._match_usda_section(s):
            section_hits += 1
            if section_hits <= 12:
                print(f"[SEC p{i+1}] {s!r}")
        if reg._PCN_RE.match(s):
            pcn_hits += 1
            if pcn_hits <= 12:
                print(f"[PCN p{i+1}] {s!r}")
print("section_hits:", section_hits, "pcn_hits:", pcn_hits)

# 2) dump raw lines of first 3 pages so we can see real layout
for i in range(min(3, len(pdf.pages))):
    t = pdf.pages[i].extract_text() or ""
    print(f"\n===== PAGE {i+1} (first 1200 chars) =====")
    print(t[:1200])
