"""寄送 Email（驗證碼）。

設定放在專案資料夾的 email_settings.txt（不會上傳到 GitHub），格式見 email_settings.example.txt。
也可以用同名的環境變數設定（部署到雲端主機時較方便）。
沒有設定時為「測試模式」：不寄信，驗證碼直接顯示在網站畫面上。
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "email_settings.txt")
KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM_NAME")


def load_settings():
    conf = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587", "MAIL_FROM_NAME": "HAN REJUVE"}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip().upper(), v.strip().strip('"').strip("'")
                if k in KEYS and v:
                    conf[k] = v
    for k in KEYS:  # 環境變數優先
        if os.environ.get(k):
            conf[k] = os.environ[k]
    if conf.get("SMTP_PASSWORD"):
        conf["SMTP_PASSWORD"] = conf["SMTP_PASSWORD"].replace(" ", "")  # Google 應用程式密碼常帶空格
    return conf


def is_configured():
    c = load_settings()
    return bool(c.get("SMTP_USER") and c.get("SMTP_PASSWORD"))


def send_mail(to, subject, text, html=None):
    """寄出成功回傳 True；未設定回傳 False；連線或帳密錯誤會丟出例外。"""
    c = load_settings()
    if not (c.get("SMTP_USER") and c.get("SMTP_PASSWORD")):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((c["MAIL_FROM_NAME"], c["SMTP_USER"]))
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    port = int(c["SMTP_PORT"])
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(c["SMTP_HOST"], port, context=ctx, timeout=20) as s:
            s.login(c["SMTP_USER"], c["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(c["SMTP_HOST"], port, timeout=20) as s:
            s.starttls(context=ctx)
            s.login(c["SMTP_USER"], c["SMTP_PASSWORD"])
            s.send_message(msg)
    return True
