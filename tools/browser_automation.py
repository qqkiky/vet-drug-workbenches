#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器自动化脚本
================
功能：
  1) 打开浏览器（默认可见 headed 模式，可加 --headless 转为无头）
  2) 导航到目标链接（链接在传入前会被「规范+编码+校验」，避免把错误地址丢给浏览器）
  3) 获取并输出页面结果（标题 / HTTP 状态 / 正文摘要）
  4) 对「链接错误 / 未找到相关结果」等异常做处理并给出明确提示

为什么之前会显示“未找到相关结果”
---------------------------------
最常见的根因是「链接地址在拼接/传递时没有被正确编码」：
  - 中文 / 空格 / 特殊字符直接拼进 URL（如 https://x.com/s?q=宠物药 未编码）
  - 协议缺失（http// 少一个斜杠）、多余斜杠、全角符号
  - 查询参数整体未做 urlencode
本脚本在导航前统一修复这些问题，并在加载后检测“未找到”类信号，
一旦命中就当作「链接错误」异常抛出，而不是静默地返回空页面。

用法：
  # 直接打开一个链接（脚本会自动修正）
  python browser_automation.py "https://www.bing.com/search?q=宠物药动态"

  # 用「搜索基址 + 关键词」构造一个被正确编码的链接（最稳）
  python browser_automation.py --search-base "https://www.bing.com/search" --query "宠物药 新药审批"

  # 无头模式 + 把结果存成 json
  python browser_automation.py "https://example.com" --headless --output result.json
"""

import argparse
import json
import re
import sys
import urllib.parse
from typing import Optional


# ---------------------------------------------------------------------------
# 1. 链接规范与校验（修正“链接地址有误”的核心逻辑）
# ---------------------------------------------------------------------------

class LinkError(ValueError):
    """链接无效，或页面未返回有效结果时抛出。"""


# 常见“未找到 / 空结果”信号（命中即视为链接问题）
NOT_FOUND_PATTERNS = [
    "未找到相关结果", "未找到结果", "没有找到相关", "没有找到结果",
    "暂无相关", "无相关结果", "没有匹配的结果", "没有搜到",
    "no results", "no matching results", "0 results found",
    "did not match", "couldn't find", "nothing found",
]


def normalize_url(raw: str, default_scheme: str = "https") -> str:
    """清洗并规范一个可能写错的链接地址，返回可安全导航的 URL。"""
    if not raw:
        raise LinkError("链接地址为空，无法导航。")
    url = raw.strip()
    if not url:
        raise LinkError("链接地址仅含空白，无法导航。")

    # 修复明显笔误
    url = url.replace("：", ":").replace("／", "/").replace("∥", "//")  # 全角符号
    url = re.sub(r'^([a-zA-Z]+):?//+', r'\1://', url)                  # http// -> http://
    url = re.sub(r'(https?://)/+', r'\1', url)                         # https:///x -> https://x

    # 补全协议
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://', url):
        url = f"{default_scheme}://{url}"

    # 解析并对查询参数做正确编码（核心修复点）
    parts = urllib.parse.urlparse(url)
    if parts.query:
        qp = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        encoded_query = urllib.parse.urlencode(qp, doseq=True)
        parts = parts._replace(query=encoded_query)
    # 路径里若含中文/空格也编码
    if any(ord(c) > 127 or c == ' ' for c in parts.path):
        parts = parts._replace(path=urllib.parse.quote(parts.path, safe="/;@&=+$,:"))

    return urllib.parse.urlunparse(parts)


def validate_url(url: str) -> None:
    """导航前最后一道校验：协议与主机名必须合理。"""
    parts = urllib.parse.urlparse(url)
    if not parts.scheme or not parts.netloc:
        raise LinkError(f"链接格式不合法（缺少协议或主机名）：{url}")
    host = parts.netloc.split(':')[0].lower()
    if host not in ("localhost", "127.0.0.1") and '.' not in host:
        raise LinkError(f"主机名不完整（缺少域名，疑似地址写错）：{host}")


def build_search_url(base: str, query: str, param: str = "q") -> str:
    """用「基址 + 关键词」构造一个被正确 URL 编码的搜索链接。"""
    base = base.strip()
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://', base):
        base = "https://" + base
    return base + ("?" if "?" not in base else "&") + urllib.parse.urlencode({param: query})


def detect_not_found(text: str) -> bool:
    """检测页面文本是否包含“未找到相关结果”类信号。"""
    t = (text or "").lower()
    return any(p.lower() in t for p in NOT_FOUND_PATTERNS)


# ---------------------------------------------------------------------------
# 2. 浏览器自动化主流程
# ---------------------------------------------------------------------------

def run(url: str, *, headless: bool, timeout_ms: int,
        output: Optional[str], wait_for: Optional[str]) -> int:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    # ---- 修正链接：规范 + 编码 + 校验 ----
    try:
        fixed = normalize_url(url)
        validate_url(fixed)
    except LinkError as e:
        print(f"[链接错误] {e}", file=sys.stderr)
        return 2

    print(f"[导航] 原始链接 : {url}")
    print(f"[导航] 修正链接 : {fixed}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            resp = page.goto(fixed, wait_until="domcontentloaded")
        except PWTimeout:
            print(f"[链接错误] 页面加载超时（>{timeout_ms}ms）：{fixed}", file=sys.stderr)
            browser.close()
            return 3
        except Exception as e:  # 连接失败 / DNS 失败 / 协议错误等
            print(f"[链接错误] 无法打开页面：{e}", file=sys.stderr)
            browser.close()
            return 4

        status = resp.status if resp else None
        if status and status >= 400:
            print(f"[链接错误] 服务器返回错误状态码 HTTP {status}：{fixed}", file=sys.stderr)

        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=timeout_ms)
            except PWTimeout:
                print(f"[警告] 未在限定时间内等到选择器：{wait_for}", file=sys.stderr)

        title = page.title()
        body_text = page.inner_text("body") or ""
        not_found = detect_not_found(title + "\n" + body_text)
        final_url = page.url

        result = {
            "requested": url,
            "resolved": fixed,
            "final_url": final_url,
            "title": title,
            "http_status": status,
            "not_found": not_found,
            "text_len": len(body_text),
            "text": body_text[:8000],
        }

        print("\n===== 页面结果 =====")
        print(f"最终地址 : {final_url}")
        print(f"标题     : {title}")
        print(f"HTTP状态 : {status}")
        print(f"空结果?  : {'是（检测到“未找到相关结果”类信号）' if not_found else '否'}")
        print(f"正文长度 : {len(body_text)} 字符")
        print("----- 正文摘要（前 2000 字）-----")
        print(body_text[:2000])

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n[已保存结果到] {output}")

        browser.close()

        if not_found:
            print("[链接错误] 页面显示“未找到相关结果”，请检查链接地址是否正确"
                  "（域名 / 路径 / 查询参数）。", file=sys.stderr)
            return 5
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="浏览器自动化：打开浏览器并获取页面结果")
    ap.add_argument("url", nargs="?", help="目标链接（脚本会自动修正编码与格式）")
    ap.add_argument("--search-base", help="搜索基址，配合 --query 构造正确编码的链接")
    ap.add_argument("--query", help="搜索关键词（与 --search-base 搭配）")
    ap.add_argument("--headless", action="store_true", help="无头模式（不弹窗，适合服务器/测试）")
    ap.add_argument("--timeout", type=int, default=30000, help="超时毫秒，默认 30000")
    ap.add_argument("--output", help="把结果保存为 JSON 文件路径")
    ap.add_argument("--wait-for", help="加载完成后等待该 CSS 选择器出现（可选）")
    args = ap.parse_args()

    if args.search_base and args.query:
        target = build_search_url(args.search_base, args.query)
    elif args.url:
        target = args.url
    else:
        ap.error("请提供 url 参数，或同时使用 --search-base 与 --query。")

    return run(target, headless=args.headless, timeout_ms=args.timeout,
               output=args.output, wait_for=args.wait_for)


if __name__ == "__main__":
    sys.exit(main())
