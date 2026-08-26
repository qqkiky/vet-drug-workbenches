"""Email digest of pending regulatory changes.

Sends an HTML email summarizing unpublished changes (notified=0) from the
change_log. Sends ONLY when there is at least one pending change — if nothing
changed, nothing is sent (no spam on quiet days). After a successful send,
those rows are marked notified=1.

Configuration (environment variables):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
  MAIL_FROM   (display/from address; defaults to SMTP_USER)
  MAIL_TO     (comma-separated recipients)
  MAIL_DRYRUN=1  -> build & print the email but do not actually send
"""
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import db


LABELS = {
    "NEW": "新增获批", "UPDATED": "信息更新",
    "STATUS_CHANGE": "状态变更", "WITHDRAWN": "已撤回",
}
REGION_LABEL = {"US": "美国 USDA/CVB", "EU": "欧盟 EMA/CVMP"}


def pending():
    return db.get_notifications(only_unread=True, limit=200)


def build_html(changes):
    groups = {k: [] for k in LABELS}
    for c in changes:
        groups.setdefault(c["change_type"], []).append(c)
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = []
    parts.append("<h2>兽用生物制品监管追踪 · 每日更新</h2>")
    parts.append("<p>推送时间：%s</p>" % today)
    parts.append("<p>本次共 <b>%d</b> 项变更：" % len(changes))
    summary = "，".join("%s %d" % (LABELS.get(k, k), len(v))
                        for k, v in groups.items() if v)
    parts.append(summary + "</p>")
    for k in LABELS:
        items = groups.get(k)
        if not items:
            continue
        parts.append("<h3>%s（%d）</h3><ul>" % (LABELS[k], len(items)))
        for c in items:
            name = c.get("product_name") or "（未知产品）"
            region = REGION_LABEL.get(c.get("region"), c.get("region") or "")
            no = c.get("approval_number") or ""
            line = "<li><b>%s</b> · %s" % (name, region)
            if no:
                line += " · 编号 %s" % no
            if c.get("field"):
                line += "（%s：%s → %s）" % (
                    c["field"], c.get("prev_value") or "—", c.get("new_value") or "—")
            line += "</li>"
            parts.append(line)
        parts.append("</ul>")
    parts.append("<hr><p style='color:#888;font-size:12px'>"
                 "本邮件由兽用生物制品监管追踪工作台自动发送。</p>")
    return "".join(parts)


def send_digest(dry_run=None):
    """Send a digest of pending changes. Returns the number of changes sent
    (0 when nothing changed)."""
    changes = pending()
    if not changes:
        print("[notify] 无新变更，跳过邮件推送。")
        return 0
    html = build_html(changes)
    dry = dry_run if dry_run is not None else (os.environ.get("MAIL_DRYRUN") == "1")
    if dry:
        print("[notify][dry-run] 将发送 %d 条变更摘要：" % len(changes))
        print(html)
        return len(changes)
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    to = os.environ.get("MAIL_TO")
    if not (host and user and pwd and to):
        print("[notify][error] 缺少 SMTP 配置（SMTP_HOST/SMTP_USER/"
              "SMTP_PASS/MAIL_TO），无法发送。")
        raise RuntimeError("SMTP 配置缺失")
    port = int(os.environ.get("SMTP_PORT", "465"))
    frm = os.environ.get("MAIL_FROM", user)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "兽用生物制品监管追踪 · %d 项更新" % len(changes)
    msg["From"] = frm
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=ctx) as s:
        s.login(user, pwd)
        s.send_message(msg)
    db.mark_notifications_read()
    print("[notify] 已发送 %d 条变更摘要至 %s" % (len(changes), to))
    return len(changes)


if __name__ == "__main__":
    send_digest()
