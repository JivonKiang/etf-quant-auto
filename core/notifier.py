# -*- coding: utf-8 -*-
"""通知：SMTP 邮件。账号/密码从环境变量读取，避免明文入库。"""
import os
import smtplib
from email.mime.text import MIMEText

from . import config
from .logger import get_logger

log = get_logger()


def send_email(subject, body, html=False, to=None):
    """发送邮件。返回 True/False。未配置 SMTP 环境变量时直接跳过返回 False。"""
    if not config.CONFIG.notify.email_enabled:
        return False

    host = os.environ.get("MAIL_SERVER")
    if not host:
        log.info("未配置 MAIL_SERVER 环境变量，跳过邮件发送")
        return False

    port = int(os.environ.get("MAIL_PORT", "465"))
    user = os.environ.get("MAIL_USERNAME", "")
    pwd = os.environ.get("MAIL_PASSWORD", "")
    to = to or os.environ.get("MAIL_TO", config.CONFIG.notify.to)

    msg = MIMEText(body, "html" if html else "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            s = smtplib.SMTP(host, port, timeout=20)
            s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
        s.quit()
        log.info("邮件已发送 -> %s", to)
        return True
    except Exception as e:
        log.error("邮件发送失败：%s", e)
        return False
