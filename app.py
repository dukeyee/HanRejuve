"""HAN REJUVE 線上預約系統

Flask + SQLite。執行：python app.py  然後開啟 http://127.0.0.1:5000
"""
import functools
import io
import tempfile
import zipfile
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time as _systime

# 時區：網站一律使用馬來西亞時間（雲端主機預設多為 UTC，會讓預約時段差 8 小時）。
# 可用環境變數 TZ 改成其他時區；Windows 沒有 tzset，使用電腦本身的時區。
if hasattr(_systime, "tzset"):            # Linux / Mac 主機
    os.environ.setdefault("TZ", "Asia/Kuala_Lumpur")
    _systime.tzset()

from datetime import date, datetime, time, timedelta

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, session, url_for)
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.security import check_password_hash, generate_password_hash

import i18n
import mailer

try:  # 簡體 → 繁體自動轉換
    from opencc import OpenCC
    _s2t = OpenCC("s2t").convert
except ImportError:  # 未安裝時不轉換
    _s2t = None


def to_trad(text):
    return _s2t(text) if (_s2t and text) else text


import sys
for _stream in (sys.stdout, sys.stderr):
    try:  # 避免 Windows 主控台編碼無法顯示中文而當機
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 資料（資料庫、上傳圖片、照片、金鑰）放在 DATA_DIR。
# 雲端主機用環境變數 HAN_DATA_DIR 指到永久硬碟；本機沒設定時就是專案資料夾（和原本一樣）。
DATA_DIR = os.environ.get("HAN_DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get("HAN_DB", os.path.join(DATA_DIR, "hanrejuve.db"))
SECRET_FILE = os.path.join(DATA_DIR, "secret_key.txt")
ADMIN_PW_FILE = os.path.join(DATA_DIR, "admin_initial_password.txt")
DEFAULT_ADMIN_EMAIL = "hanrejuve2026@gmail.com"


def load_secret():
    if os.environ.get("HAN_SECRET"):
        return os.environ["HAN_SECRET"]
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_FILE, encoding="utf-8") as f:
        return f.read().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # 上線（HTTPS）時設定環境變數 HAN_HTTPS=1：登入狀態只透過加密連線傳送
    SESSION_COOKIE_SECURE=os.environ.get("HAN_HTTPS") == "1",
    PREFERRED_URL_SCHEME="https" if os.environ.get("HAN_HTTPS") == "1" else "http",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    MAX_CONTENT_LENGTH=60 * 1024 * 1024,  # 單次上傳合計上限（可一次上傳多張手機照片）
)
MAX_IMAGE_BYTES = 15 * 1024 * 1024       # 單張圖片上限
# 後台上傳的海報：本機在 static/uploads；雲端在永久硬碟的 uploads（網址一樣是 /static/uploads/...）
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads") if DATA_DIR == BASE_DIR else os.path.join(DATA_DIR, "uploads")
# 客人的服務紀錄照片：放在非公開資料夾，只有該客人和管理員能透過網站看到
PRIVATE_PHOTO_DIR = os.environ.get("HAN_PRIVATE_DIR", os.path.join(DATA_DIR, "private_uploads", "booking_photos"))
MAX_PHOTOS_PER_BOOKING = 20
ALLOWED_IMG = {"jpg", "jpeg", "png", "webp", "gif"}

STATUS_LABELS = {
    "pending": "待確認",
    "confirmed": "已確認",
    "completed": "已完成",
    "cancelled": "已取消",
    "no_show": "未到店",
}
ACTIVE_STATUSES = ("pending", "confirmed")
WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]

DEFAULT_SETTINGS = {
    "shop_name": "HAN REJUVE",
    "shop_tagline": "輕醫美 · 抗衰老 · 煥活新生",
    "shop_phone": "",
    "shop_address": "",
    "currency": "RM",
    "open_time": "10:00",
    "close_time": "20:00",
    "slot_interval": "30",       # 分鐘
    "capacity": "2",             # 同一時段可同時服務人數（美容師/床位數）
    "closed_weekdays": "",       # 逗號分隔，0=週一 … 6=週日
    "booking_days_ahead": "0",   # 可預約未來幾天，0 = 不限制
    "booking_notice": "新山區以外的客戶，最少要提前兩個星期預約",  # 預約前跳出的須知，空白 = 不顯示
    "min_advance_hours": "2",    # 最少提前幾小時預約
    "cancel_hours": "24",        # 會員最晚可於幾小時前取消
    "auto_confirm": "0",         # 1=新預約自動確認
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS email_codes (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,      -- ISO 時間
    sent_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES categories(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    duration INTEGER NOT NULL,
    price INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    guest_name TEXT,
    guest_phone TEXT,
    service_id INTEGER NOT NULL REFERENCES services(id),
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    admin_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL DEFAULT 0,          -- 使用此券的體驗價
    image TEXT,                                 -- static/ 底下的路徑（中文海報）
    image_en TEXT,                              -- 英文海報（英文介面時顯示）
    valid_days INTEGER NOT NULL DEFAULT 90,     -- 領取後幾天內有效，0 = 永久
    signup_gift INTEGER NOT NULL DEFAULT 0,     -- 1 = 新會員註冊自動贈送
    once_per_user INTEGER NOT NULL DEFAULT 1,   -- 1 = 每人限領一次
    active INTEGER NOT NULL DEFAULT 1,
    deleted INTEGER NOT NULL DEFAULT 0,         -- 1 = 已刪除（保留給已使用的預約紀錄）
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS coupon_services (
    coupon_id INTEGER NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    PRIMARY KEY (coupon_id, service_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),       -- NULL = 發給所有會員的公告
    kind TEXT NOT NULL DEFAULT 'announcement',  -- announcement / coupon
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    image TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id);
CREATE TABLE IF NOT EXISTS message_reads (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (message_id, user_id)
);
CREATE TABLE IF NOT EXISTS user_coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    coupon_id INTEGER NOT NULL REFERENCES coupons(id),
    status TEXT NOT NULL DEFAULT 'unused',      -- unused / used
    issued_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    expires_at TEXT,                            -- YYYY-MM-DD，NULL = 永久
    used_booking_id INTEGER,
    message_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_user_coupons_user ON user_coupons(user_id);
CREATE TABLE IF NOT EXISTS booking_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_booking_photos ON booking_photos(booking_id);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),   -- 對話所屬的會員
    sender TEXT NOT NULL,                            -- member / admin
    admin_id INTEGER REFERENCES users(id),           -- 回覆的管理員
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    read_by_admin INTEGER NOT NULL DEFAULT 0,
    read_by_member INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);
CREATE TABLE IF NOT EXISTS closed_dates (
    date TEXT PRIMARY KEY,
    reason TEXT NOT NULL DEFAULT ''
);
"""

# 主項目 → 子項目。沒有子項目的主項目會直接成為一個可預約的服務。
# 時長預設 60 分鐘、價格 0（顯示「價格洽詢」），請到後台修改。
SEED_CATALOG = [
    ("免費面診", [], 30),   # 第三個值：每次佔用的分鐘數（沒寫就是 60）
    ("輕抗衰", ["膠原支架", "祛抬頭紋", "祛魚尾紋", "祛川字紋", "淚溝激活", "額頭精雕",
               "V臉", "臉部提升", "祛法令紋", "祛嘴角肉", "雙下巴溶脂"]),
    ("皮膚管理", ["嬰兒水光針", "愛馬仕水光", "凹凸洞", "淡化疤印", "淡化黑斑"]),
    ("身材管理", ["穴位瘦全身", "局部溶脂", "十八穴位", "減啤酒肚", "躺瘦三寶"]),
    ("外泌體生髮", []),
    ("9D黃金炮", []),
    ("AI量子儀", []),
    ("家醫美", ["七日白", "Serena緊緻提升", "貴婦霜", "潔臉凝膠", "醫用面膜"]),
]


def seed_catalog(db):
    for ci, (cat, items, *rest) in enumerate(SEED_CATALOG):
        minutes = rest[0] if rest else 60
        cid = db.execute("INSERT INTO categories(name, sort_order) VALUES (?, ?)", (cat, ci)).lastrowid
        for si, name in enumerate(items or [cat]):
            db.execute("INSERT INTO services(category_id, name, duration, price, sort_order) VALUES (?,?,?,?,?)",
                       (cid, name, minutes, 0, si))


# 預設優惠券（依海報內容建立）。services 以子項目名稱對應。
# 前三張為新人禮（註冊自動贈送）；全部永久有效、每人限領一次。
SEED_COUPONS = [
    dict(name="新粉·體驗卡", price=499, image="img/promo-newfan.jpg", image_en="img/promo-newfan-en.jpg",
         description="打造媽生幼態臉，以下項目任選其中一個：淚溝激活、抬頭紋去皺、激活印堂凹陷、魚尾紋去皺、雙下巴脂肪剝離術。雙人行 RM788。",
         services=["淚溝激活", "祛抬頭紋", "祛川字紋", "祛魚尾紋", "雙下巴溶脂"]),
    dict(name="鑽石嬰兒肌水光煥膚", price=688, image="img/promo-hydra.jpg", image_en="img/promo-hydra-en.jpg",
         description="新客專享・多重功效體驗卡。雙重高效補水美肌護理，煥發水光透亮肌。每人僅限體驗一次。",
         services=["嬰兒水光針"]),
    dict(name="9D黃金炮 新人體驗", price=299, image="img/promo-9d.jpg", image_en="img/promo-9d-en.jpg",
         description="黑科技煥膚・重塑年輕肌。去皺抗衰、補水嫩膚、緊緻提拉。",
         services=["9D黃金炮"]),
    dict(name="無創穴位瘦身", price=788, image="img/promo-acupoint.jpg", image_en="img/promo-acupoint-en.jpg",
         description="精準科技・安全溶脂・塑造自信曲線。一次體驗 RM788｜四次療程 RM2688（一個療程）。送價值 RM988 一次雙下巴溶脂。",
         services=["穴位瘦全身"], signup_gift=0),
]


def seed_coupons(db):
    for c in SEED_COUPONS:
        cid = db.execute(
            "INSERT INTO coupons(name, description, price, image, image_en, valid_days, signup_gift, once_per_user) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (c["name"], c["description"], c["price"], c["image"], c.get("image_en"),
             c.get("valid_days", 0), c.get("signup_gift", 1))).lastrowid
        for sname in c["services"]:
            row = db.execute("SELECT id FROM services WHERE name = ?", (sname,)).fetchone()
            if row:
                db.execute("INSERT OR IGNORE INTO coupon_services(coupon_id, service_id) VALUES (?,?)", (cid, row["id"]))


# ---------------------------------------------------------------- 資料庫
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    # 舊版資料庫升級：services 加上 category_id 欄位
    cols = {r["name"] for r in db.execute("PRAGMA table_info(services)")}
    if "category_id" not in cols:
        db.execute("ALTER TABLE services ADD COLUMN category_id INTEGER REFERENCES categories(id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_services_cat ON services(category_id)")
    if db.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        seed_catalog(db)
    ucols = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
    if "email_verified" not in ucols:
        db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE users SET email_verified = 1")
    # 舊版資料庫升級：bookings 加上優惠券與實際價格欄位
    bcols = {r["name"] for r in db.execute("PRAGMA table_info(bookings)")}
    if "user_coupon_id" not in bcols:
        db.execute("ALTER TABLE bookings ADD COLUMN user_coupon_id INTEGER")
    if "final_price" not in bcols:
        db.execute("ALTER TABLE bookings ADD COLUMN final_price INTEGER")
    if "service_note" not in bcols:   # 服務紀錄（客人看得到）
        db.execute("ALTER TABLE bookings ADD COLUMN service_note TEXT NOT NULL DEFAULT ''")
    ccols = {r["name"] for r in db.execute("PRAGMA table_info(coupons)")}
    if "deleted" not in ccols:
        db.execute("ALTER TABLE coupons ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
    if "image_en" not in ccols:
        db.execute("ALTER TABLE coupons ADD COLUMN image_en TEXT")
        for c in SEED_COUPONS:
            db.execute("UPDATE coupons SET image_en = ? WHERE image = ? AND image_en IS NULL", (c["image_en"], c["image"]))
    # 新人體驗券只建立一次（之後管理員刪除也不會再自動出現）
    if not db.execute("SELECT 1 FROM settings WHERE key = 'coupons_seeded'").fetchone():
        if db.execute("SELECT COUNT(*) FROM coupons").fetchone()[0] == 0:
            seed_coupons(db)
        db.execute("INSERT INTO settings(key, value) VALUES ('coupons_seeded', '1')")
    if db.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0] == 0:
        env_pw = os.environ.get("HAN_ADMIN_PASSWORD", "").strip()
        pw = env_pw or secrets.token_urlsafe(9)
        db.execute(
            "INSERT INTO users(name, phone, email, password_hash, is_admin, email_verified) VALUES (?,?,?,?,1,1)",
            ("管理員", "", os.environ.get("HAN_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower(), generate_password_hash(pw)),
        )
        if env_pw:
            print("[HAN REJUVE] 已建立管理員帳號（密碼為環境變數 HAN_ADMIN_PASSWORD）")
            db.close()
            return
        with open(ADMIN_PW_FILE, "w", encoding="utf-8") as f:
            f.write(
                "HAN REJUVE 初始管理員帳號\n"
                f"Email：{DEFAULT_ADMIN_EMAIL}\n"
                f"密碼：{pw}\n\n"
                "請登入後到「我的帳號」修改密碼，然後刪除此檔案。\n"
            )
        print(f"[HAN REJUVE] 已建立管理員帳號，登入資料請見 {ADMIN_PW_FILE}")
    db.close()


def get_settings():
    if "settings" not in g:
        rows = get_db().execute("SELECT key, value FROM settings").fetchall()
        s = dict(DEFAULT_SETTINGS)
        s.update({r["key"]: r["value"] for r in rows})
        g.settings = s
    return g.settings


# ---------------------------------------------------------------- 工具
def to_min(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def to_hm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_date(s):
    try:
        return datetime.strptime(s or "", "%Y-%m-%d").date()
    except ValueError:
        return None


def closed_weekdays(s):
    return {int(x) for x in s["closed_weekdays"].split(",") if x.strip().isdigit()}


def date_closed_reason(d):
    """回傳公休原因；營業日回傳 None。"""
    s = get_settings()
    if d.weekday() in closed_weekdays(s):
        return f"每週{WEEKDAY_LABELS[d.weekday()]}公休"
    row = get_db().execute("SELECT reason FROM closed_dates WHERE date = ?", (d.isoformat(),)).fetchone()
    if row:
        return row["reason"] or "店休日"
    return None


def compute_slots(service, d, for_admin=False, exclude_booking_id=None):
    """計算某服務在某日的所有時段及是否可預約。"""
    s = get_settings()
    today = date.today()
    if date_closed_reason(d):
        return []
    if not for_admin:
        days_ahead = int(s["booking_days_ahead"] or 0)
        if d < today or (days_ahead > 0 and d > today + timedelta(days=days_ahead)):
            return []
    open_m, close_m = to_min(s["open_time"]), to_min(s["close_time"])
    step = max(5, int(s["slot_interval"]))
    cap = max(1, int(s["capacity"]))
    dur = int(service["duration"])

    rows = get_db().execute(
        f"SELECT id, start_time, end_time FROM bookings WHERE date = ? AND status IN ({','.join('?' * len(ACTIVE_STATUSES))})",
        (d.isoformat(), *ACTIVE_STATUSES),
    ).fetchall()
    busy = [(to_min(r["start_time"]), to_min(r["end_time"])) for r in rows if r["id"] != exclude_booking_id]

    now = datetime.now()
    earliest = now if for_admin else now + timedelta(hours=float(s["min_advance_hours"]))

    slots = []
    t = open_m
    while t + dur <= close_m:
        start_dt = datetime.combine(d, time(t // 60, t % 60))
        end = t + dur
        # 區間內最大同時預約數
        points = [t] + [b0 for b0, _ in busy if t < b0 < end]
        peak = max(sum(1 for b0, b1 in busy if b0 <= p < b1) for p in points)
        available = start_dt >= earliest and peak < cap
        slots.append({"time": to_hm(t), "end": to_hm(end), "available": available,
                      "remaining": max(0, cap - peak)})
        t += step
    return slots


def create_booking(service_id, d, start, user_id=None, guest_name=None, guest_phone=None,
                   note="", for_admin=False, status=None, user_coupon_id=None):
    """在交易內再次檢查時段與優惠券，避免重複預約或重複用券。回傳 (booking_id, 錯誤訊息)。"""
    db = get_db()
    service = db.execute(
        "SELECT s.*, COALESCE(c.active, 1) AS cat_active FROM services s "
        "LEFT JOIN categories c ON c.id = s.category_id WHERE s.id = ?", (service_id,)).fetchone()
    if not service or ((not service["active"] or not service["cat_active"]) and not for_admin):
        return None, "找不到此服務項目"
    db.execute("BEGIN IMMEDIATE")
    try:
        slots = compute_slots(service, d, for_admin=for_admin)
        slot = next((x for x in slots if x["time"] == start), None)
        if not slot or not slot["available"]:
            db.execute("ROLLBACK")
            return None, "此時段已無法預約，請選擇其他時間"
        final_price = None
        if user_coupon_id:
            uc = usable_coupon(user_coupon_id, user_id, service_id)
            if not uc:
                db.execute("ROLLBACK")
                return None, "此優惠券無法用於這個項目，或已使用／已過期"
            final_price = uc["price"]
        if status is None:
            status = "confirmed" if get_settings()["auto_confirm"] == "1" else "pending"
        cur = db.execute(
            """INSERT INTO bookings(user_id, guest_name, guest_phone, service_id, date,
                   start_time, end_time, status, note, user_coupon_id, final_price)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, guest_name, guest_phone, service_id, d.isoformat(), start, slot["end"], status, note,
             user_coupon_id or None, final_price),
        )
        if user_coupon_id:
            db.execute("UPDATE user_coupons SET status = 'used', used_booking_id = ? WHERE id = ?",
                       (cur.lastrowid, user_coupon_id))
        db.execute("COMMIT")
        return cur.lastrowid, None
    except Exception:
        db.execute("ROLLBACK")
        raise


def load_catalog(active_only=True):
    """回傳分類列表，每個分類帶有 services。單一項目且同名的分類標記為 single（直接可選，不用展開）。"""
    db = get_db()
    where = " WHERE active = 1" if active_only else ""
    cats = [dict(r, services=[]) for r in db.execute(f"SELECT * FROM categories{where} ORDER BY sort_order, id")]
    by_id = {c["id"]: c for c in cats}
    other = {"id": None, "name": "其他", "description": "", "active": 1, "sort_order": 9999, "services": []}
    for r in db.execute(f"SELECT * FROM services{where} ORDER BY sort_order, id"):
        s = dict(r)
        if s["category_id"] in by_id:
            by_id[s["category_id"]]["services"].append(s)
        elif s["category_id"] is None or not active_only:
            other["services"].append(s)
    if other["services"]:
        cats.append(other)
    for c in cats:
        c["single"] = len(c["services"]) == 1 and c["services"][0]["name"] == c["name"]
        c["ids"] = [s["id"] for s in c["services"]]
        for s in c["services"]:
            s["full_name"] = s["name"] if (c["single"] or c["id"] is None) else f"{c['name']} · {s['name']}"
    return [c for c in cats if c["services"]] if active_only else cats


SERVICE_FULL_NAME = "CASE WHEN c.name IS NULL OR c.name = s.name THEN s.name ELSE c.name || ' · ' || s.name END"

BOOKING_SELECT = f"""
SELECT b.*,
       {SERVICE_FULL_NAME} AS service_name,
       COALESCE(b.final_price, s.price) AS price, s.price AS list_price, s.duration,
       cp.name AS coupon_name,
       COALESCE(u.name, b.guest_name) AS customer_name,
       COALESCE(u.phone, b.guest_phone) AS customer_phone,
       u.email AS customer_email
FROM bookings b
JOIN services s ON s.id = b.service_id
LEFT JOIN categories c ON c.id = s.category_id
LEFT JOIN users u ON u.id = b.user_id
LEFT JOIN user_coupons uc ON uc.id = b.user_coupon_id
LEFT JOIN coupons cp ON cp.id = uc.coupon_id
"""


# ---------------------------------------------------------------- 優惠券 / 收件箱
def coupon_services_map(coupon_ids):
    """{coupon_id: [{"id":..., "name": 子項目名稱}]}"""
    if not coupon_ids:
        return {}
    q = ",".join("?" * len(coupon_ids))
    rows = get_db().execute(
        f"SELECT cs.coupon_id, s.id, s.name AS name FROM coupon_services cs "
        f"JOIN services s ON s.id = cs.service_id LEFT JOIN categories c ON c.id = s.category_id "
        f"WHERE cs.coupon_id IN ({q}) ORDER BY c.sort_order, s.sort_order", list(coupon_ids)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["coupon_id"], []).append({"id": r["id"], "name": r["name"]})
    return out


def coupon_state(uc):
    if uc["status"] == "used":
        return "used"
    if uc["expires_at"] and uc["expires_at"] < date.today().isoformat():
        return "expired"
    return "usable"


def user_coupons_for(user_id, where="", params=()):
    rows = get_db().execute(
        "SELECT uc.*, c.name, c.description, c.price, c.image, c.image_en FROM user_coupons uc "
        "JOIN coupons c ON c.id = uc.coupon_id WHERE uc.user_id = ? " + where +
        " ORDER BY uc.issued_at DESC, uc.id DESC", (user_id, *params)).fetchall()
    smap = coupon_services_map({r["coupon_id"] for r in rows})
    out = []
    for r in rows:
        d = dict(r)
        d["services"] = smap.get(r["coupon_id"], [])
        d["state"] = coupon_state(r)
        out.append(d)
    return out


def usable_coupon(user_coupon_id, user_id, service_id):
    db = get_db()
    uc = db.execute("SELECT uc.*, c.price FROM user_coupons uc JOIN coupons c ON c.id = uc.coupon_id "
                    "WHERE uc.id = ? AND uc.user_id = ?", (user_coupon_id, user_id)).fetchone()
    if not uc or coupon_state(uc) != "usable":
        return None
    if not db.execute("SELECT 1 FROM coupon_services WHERE coupon_id = ? AND service_id = ?",
                      (uc["coupon_id"], service_id)).fetchone():
        return None
    return uc


def issue_coupon(coupon, user_id, message_id=None):
    """發一張券給會員；每人限領一次且已領過時回傳 None。"""
    db = get_db()
    if coupon["once_per_user"] and db.execute(
            "SELECT 1 FROM user_coupons WHERE user_id = ? AND coupon_id = ?", (user_id, coupon["id"])).fetchone():
        return None
    exp = (date.today() + timedelta(days=coupon["valid_days"])).isoformat() if coupon["valid_days"] else None
    return db.execute("INSERT INTO user_coupons(user_id, coupon_id, expires_at, message_id) VALUES (?,?,?,?)",
                      (user_id, coupon["id"], exp, message_id)).lastrowid


def send_message(user_id, title, body="", image=None, kind="announcement"):
    return get_db().execute("INSERT INTO messages(user_id, kind, title, body, image) VALUES (?,?,?,?,?)",
                            (user_id, kind, title, body, image)).lastrowid


DEFAULT_DURATION = 60      # 每個服務項目佔用的時段長度（分鐘）
CODE_TTL_MIN = 10          # 驗證碼有效分鐘
CODE_RESEND_SEC = 60       # 重寄冷卻秒數
CODE_MAX_ATTEMPTS = 5      # 最多輸錯次數


def _code_hash(user_id, code):
    return hmac.new(app.config["SECRET_KEY"].encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def resend_wait(user_id):
    """距離可以重寄還要幾秒；0 = 可以寄。"""
    row = get_db().execute("SELECT sent_at FROM email_codes WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return 0
    passed = (datetime.now() - datetime.fromisoformat(row["sent_at"])).total_seconds()
    return max(0, int(CODE_RESEND_SEC - passed))


def send_verification_code(user):
    """產生並寄出驗證碼。回傳 'sent' | 'dev'（未設定寄信，測試模式）| 'error'。"""
    code = f"{secrets.randbelow(1000000):06d}"
    now = datetime.now()
    get_db().execute(
        "INSERT OR REPLACE INTO email_codes(user_id, code_hash, expires_at, sent_at, attempts) VALUES (?,?,?,?,0)",
        (user["id"], _code_hash(user["id"], code), (now + timedelta(minutes=CODE_TTL_MIN)).isoformat(), now.isoformat()))
    if not mailer.is_configured():
        session["dev_code"] = code
        print(f"[HAN REJUVE] 測試模式驗證碼 {user['email']}: {code}")
        return "dev"
    session.pop("dev_code", None)
    shop = get_settings()["shop_name"]
    en = is_english()
    subject = f"{shop} verification code: {code}" if en else f"{shop} 驗證碼：{code}"
    if en:
        text = (f"Hi {user['name']},\n\nYour verification code is {code}\n"
                f"It expires in {CODE_TTL_MIN} minutes.\n\n"
                f"If you did not sign up at {shop}, please ignore this email.\n")
    else:
        text = (f"{user['name']} 您好：\n\n您的驗證碼是 {code}\n"
                f"{CODE_TTL_MIN} 分鐘內有效。\n\n"
                f"如果您沒有註冊 {shop} 會員，請忽略這封信。\n")
    html = render_template("email/verify_code.html", user=user, code=code, minutes=CODE_TTL_MIN, en=en)
    try:
        mailer.send_mail(user["email"], subject, text, html)
        return "sent"
    except Exception as e:  # 帳密錯誤、連線失敗等
        app.logger.error("寄送驗證碼失敗 %s: %s", user["email"], e)
        return "error"


def check_verification_code(user_id, code):
    """回傳 'ok' | 'wrong' | 'expired' | 'locked'。"""
    db = get_db()
    row = db.execute("SELECT * FROM email_codes WHERE user_id = ?", (user_id,)).fetchone()
    if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now():
        return "expired"
    if row["attempts"] >= CODE_MAX_ATTEMPTS:
        return "locked"
    if hmac.compare_digest(row["code_hash"], _code_hash(user_id, code)):
        db.execute("DELETE FROM email_codes WHERE user_id = ?", (user_id,))
        return "ok"
    db.execute("UPDATE email_codes SET attempts = attempts + 1 WHERE user_id = ?", (user_id,))
    return "locked" if row["attempts"] + 1 >= CODE_MAX_ATTEMPTS else "wrong"


def give_signup_gifts(user_id):
    db = get_db()
    gifts = db.execute("SELECT * FROM coupons WHERE signup_gift = 1 AND active = 1 AND deleted = 0 ORDER BY id").fetchall()
    if not gifts:
        return 0
    shop = get_settings()["shop_name"]
    mid = send_message(user_id, f"歡迎加入 {shop}！送你 {len(gifts)} 張新人體驗券",
                       "感謝你註冊成為會員，以下是專屬新人體驗券。預約時選擇優惠券即可享有體驗價。", kind="coupon")
    return sum(1 for c in gifts if issue_coupon(c, user_id, mid))


def release_coupon(booking_id):
    """預約取消時退回優惠券。"""
    get_db().execute("UPDATE user_coupons SET status = 'unused', used_booking_id = NULL "
                     "WHERE used_booking_id = ?", (booking_id,))


def inbox_query(user_id):
    return ("SELECT m.*, (r.user_id IS NOT NULL) AS is_read FROM messages m "
            "LEFT JOIN message_reads r ON r.message_id = m.id AND r.user_id = ? "
            "WHERE m.user_id = ? OR m.user_id IS NULL", (user_id, user_id))


def unread_count(user_id):
    sql, params = inbox_query(user_id)
    return get_db().execute(f"SELECT COUNT(*) FROM ({sql}) WHERE is_read = 0", params).fetchone()[0]


def _check_image(file):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMG:
        raise ValueError("圖片只接受 JPG、PNG、WEBP、GIF 格式")
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_IMAGE_BYTES:
        raise ValueError("單張圖片請小於 15MB")
    return "jpg" if ext == "jpeg" else ext


def save_private_photo(file):
    """儲存服務紀錄照片到非公開資料夾，回傳檔名。"""
    ext = _check_image(file)
    os.makedirs(PRIVATE_PHOTO_DIR, exist_ok=True)
    name = f"{secrets.token_hex(12)}.{ext}"
    file.save(os.path.join(PRIVATE_PHOTO_DIR, name))
    return name


def booking_photos_map(booking_ids):
    if not booking_ids:
        return {}
    q = ",".join("?" * len(booking_ids))
    out = {}
    for r in get_db().execute(f"SELECT * FROM booking_photos WHERE booking_id IN ({q}) ORDER BY id", list(booking_ids)):
        out.setdefault(r["booking_id"], []).append(dict(r))
    return out


def save_upload(file):
    """儲存上傳的圖片，回傳 static/ 底下的路徑；沒有檔案回傳 None。"""
    if not file or not file.filename:
        return None
    ext = _check_image(file)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{secrets.token_hex(8)}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, name))
    return "uploads/" + name


# ---------------------------------------------------------------- 驗證 / CSRF
def current_user():
    if "user" not in g:
        uid = session.get("uid")
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone() if uid else None
    return g.user


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        u = current_user()
        if not u:
            flash("請先登入會員", "info")
            return redirect(url_for("login", next=request.full_path))
        if not u["email_verified"] and not u["is_admin"]:
            return redirect(url_for("verify_email"))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        u = current_user()
        if not u:
            return redirect(url_for("login", next=request.full_path))
        if not u["is_admin"]:
            abort(403)
        return view(*a, **kw)
    return wrapped


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.before_request
def check_csrf():
    if request.method == "POST":
        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("_csrf"):
            abort(400, "表單已過期，請重新整理頁面後再試")


NO_CONVERT_FIELDS = {"_csrf", "password", "password2", "old", "new", "new2", "email"}


@app.before_request
def convert_form_to_traditional():
    """全站以繁體中文為主：表單送出的文字（公告、服務名稱、備註、姓名等）自動轉成繁體。"""
    if request.method == "POST" and _s2t and request.form:
        items = [(k, v if k in NO_CONVERT_FIELDS else to_trad(v)) for k, v in request.form.items(multi=True)]
        request.__dict__["form"] = ImmutableMultiDict(items)


def reset_session():
    """登入／登出時清除 session，但保留語言設定。"""
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang


def is_english():
    return session.get("lang") == "en"


@app.route("/lang/<code>")
def set_lang(code):
    if code in ("zh", "en"):
        session["lang"] = code
    return redirect(safe_next(request.args.get("next")) or url_for("index"))


@app.after_request
def apply_language(resp):
    """英文模式：頁面送出前翻譯介面文字（表單欄位的值不翻譯）。"""
    if (is_english() and resp.mimetype == "text/html" and not resp.direct_passthrough
            and resp.status_code != 304):
        resp.set_data(i18n.translate_html(resp.get_data(as_text=True)))
    return resp


@app.context_processor
def inject_globals():
    u = current_user()
    return {
        "lang": "en" if is_english() else "zh",
        "i18n_js": i18n.js_dict() if is_english() else {},
        "csrf_token": csrf_token,
        "current_user": u,
        "unread": unread_count(u["id"]) if u else 0,
        "chat_unread": chat_unread_count(u) if u else 0,
        "S": get_settings(),
        "STATUS_LABELS": STATUS_LABELS,
        "WEEKDAY_LABELS": WEEKDAY_LABELS,
        "now": datetime.now(),
    }


@app.template_filter("weekday")
def weekday_filter(ds):
    d = parse_date(ds)
    return WEEKDAY_LABELS[d.weekday()] if d else ""


@app.template_filter("money")
def money_filter(v):
    if not v:
        return "價格洽詢"
    return f"{get_settings()['currency']}{int(v):,}"


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
MY_MOBILE_RE = re.compile(r"^1(1\d{8}|[02-9]\d{7})$")  # 011 為 8 碼，其餘 01X 為 7 碼


def valid_email(email):
    return bool(EMAIL_RE.match(email or ""))


def normalize_my_phone(raw):
    """馬來西亞手機號碼 → +60XXXXXXXXX；格式不符回傳 None。
    接受 012-345 6789、0123456789、+60 12-345 6789、60123456789 等寫法。"""
    s = re.sub(r"[\s\-().]", "", raw or "")
    for prefix in ("+60", "60", "0"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return "+60" + s if MY_MOBILE_RE.match(s) else None


@app.template_filter("phone")
def phone_filter(p):
    """+60123456789 → +60 12-345 6789；+601123456789 → +60 11-2345 6789"""
    if p and p.startswith("+60") and MY_MOBILE_RE.match(p[3:]):
        n = p[3:]
        return f"+60 {n[:2]}-{n[2:-4]} {n[-4:]}"
    return p or ""


PHONE_ERROR = "手機號碼格式不正確，請輸入馬來西亞手機號碼，例如 12-345 6789"


def safe_next(url):
    return url if url and url.startswith("/") and not url.startswith("//") else None


# ---------------------------------------------------------------- 會員前台
@app.route("/")
def index():
    return render_template("index.html", catalog=load_catalog())


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("index"))
    form = request.form
    if request.method == "POST":
        name = form.get("name", "").strip()
        phone = normalize_my_phone(form.get("phone", ""))
        email = form.get("email", "").strip().lower()
        pw = form.get("password", "")
        error = None
        if not name or not form.get("phone", "").strip() or not email:
            error = "請填寫所有欄位"
        elif not valid_email(email):
            error = "Email 格式不正確，例如 name@gmail.com"
        elif not phone:
            error = PHONE_ERROR
        elif get_db().execute("SELECT 1 FROM users WHERE phone = ?", (phone,)).fetchone():
            error = "此手機號碼已註冊，請直接登入"
        elif len(pw) < 6:
            error = "密碼至少需要 6 個字元"
        elif pw != form.get("password2", ""):
            error = "兩次輸入的密碼不一致"
        elif get_db().execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            error = "此 Email 已註冊，請直接登入"
        if error:
            flash(error, "error")
        else:
            cur = get_db().execute(
                "INSERT INTO users(name, phone, email, password_hash) VALUES (?,?,?,?)",
                (name, phone, email, generate_password_hash(pw)),
            )
            reset_session()
            session.permanent = True
            session["uid"] = cur.lastrowid
            nxt = safe_next(request.args.get("next"))
            if nxt:
                session["after_verify"] = nxt
            user = get_db().execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
            result = send_verification_code(user)
            if result == "error":
                flash("驗證信寄送失敗，請稍後按「重新寄送」再試一次", "error")
            return redirect(url_for("verify_email"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone() if valid_email(email) else None
        if user and check_password_hash(user["password_hash"], pw):
            reset_session()
            session.permanent = True
            session["uid"] = user["id"]
            nxt = safe_next(request.args.get("next"))
            if user["is_admin"]:
                return redirect(nxt or url_for("admin_dashboard"))
            if not user["email_verified"]:
                if nxt:
                    session["after_verify"] = nxt
                return redirect(url_for("verify_email"))
            return redirect(nxt or url_for("my_bookings"))
        flash("Email 或密碼錯誤", "error")
    return render_template("login.html", email=request.form.get("email", ""))


@app.route("/logout", methods=["POST"])
def logout():
    reset_session()
    flash("已登出", "info")
    return redirect(url_for("index"))


@app.route("/verify", methods=["GET", "POST"])
def verify_email():
    """註冊後輸入 Email 驗證碼；可重寄、可修改填錯的 Email。"""
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    if u["email_verified"]:
        return redirect(url_for("my_bookings"))
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "verify":
            code = re.sub(r"\D", "", request.form.get("code", ""))
            result = check_verification_code(u["id"], code) if len(code) == 6 else "wrong"
            if result == "ok":
                db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (u["id"],))
                session.pop("dev_code", None)
                gifts = give_signup_gifts(u["id"])
                flash(f"Email 驗證成功，歡迎加入 {get_settings()['shop_name']}，{u['name']}！"
                      + (f"已送你 {gifts} 張新人體驗券，請到「收件箱」查看。" if gifts else ""), "success")
                nxt = session.pop("after_verify", None)
                return redirect(nxt or (url_for("inbox") if gifts else url_for("book")))
            flash({"wrong": "驗證碼不正確，請再確認一次",
                   "expired": "驗證碼已過期，請按「重新寄送」",
                   "locked": "輸錯太多次，請按「重新寄送」取得新的驗證碼"}[result], "error")
        elif action == "resend":
            wait = resend_wait(u["id"])
            if wait:
                flash(f"請等 {wait} 秒後再重新寄送", "info")
            else:
                result = send_verification_code(u)
                flash("驗證信寄送失敗，請稍後再試，或聯絡我們" if result == "error" else "已重新寄送驗證碼",
                      "error" if result == "error" else "success")
        elif action == "change_email":
            email = request.form.get("email", "").strip().lower()
            if not valid_email(email):
                flash("Email 格式不正確，例如 name@gmail.com", "error")
            elif email == u["email"].lower():
                flash("這就是目前的 Email", "info")
            elif db.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (email, u["id"])).fetchone():
                flash("此 Email 已註冊，請直接登入", "error")
            elif resend_wait(u["id"]):
                flash(f"請等 {resend_wait(u['id'])} 秒後再修改", "info")
            else:
                db.execute("UPDATE users SET email = ? WHERE id = ?", (email, u["id"]))
                u = db.execute("SELECT * FROM users WHERE id = ?", (u["id"],)).fetchone()
                g.user = u
                result = send_verification_code(u)
                flash("Email 已更新，驗證碼已寄到新信箱" if result != "error" else "Email 已更新，但驗證信寄送失敗，請稍後重新寄送",
                      "success" if result != "error" else "error")
        return redirect(url_for("verify_email"))
    if not db.execute("SELECT 1 FROM email_codes WHERE user_id = ?", (u["id"],)).fetchone():
        send_verification_code(u)  # 從未寄過驗證碼時自動寄一封；過期的請客人按「重新寄送」
    return render_template("verify.html", wait=resend_wait(u["id"]), dev_code=session.get("dev_code"),
                           minutes=CODE_TTL_MIN, mail_ready=mailer.is_configured())


@app.route("/book", methods=["GET", "POST"])
@login_required
def book():
    db = get_db()
    s = get_settings()
    if request.method == "POST":
        d = parse_date(request.form.get("date"))
        sid = request.form.get("service_id", type=int)
        start = request.form.get("time", "")
        note = request.form.get("note", "").strip()[:500]
        if not d or not sid or not start:
            flash("請選擇服務、日期與時間", "error")
        elif s["booking_notice"].strip() and request.form.get("confirm_notice") != "1":
            flash("請先閱讀預約須知並勾選確認", "error")
        else:
            bid, err = create_booking(sid, d, start, user_id=current_user()["id"], note=note,
                                      user_coupon_id=request.form.get("user_coupon_id", type=int))
            if err:
                flash(err, "error")
            else:
                flash("預約成功！" + ("已為您確認時段。" if s["auto_confirm"] == "1" else "我們確認後會再與您聯繫。"), "success")
                return redirect(url_for("my_bookings"))
    today = date.today()
    coupons = [c for c in user_coupons_for(current_user()["id"], "AND uc.status = 'unused'")
               if c["state"] == "usable" and c["services"]]
    pre_coupon = request.form.get("user_coupon_id", type=int) or request.args.get("coupon", type=int)
    preselect = request.form.get("service_id", type=int) or request.args.get("service", type=int)
    pc = next((c for c in coupons if c["id"] == pre_coupon), None)
    if pc and not preselect and len(pc["services"]) == 1:
        preselect = pc["services"][0]["id"]
    return render_template(
        "book.html", catalog=load_catalog(),
        min_date=today.isoformat(),
        max_date=(today + timedelta(days=int(s["booking_days_ahead"]))).isoformat()
                 if int(s["booking_days_ahead"] or 0) > 0 else "",
        preselect=preselect, coupons=coupons, pre_coupon=pc["id"] if pc else None,
        **closed_info(),
    )


def closed_info():
    rows = get_db().execute("SELECT date FROM closed_dates WHERE date >= ?", (date.today().isoformat(),)).fetchall()
    return {"closed_weekdays": sorted(closed_weekdays(get_settings())),
            "closed_dates": [r["date"] for r in rows]}


@app.route("/api/slots")
def api_slots():
    u = current_user()
    for_admin = bool(u and u["is_admin"] and request.args.get("admin") == "1")
    d = parse_date(request.args.get("date"))
    sid = request.args.get("service_id", type=int)
    service = get_db().execute("SELECT * FROM services WHERE id = ?", (sid,)).fetchone() if sid else None
    if not d or not service:
        return jsonify({"ok": False, "message": "參數錯誤"}), 400
    reason = date_closed_reason(d)
    if reason:
        return jsonify({"ok": True, "closed": True, "slots": [],
                        "message": i18n.translate_text(reason) if is_english() else reason})
    slots = compute_slots(service, d, for_admin=for_admin)
    return jsonify({"ok": True, "closed": False, "slots": slots})


@app.route("/my")
@login_required
def my_bookings():
    rows = get_db().execute(
        BOOKING_SELECT + " WHERE b.user_id = ? ORDER BY b.date DESC, b.start_time DESC",
        (current_user()["id"],),
    ).fetchall()
    now_key = datetime.now().strftime("%Y-%m-%d %H:%M")
    cancel_h = float(get_settings()["cancel_hours"])
    upcoming, past = [], []
    for r in rows:
        key = f"{r['date']} {r['start_time']}"
        item = dict(r)
        start_dt = datetime.strptime(key, "%Y-%m-%d %H:%M")
        item["can_cancel"] = r["status"] in ACTIVE_STATUSES and start_dt - datetime.now() >= timedelta(hours=cancel_h)
        (upcoming if key >= now_key and r["status"] in ACTIVE_STATUSES else past).append(item)
    upcoming.reverse()
    photos = booking_photos_map([r["id"] for r in rows])
    return render_template("my_bookings.html", upcoming=upcoming, past=past, photos=photos)


@app.route("/my/<int:bid>/cancel", methods=["POST"])
@login_required
def cancel_booking(bid):
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id = ? AND user_id = ?", (bid, current_user()["id"])).fetchone()
    if not b:
        abort(404)
    start_dt = datetime.strptime(f"{b['date']} {b['start_time']}", "%Y-%m-%d %H:%M")
    hours = float(get_settings()["cancel_hours"])
    if b["status"] not in ACTIVE_STATUSES:
        flash("此預約無法取消", "error")
    elif start_dt - datetime.now() < timedelta(hours=hours):
        flash(f"預約前 {hours:g} 小時內無法線上取消，請直接來電", "error")
    else:
        db.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (bid,))
        release_coupon(bid)
        flash("預約已取消" + ("，優惠券已退回「我的優惠券」" if b["user_coupon_id"] else ""), "success")
    return redirect(url_for("my_bookings"))


# ---------------------------------------------------------------- 收件箱 / 我的優惠券
@app.route("/inbox")
@login_required
def inbox():
    sql, params = inbox_query(current_user()["id"])
    rows = get_db().execute(sql + " ORDER BY m.created_at DESC, m.id DESC LIMIT 200", params).fetchall()
    return render_template("inbox.html", rows=rows)


@app.route("/inbox/<int:mid>")
@login_required
def inbox_message(mid):
    db = get_db()
    uid = current_user()["id"]
    m = db.execute("SELECT * FROM messages WHERE id = ? AND (user_id = ? OR user_id IS NULL)", (mid, uid)).fetchone()
    if not m:
        abort(404)
    db.execute("INSERT OR IGNORE INTO message_reads(message_id, user_id) VALUES (?, ?)", (mid, uid))
    coupons = user_coupons_for(uid, "AND uc.message_id = ?", (mid,))
    return render_template("inbox_message.html", m=m, coupons=coupons)


@app.route("/inbox/read-all", methods=["POST"])
@login_required
def inbox_read_all():
    uid = current_user()["id"]
    sql, params = inbox_query(uid)
    get_db().execute(f"INSERT OR IGNORE INTO message_reads(message_id, user_id) SELECT id, ? FROM ({sql})",
                     (uid, *params))
    return redirect(url_for("inbox"))


@app.route("/coupons")
@login_required
def my_coupons():
    rows = user_coupons_for(current_user()["id"])
    tab = request.args.get("tab", "usable")
    return render_template("my_coupons.html", rows=[r for r in rows if r["state"] == tab], tab=tab,
                           counts={k: sum(1 for r in rows if r["state"] == k) for k in ("usable", "used", "expired")})


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    db = get_db()
    u = current_user()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = request.form.get("name", "").strip()
            raw = request.form.get("phone", "").strip()
            phone = normalize_my_phone(raw) if raw else ""
            if not name:
                flash("姓名不能空白", "error")
            elif phone is None or (not phone and not u["is_admin"]):
                flash(PHONE_ERROR, "error")
            else:
                db.execute("UPDATE users SET name = ?, phone = ? WHERE id = ?", (name, phone, u["id"]))
                flash("資料已更新", "success")
        elif action == "password":
            old, new = request.form.get("old", ""), request.form.get("new", "")
            if not check_password_hash(u["password_hash"], old):
                flash("目前密碼不正確", "error")
            elif len(new) < 6:
                flash("新密碼至少需要 6 個字元", "error")
            elif new != request.form.get("new2", ""):
                flash("兩次輸入的新密碼不一致", "error")
            else:
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), u["id"]))
                flash("密碼已更新", "success")
        return redirect(url_for("account"))
    return render_template("account.html")


# ---------------------------------------------------------------- 管理後台
@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    today = date.today()
    week_end = today + timedelta(days=6)
    stats = {
        "today": db.execute("SELECT COUNT(*) FROM bookings WHERE date = ? AND status IN ('pending','confirmed','completed')", (today.isoformat(),)).fetchone()[0],
        "pending": db.execute("SELECT COUNT(*) FROM bookings WHERE status = 'pending' AND date >= ?", (today.isoformat(),)).fetchone()[0],
        "week": db.execute("SELECT COUNT(*) FROM bookings WHERE date BETWEEN ? AND ? AND status IN ('pending','confirmed','completed')", (today.isoformat(), week_end.isoformat())).fetchone()[0],
        "members": db.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0").fetchone()[0],
        "month_revenue": db.execute(
            "SELECT COALESCE(SUM(COALESCE(b.final_price, s.price)),0) FROM bookings b JOIN services s ON s.id=b.service_id "
            "WHERE b.status = 'completed' AND substr(b.date,1,7) = ?", (today.strftime("%Y-%m"),)).fetchone()[0],
    }
    today_list = db.execute(BOOKING_SELECT + " WHERE b.date = ? AND b.status != 'cancelled' ORDER BY b.start_time", (today.isoformat(),)).fetchall()
    pending = db.execute(BOOKING_SELECT + " WHERE b.status = 'pending' AND b.date >= ? ORDER BY b.date, b.start_time LIMIT 20", (today.isoformat(),)).fetchall()
    return render_template("admin/dashboard.html", stats=stats, today_list=today_list, pending=pending, today=today)


@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    db = get_db()
    d = request.args.get("date", "")
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    rng = request.args.get("range", "" if (d or q or status) else "upcoming")
    where, params = [], []
    if d:
        where.append("b.date = ?"); params.append(d)
    elif rng == "upcoming":
        where.append("b.date >= ?"); params.append(date.today().isoformat())
    if status:
        where.append("b.status = ?"); params.append(status)
    if q:
        where.append("(COALESCE(u.name,b.guest_name) LIKE ? OR COALESCE(u.phone,b.guest_phone) LIKE ? OR u.email LIKE ?)")
        params += [f"%{q}%"] * 3
    sql = BOOKING_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    order = " ORDER BY b.date, b.start_time" if rng == "upcoming" or d else " ORDER BY b.date DESC, b.start_time DESC"
    rows = db.execute(sql + order + " LIMIT 300", params).fetchall()
    day = parse_date(d)
    nav = {"prev": (day - timedelta(days=1)).isoformat(), "next": (day + timedelta(days=1)).isoformat()} if day else None
    return render_template("admin/bookings.html", rows=rows, f={"date": d, "status": status, "q": q, "range": rng}, nav=nav)


@app.route("/admin/bookings/<int:bid>", methods=["GET", "POST"])
@admin_required
def admin_booking_detail(bid):
    db = get_db()
    b = db.execute(BOOKING_SELECT + " WHERE b.id = ?", (bid,)).fetchone()
    if not b:
        abort(404)
    if request.method == "POST":
        status = request.form.get("status")
        admin_note = request.form.get("admin_note")
        if status in STATUS_LABELS:
            if status in ACTIVE_STATUSES and b["status"] not in ACTIVE_STATUSES:
                # 從取消狀態恢復時，確認時段仍有空位
                svc = db.execute("SELECT * FROM services WHERE id = ?", (b["service_id"],)).fetchone()
                slot = next((x for x in compute_slots(svc, parse_date(b["date"]), for_admin=True, exclude_booking_id=bid)
                             if x["time"] == b["start_time"]), None)
                if not slot or slot["remaining"] <= 0:
                    flash("該時段已額滿，無法恢復此預約", "error")
                    return redirect(request.form.get("back") or url_for("admin_booking_detail", bid=bid))
            db.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, bid))
            if b["user_coupon_id"]:
                if status == "cancelled" and b["status"] != "cancelled":
                    release_coupon(bid)
                    flash("已將此預約使用的優惠券退回給會員", "info")
                elif b["status"] == "cancelled" and status != "cancelled":
                    # 恢復預約時重新扣回優惠券；若會員已把券用在別的預約，則此預約改為原價
                    took = db.execute("UPDATE user_coupons SET status = 'used', used_booking_id = ? "
                                      "WHERE id = ? AND status = 'unused'", (bid, b["user_coupon_id"])).rowcount
                    if not took:
                        db.execute("UPDATE bookings SET user_coupon_id = NULL, final_price = NULL WHERE id = ?", (bid,))
                        flash("此預約原本的優惠券已被使用，恢復後改以原價計算", "info")
        if admin_note is not None:
            db.execute("UPDATE bookings SET admin_note = ? WHERE id = ?", (admin_note.strip()[:1000], bid))
        flash(f"預約 #{bid} 已更新", "success")
        return redirect(safe_next(request.form.get("back")) or url_for("admin_booking_detail", bid=bid))
    return render_template("admin/booking_detail.html", b=b, photos=booking_photos_map([bid]).get(bid, []),
                           max_photos=MAX_PHOTOS_PER_BOOKING)


@app.route("/admin/bookings/<int:bid>/record", methods=["POST"])
@admin_required
def admin_booking_record(bid):
    """服務紀錄：給客人看的備註與照片。"""
    db = get_db()
    if not db.execute("SELECT 1 FROM bookings WHERE id = ?", (bid,)).fetchone():
        abort(404)
    action = request.form.get("action")
    if action == "delete_photo":
        p = db.execute("SELECT * FROM booking_photos WHERE id = ? AND booking_id = ?",
                       (request.form.get("photo_id", type=int), bid)).fetchone()
        if p:
            db.execute("DELETE FROM booking_photos WHERE id = ?", (p["id"],))
            try:
                os.remove(os.path.join(PRIVATE_PHOTO_DIR, p["filename"]))
            except OSError:
                pass
            flash("照片已刪除", "success")
    else:
        db.execute("UPDATE bookings SET service_note = ? WHERE id = ?",
                   (request.form.get("service_note", "").strip()[:3000], bid))
        files = [f for f in request.files.getlist("photos") if f and f.filename]
        have = db.execute("SELECT COUNT(*) FROM booking_photos WHERE booking_id = ?", (bid,)).fetchone()[0]
        if have + len(files) > MAX_PHOTOS_PER_BOOKING:
            flash(f"每筆預約最多 {MAX_PHOTOS_PER_BOOKING} 張照片，目前已有 {have} 張", "error")
            return redirect(url_for("admin_booking_detail", bid=bid) + "#record")
        saved = 0
        try:
            for file in files:
                name = save_private_photo(file)
                db.execute("INSERT INTO booking_photos(booking_id, filename) VALUES (?, ?)", (bid, name))
                saved += 1
        except ValueError as e:
            flash(str(e), "error")
        flash("服務紀錄已儲存" + (f"，新增 {saved} 張照片" if saved else ""), "success")
    return redirect(url_for("admin_booking_detail", bid=bid) + "#record")


@app.route("/booking-photo/<int:pid>")
def booking_photo(pid):
    """服務紀錄照片：只有該預約的會員本人和管理員可以看。"""
    u = current_user()
    if not u:
        abort(404)
    row = get_db().execute("SELECT p.filename, b.user_id FROM booking_photos p JOIN bookings b ON b.id = p.booking_id "
                           "WHERE p.id = ?", (pid,)).fetchone()
    if not row or not (u["is_admin"] or row["user_id"] == u["id"]):
        abort(404)
    resp = send_from_directory(PRIVATE_PHOTO_DIR, row["filename"], max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@app.route("/admin/bookings/new", methods=["GET", "POST"])
@admin_required
def admin_booking_new():
    db = get_db()
    form = request.form
    if request.method == "POST":
        d = parse_date(form.get("date"))
        sid = form.get("service_id", type=int)
        start = form.get("time", "")
        name = form.get("guest_name", "").strip()
        phone = form.get("guest_phone", "").strip()
        # 馬來西亞手機統一格式（方便連結會員）；其他號碼（例如新加坡）照原樣保存
        phone = normalize_my_phone(phone) or phone
        if not (d and sid and start and name and phone):
            flash("請完整填寫顧客姓名、電話、服務、日期與時間", "error")
        else:
            member = db.execute("SELECT id FROM users WHERE phone = ? AND is_admin = 0", (phone,)).fetchone()
            bid, err = create_booking(
                sid, d, start,
                user_id=member["id"] if member else None,
                guest_name=None if member else name,
                guest_phone=None if member else phone,
                note=form.get("note", "").strip()[:500], for_admin=True, status="confirmed",
            )
            if err:
                flash(err, "error")
            else:
                flash(f"已新增預約 #{bid}" + ("（已連結到會員）" if member else ""), "success")
                return redirect(url_for("admin_bookings", date=d.isoformat()))
    return render_template("admin/booking_new.html", catalog=load_catalog(active_only=False), form=form,
                           today=date.today().isoformat(), **closed_info())


@app.route("/admin/services")
@admin_required
def admin_services():
    counts = dict(get_db().execute("SELECT service_id, COUNT(*) FROM bookings GROUP BY service_id").fetchall())
    return render_template("admin/services.html", catalog=load_catalog(active_only=False), counts=counts)


@app.route("/admin/categories", methods=["POST"])
@admin_required
def admin_categories():
    db = get_db()
    f = request.form
    action, cid = f.get("action"), f.get("id", type=int)
    name = f.get("name", "").strip()
    if action == "add":
        if name:
            db.execute("INSERT INTO categories(name, description, sort_order) VALUES (?,?,?)",
                       (name, f.get("description", "").strip(), f.get("sort_order", type=int) or 0))
            flash(f"已新增主項目「{name}」，接著可以為它新增子項目", "success")
    elif action == "update" and cid:
        if name:
            db.execute("UPDATE categories SET name=?, description=?, sort_order=?, active=? WHERE id=?",
                       (name, f.get("description", "").strip(), f.get("sort_order", type=int) or 0,
                        1 if f.get("active") else 0, cid))
            flash("主項目已更新", "success")
    elif action == "delete" and cid:
        if db.execute("SELECT 1 FROM services WHERE category_id = ?", (cid,)).fetchone():
            flash("請先刪除或移走這個主項目下的子項目", "error")
        else:
            db.execute("DELETE FROM categories WHERE id = ?", (cid,))
            flash("主項目已刪除", "success")
    return redirect(url_for("admin_services"))


@app.route("/admin/services/new", methods=["GET", "POST"])
@app.route("/admin/services/<int:sid>", methods=["GET", "POST"])
@admin_required
def admin_service_edit(sid=None):
    db = get_db()
    svc = db.execute("SELECT * FROM services WHERE id = ?", (sid,)).fetchone() if sid else None
    if sid and not svc:
        abort(404)
    if request.method == "POST":
        f = request.form
        if f.get("action") == "delete" and svc:
            if db.execute("SELECT 1 FROM bookings WHERE service_id = ?", (sid,)).fetchone():
                db.execute("UPDATE services SET active = 0 WHERE id = ?", (sid,))
                flash("此服務已有預約紀錄，已改為「停用」而非刪除", "info")
            else:
                db.execute("DELETE FROM services WHERE id = ?", (sid,))
                flash("服務已刪除", "success")
            return redirect(url_for("admin_services"))
        name = f.get("name", "").strip()
        duration = svc["duration"] if svc else DEFAULT_DURATION  # 不在後台顯示，只用來計算時段佔用
        price = f.get("price", type=int)
        if not name or price is None or price < 0:
            flash("請填寫名稱與價格", "error")
        else:
            vals = (f.get("category_id", type=int), name, f.get("description", "").strip(), duration, price,
                    1 if f.get("active") else 0, f.get("sort_order", type=int) or 0)
            if svc:
                db.execute("UPDATE services SET category_id=?, name=?, description=?, duration=?, price=?, active=?, sort_order=? WHERE id=?", (*vals, sid))
            else:
                db.execute("INSERT INTO services(category_id, name, description, duration, price, active, sort_order) VALUES (?,?,?,?,?,?,?)", vals)
            flash("服務項目已儲存", "success")
            return redirect(url_for("admin_services"))
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order, id").fetchall()
    cur_cat = svc["category_id"] if svc else request.args.get("category", type=int)
    return render_template("admin/service_form.html", svc=svc, categories=categories, cur_cat=cur_cat)


@app.route("/admin/members")
@admin_required
def admin_members():
    q = request.args.get("q", "").strip()
    sql = ("SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS cnt, "
           "(SELECT MAX(date) FROM bookings b WHERE b.user_id = u.id AND b.status != 'cancelled') AS last_date "
           "FROM users u")
    params = []
    if q:
        sql += " WHERE u.name LIKE ? OR u.phone LIKE ? OR u.email LIKE ?"
        params = [f"%{q}%"] * 3
    rows = get_db().execute(sql + " ORDER BY u.is_admin DESC, u.created_at DESC LIMIT 500", params).fetchall()
    return render_template("admin/members.html", rows=rows, q=q)


@app.route("/admin/members/<int:uid>", methods=["GET", "POST"])
@admin_required
def admin_member_detail(uid):
    db = get_db()
    m = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not m:
        abort(404)
    if request.method == "POST":
        if request.form.get("action") == "toggle_admin":
            if uid == current_user()["id"]:
                flash("不能變更自己的管理員權限", "error")
            else:
                db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (0 if m["is_admin"] else 1, uid))
                flash("權限已更新", "success")
        elif request.form.get("action") == "verify_email":
            if not m["email_verified"]:
                db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (uid,))
                db.execute("DELETE FROM email_codes WHERE user_id = ?", (uid,))
                gifts = give_signup_gifts(uid)
                flash("已手動驗證此會員的 Email" + (f"，並送出 {gifts} 張新人體驗券" if gifts else ""), "success")
        elif request.form.get("action") == "reset_password":
            pw = secrets.token_urlsafe(6)
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(pw), uid))
            flash(f"已重設密碼，臨時密碼：{pw}（請轉告會員登入後自行修改）", "success")
        return redirect(url_for("admin_member_detail", uid=uid))
    rows = db.execute(BOOKING_SELECT + " WHERE b.user_id = ? ORDER BY b.date DESC, b.start_time DESC", (uid,)).fetchall()
    spent = sum(r["price"] for r in rows if r["status"] == "completed")
    return render_template("admin/member_detail.html", m=m, rows=rows, spent=spent,
                           coupons=user_coupons_for(uid))


# ---------------------------------------------------------------- 後台：公告與信件
@app.route("/admin/messages")
@admin_required
def admin_messages():
    db = get_db()
    announcements = db.execute(
        "SELECT m.*, (SELECT COUNT(*) FROM message_reads r WHERE r.message_id = m.id) AS reads "
        "FROM messages m WHERE m.user_id IS NULL ORDER BY m.created_at DESC, m.id DESC LIMIT 100").fetchall()
    personal = db.execute(
        "SELECT m.*, u.name AS user_name, (r.user_id IS NOT NULL) AS is_read, "
        "(SELECT COUNT(*) FROM user_coupons uc WHERE uc.message_id = m.id) AS coupon_count "
        "FROM messages m JOIN users u ON u.id = m.user_id "
        "LEFT JOIN message_reads r ON r.message_id = m.id AND r.user_id = m.user_id "
        "ORDER BY m.created_at DESC, m.id DESC LIMIT 100").fetchall()
    members = db.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0").fetchone()[0]
    return render_template("admin/messages.html", announcements=announcements, personal=personal, members=members)


@app.route("/admin/announcements/new", methods=["GET", "POST"])
@admin_required
def admin_announcement_new():
    f = request.form
    if request.method == "POST":
        title = f.get("title", "").strip()
        if not title:
            flash("請填寫標題", "error")
        else:
            try:
                image = save_upload(request.files.get("image"))
            except ValueError as e:
                flash(str(e), "error")
            else:
                send_message(None, title[:200], f.get("body", "").strip()[:5000], image)
                flash("公告已發佈，所有會員都會在收件箱看到", "success")
                return redirect(url_for("admin_messages"))
    return render_template("admin/announcement_form.html", form=f)


@app.route("/admin/messages/<int:mid>/delete", methods=["POST"])
@admin_required
def admin_message_delete(mid):
    db = get_db()
    db.execute("DELETE FROM message_reads WHERE message_id = ?", (mid,))
    db.execute("UPDATE user_coupons SET message_id = NULL WHERE message_id = ?", (mid,))  # 已發出的券保留
    db.execute("DELETE FROM messages WHERE id = ?", (mid,))
    flash("信件已刪除（已發出的優惠券仍保留在會員帳戶中）", "success")
    return redirect(url_for("admin_messages"))


# ---------------------------------------------------------------- 後台：優惠券
@app.route("/admin/coupons")
@admin_required
def admin_coupons():
    rows = [dict(r) for r in get_db().execute(
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM user_coupons uc WHERE uc.coupon_id = c.id) AS issued, "
        "(SELECT COUNT(*) FROM user_coupons uc WHERE uc.coupon_id = c.id AND uc.status = 'used') AS used "
        "FROM coupons c WHERE c.deleted = 0 ORDER BY c.active DESC, c.id DESC").fetchall()]
    smap = coupon_services_map([r["id"] for r in rows])
    for r in rows:
        r["services"] = smap.get(r["id"], [])
    return render_template("admin/coupons.html", rows=rows)


@app.route("/admin/coupons/new", methods=["GET", "POST"])
@app.route("/admin/coupons/<int:cid>", methods=["GET", "POST"])
@admin_required
def admin_coupon_edit(cid=None):
    db = get_db()
    cp = db.execute("SELECT * FROM coupons WHERE id = ? AND deleted = 0", (cid,)).fetchone() if cid else None
    if cid and not cp:
        abort(404)
    selected = {r[0] for r in db.execute("SELECT service_id FROM coupon_services WHERE coupon_id = ?", (cid,))} if cp else set()
    if request.method == "POST" and request.form.get("action") == "delete" and cp:
        # 會員手上未使用的券一併移除；已使用的保留在預約紀錄中
        removed = db.execute("DELETE FROM user_coupons WHERE coupon_id = ? AND status = 'unused'", (cid,)).rowcount
        if db.execute("SELECT 1 FROM user_coupons WHERE coupon_id = ?", (cid,)).fetchone():
            db.execute("UPDATE coupons SET deleted = 1, active = 0, signup_gift = 0 WHERE id = ?", (cid,))
        else:
            db.execute("DELETE FROM coupon_services WHERE coupon_id = ?", (cid,))
            db.execute("DELETE FROM coupons WHERE id = ?", (cid,))
        flash(f"優惠券「{cp['name']}」已刪除" + (f"，並移除 {removed} 位會員未使用的券" if removed else ""), "success")
        return redirect(url_for("admin_coupons"))
    unused_holders = db.execute("SELECT COUNT(*) FROM user_coupons WHERE coupon_id = ? AND status = 'unused'",
                                (cid,)).fetchone()[0] if cp else 0
    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip()
        price = f.get("price", type=int)
        valid_days = f.get("valid_days", type=int)
        services = [int(x) for x in f.getlist("services") if x.isdigit()]
        selected = set(services)
        if not name or price is None or price < 0 or valid_days is None or valid_days < 0:
            flash("請填寫名稱、體驗價與有效天數", "error")
        elif not services:
            flash("請至少選擇一個可使用此券的項目", "error")
        else:
            try:
                image = save_upload(request.files.get("image"))
                image_en = save_upload(request.files.get("image_en"))
            except ValueError as e:
                flash(str(e), "error")
            else:
                if f.get("remove_image"):
                    image = ""
                if f.get("remove_image_en"):
                    image_en = ""
                vals = dict(name=name[:100], description=f.get("description", "").strip()[:2000], price=price,
                            valid_days=valid_days, signup_gift=1 if f.get("signup_gift") else 0,
                            once_per_user=1 if f.get("once_per_user") else 0, active=1 if f.get("active") else 0)
                if image is not None:
                    vals["image"] = image or None
                if image_en is not None:
                    vals["image_en"] = image_en or None
                if cp:
                    sets = ", ".join(f"{k} = ?" for k in vals)
                    db.execute(f"UPDATE coupons SET {sets} WHERE id = ?", (*vals.values(), cid))
                else:
                    cols = ", ".join(vals)
                    cid = db.execute(f"INSERT INTO coupons({cols}) VALUES ({','.join('?' * len(vals))})",
                                     tuple(vals.values())).lastrowid
                db.execute("DELETE FROM coupon_services WHERE coupon_id = ?", (cid,))
                for sid in services:
                    db.execute("INSERT OR IGNORE INTO coupon_services(coupon_id, service_id) VALUES (?, ?)", (cid, sid))
                flash("優惠券已儲存", "success")
                return redirect(url_for("admin_coupons"))
    return render_template("admin/coupon_form.html", cp=cp, selected=selected, unused_holders=unused_holders,
                           catalog=load_catalog(active_only=False))


@app.route("/admin/coupons/send", methods=["GET", "POST"])
@admin_required
def admin_coupon_send():
    db = get_db()
    coupons = db.execute("SELECT * FROM coupons WHERE active = 1 AND deleted = 0 ORDER BY id DESC").fetchall()
    members = db.execute("SELECT id, name, phone, email FROM users WHERE is_admin = 0 ORDER BY created_at DESC").fetchall()
    f = request.form
    if request.method == "POST":
        cp = db.execute("SELECT * FROM coupons WHERE id = ? AND active = 1 AND deleted = 0", (f.get("coupon_id", type=int),)).fetchone()
        if f.get("target") == "all":
            uids = [m["id"] for m in members]
        else:
            uids = [int(x) for x in f.getlist("users") if x.isdigit()]
        title = f.get("title", "").strip() or (f"送你一張優惠券：{cp['name']}" if cp else "")
        body = f.get("body", "").strip()
        if not cp:
            flash("請選擇要發送的優惠券", "error")
        elif not uids:
            flash("請選擇收件會員", "error")
        else:
            sent = skipped = 0
            for uid in uids:
                if cp["once_per_user"] and db.execute(
                        "SELECT 1 FROM user_coupons WHERE user_id = ? AND coupon_id = ?", (uid, cp["id"])).fetchone():
                    skipped += 1
                    continue
                mid = send_message(uid, title[:200], body[:5000], kind="coupon")
                issue_coupon(cp, uid, mid)
                sent += 1
            flash(f"已發送給 {sent} 位會員" + (f"，{skipped} 位已領過此券（每人限領一次）而略過" if skipped else ""),
                  "success" if sent else "info")
            return redirect(url_for("admin_messages"))
    pre_users = {int(x) for x in request.args.getlist("uid") if x.isdigit()}
    return render_template("admin/coupon_send.html", coupons=coupons, members=members, form=f,
                           pre_coupon=request.args.get("coupon", type=int), pre_users=pre_users)


@app.errorhandler(413)
def too_large(_e):
    flash("檔案太大，一次上傳的照片合計請小於 60MB，可以分幾次上傳", "error")
    return redirect(request.referrer or url_for("admin_messages"))


# ---------------------------------------------------------------- 線上客服
CHAT_MAX_LEN = 1000
CHAT_MAX_PER_MINUTE = 15


def chat_unread_count(u):
    db = get_db()
    if u["is_admin"]:
        return db.execute("SELECT COUNT(*) FROM chat_messages WHERE sender = 'member' AND read_by_admin = 0").fetchone()[0]
    return db.execute("SELECT COUNT(*) FROM chat_messages WHERE user_id = ? AND sender = 'admin' AND read_by_member = 0",
                      (u["id"],)).fetchone()[0]


def chat_messages_for(user_id, after=0, limit=200):
    db = get_db()
    if after:
        rows = db.execute("SELECT * FROM chat_messages WHERE user_id = ? AND id > ? ORDER BY id LIMIT ?",
                          (user_id, after, limit)).fetchall()
    else:   # 第一次載入：最近 100 則
        rows = db.execute("SELECT * FROM (SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 100) "
                          "ORDER BY id", (user_id,)).fetchall()
    return [{"id": r["id"], "sender": r["sender"], "body": r["body"], "time": r["created_at"][5:16]} for r in rows]


def chat_post(user_id, sender, body, admin_id=None):
    """新增一則訊息；回傳 (訊息, 錯誤訊息)。"""
    body = (body or "").strip()
    if not body:
        return None, "請輸入訊息"
    if len(body) > CHAT_MAX_LEN:
        return None, f"訊息太長，請在 {CHAT_MAX_LEN} 字以內"
    db = get_db()
    if sender == "member":
        recent = db.execute("SELECT COUNT(*) FROM chat_messages WHERE user_id = ? AND sender = 'member' "
                            "AND created_at >= datetime('now','localtime','-1 minute')", (user_id,)).fetchone()[0]
        if recent >= CHAT_MAX_PER_MINUTE:
            return None, "訊息傳送太頻繁，請稍後再試"
    mid = db.execute(
        "INSERT INTO chat_messages(user_id, sender, admin_id, body, read_by_admin, read_by_member) VALUES (?,?,?,?,?,?)",
        (user_id, sender, admin_id, body, 1 if sender == "admin" else 0, 1 if sender == "member" else 0)).lastrowid
    r = db.execute("SELECT * FROM chat_messages WHERE id = ?", (mid,)).fetchone()
    return {"id": r["id"], "sender": r["sender"], "body": r["body"], "time": r["created_at"][5:16]}, None


def member_api(view):
    """客服 API：已驗證 Email 的會員才能使用（回傳 JSON 錯誤，不轉頁）。"""
    @functools.wraps(view)
    def wrapped(*a, **kw):
        u = current_user()
        if not u:
            return jsonify({"ok": False, "error": "請先登入會員"}), 401
        if u["is_admin"] or not u["email_verified"]:
            return jsonify({"ok": False, "error": "無法使用客服"}), 403
        return view(*a, **kw)
    return wrapped


def admin_api(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        u = current_user()
        if not u or not u["is_admin"]:
            return jsonify({"ok": False, "error": "沒有權限"}), 403
        return view(*a, **kw)
    return wrapped


@app.route("/api/chat", methods=["GET", "POST"])
@member_api
def api_chat():
    u = current_user()
    if request.method == "POST":
        msg, err = chat_post(u["id"], "member", request.form.get("body"))
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "message": msg})
    if request.args.get("peek"):   # 只看未讀數（聊天視窗關閉時）
        return jsonify({"ok": True, "unread": chat_unread_count(u)})
    msgs = chat_messages_for(u["id"], request.args.get("after", type=int) or 0)
    get_db().execute("UPDATE chat_messages SET read_by_member = 1 WHERE user_id = ? AND sender = 'admin' "
                     "AND read_by_member = 0", (u["id"],))
    return jsonify({"ok": True, "messages": msgs, "unread": 0})


@app.route("/admin/chat")
@admin_required
def admin_chat():
    return render_template("admin/chat.html", open_uid=request.args.get("uid", type=int))


@app.route("/admin/api/chat")
@admin_api
def admin_api_chat_list():
    rows = get_db().execute("""
        SELECT u.id, u.name, u.phone, u.email, m.body AS last_body, m.sender AS last_sender, m.created_at AS last_time,
               (SELECT COUNT(*) FROM chat_messages c WHERE c.user_id = u.id AND c.sender = 'member'
                AND c.read_by_admin = 0) AS unread
        FROM users u JOIN chat_messages m ON m.id = (SELECT MAX(id) FROM chat_messages WHERE user_id = u.id)
        ORDER BY m.id DESC LIMIT 300""").fetchall()
    return jsonify({"ok": True, "unread": chat_unread_count(current_user()), "conversations": [
        {"uid": r["id"], "name": r["name"], "phone": phone_filter(r["phone"]), "email": r["email"],
         "last": r["last_body"][:60], "last_sender": r["last_sender"], "time": r["last_time"][5:16], "unread": r["unread"]}
        for r in rows]})


@app.route("/admin/api/chat/<int:uid>", methods=["GET", "POST"])
@admin_api
def admin_api_chat(uid):
    db = get_db()
    m = db.execute("SELECT id, name, phone, email FROM users WHERE id = ? AND is_admin = 0", (uid,)).fetchone()
    if not m:
        return jsonify({"ok": False, "error": "找不到此會員"}), 404
    if request.method == "POST":
        msg, err = chat_post(uid, "admin", request.form.get("body"), admin_id=current_user()["id"])
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "message": msg})
    msgs = chat_messages_for(uid, request.args.get("after", type=int) or 0)
    db.execute("UPDATE chat_messages SET read_by_admin = 1 WHERE user_id = ? AND sender = 'member' AND read_by_admin = 0",
               (uid,))
    return jsonify({"ok": True, "member": {"uid": m["id"], "name": m["name"], "phone": phone_filter(m["phone"]),
                                          "email": m["email"]}, "messages": msgs})


# ---------------------------------------------------------------- 上傳海報（雲端時存於永久硬碟）
@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, max_age=86400)


# ---------------------------------------------------------------- 資料備份與還原
BACKUP_MAX_BYTES = 500 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _allow_large_restore_upload():
    """還原備份檔可能很大（含照片），只對這個網址放寬上傳上限。"""
    if request.path == "/admin/restore":
        request.max_content_length = BACKUP_MAX_BYTES


app.before_request_funcs.setdefault(None, []).insert(0, _allow_large_restore_upload)


@app.route("/admin/backup")
@admin_required
def admin_backup():
    """下載備份：資料庫 + 上傳的海報 + 服務紀錄照片（不含寄信密碼與金鑰）。"""
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "hanrejuve.db")
        src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(snap)
        try:
            src.backup(dst)   # 一致的快照，網站使用中也安全
        finally:
            dst.close(); src.close()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "hanrejuve.db")
            for base, prefix in ((UPLOAD_DIR, "uploads"), (PRIVATE_PHOTO_DIR, "booking_photos")):
                if os.path.isdir(base):
                    for name in sorted(os.listdir(base)):
                        p = os.path.join(base, name)
                        if os.path.isfile(p) and _SAFE_NAME.match(name) and not name.startswith("."):
                            z.write(p, f"{prefix}/{name}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"hanrejuve-backup-{datetime.now():%Y%m%d-%H%M}.zip")


@app.route("/admin/restore", methods=["POST"])
@admin_required
def admin_restore():
    """還原備份：用備份檔的資料取代目前網站的全部資料。"""
    file = request.files.get("backup")
    if not file or not file.filename.lower().endswith(".zip"):
        flash("請選擇從網站下載的備份檔（.zip）", "error")
        return redirect(url_for("admin_settings") + "#backup")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zpath = os.path.join(tmp, "backup.zip")
            file.save(zpath)
            with zipfile.ZipFile(zpath) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
                if "hanrejuve.db" not in names:
                    raise ValueError("no db")
                for n in names:   # 只接受預期的檔案，防止惡意壓縮檔
                    if n == "hanrejuve.db":
                        continue
                    parts = n.split("/")
                    if len(parts) != 2 or parts[0] not in ("uploads", "booking_photos")                             or not _SAFE_NAME.match(parts[1]) or parts[1].startswith("."):
                        raise ValueError(f"bad entry {n}")
                z.extract("hanrejuve.db", tmp)
                new_db = sqlite3.connect(os.path.join(tmp, "hanrejuve.db"))
                try:
                    if new_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or                             not new_db.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]:
                        raise ValueError("invalid db")
                    live = sqlite3.connect(DB_PATH, timeout=30)
                    try:
                        new_db.backup(live)   # 以備份內容取代目前資料庫
                    finally:
                        live.close()
                finally:
                    new_db.close()
                restored_files = 0
                for n in names:
                    if n == "hanrejuve.db":
                        continue
                    folder, name = n.split("/")
                    target_dir = UPLOAD_DIR if folder == "uploads" else PRIVATE_PHOTO_DIR
                    os.makedirs(target_dir, exist_ok=True)
                    with z.open(n) as src, open(os.path.join(target_dir, name), "wb") as out:
                        out.write(src.read())
                    restored_files += 1
    except (zipfile.BadZipFile, ValueError, sqlite3.DatabaseError) as e:
        app.logger.warning("還原失敗：%s", e)
        flash("備份檔不正確或已損壞，資料沒有變更", "error")
        return redirect(url_for("admin_settings") + "#backup")
    old = g.pop("db", None)
    if old is not None:
        old.close()
    g.pop("user", None)
    init_db()   # 舊版本的備份會自動升級資料表
    reset_session()
    flash(f"資料已還原（含 {restored_files} 個圖片檔），請用備份裡的管理員帳號重新登入", "success")
    return redirect(url_for("login"))


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    db = get_db()
    if request.method == "POST":
        f = request.form
        action = f.get("action")
        if action == "add_closed":
            d = parse_date(f.get("closed_date"))
            if d:
                db.execute("INSERT OR REPLACE INTO closed_dates(date, reason) VALUES (?, ?)", (d.isoformat(), f.get("reason", "").strip()))
                flash(f"已新增店休日 {d.isoformat()}", "success")
        elif action == "remove_closed":
            db.execute("DELETE FROM closed_dates WHERE date = ?", (f.get("closed_date"),))
            flash("已移除店休日", "success")
        else:
            try:
                if to_min(f["open_time"]) >= to_min(f["close_time"]):
                    raise ValueError("打烊時間必須晚於開店時間")
                for k in ("slot_interval", "capacity"):
                    if int(f[k]) < 1:
                        raise ValueError("數值必須大於 0")
                if int(f["booking_days_ahead"]) < 0:
                    raise ValueError("可預約天數不能為負數")
                for k in ("min_advance_hours", "cancel_hours"):
                    if float(f[k]) < 0:
                        raise ValueError("時數不能為負數")
            except (KeyError, ValueError) as e:
                flash(f"設定有誤：{e}", "error")
                return redirect(url_for("admin_settings"))
            new = {k: f.get(k, "").strip() for k in DEFAULT_SETTINGS if k not in ("closed_weekdays", "auto_confirm")}
            new["closed_weekdays"] = ",".join(f.getlist("closed_weekdays"))
            new["auto_confirm"] = "1" if f.get("auto_confirm") else "0"
            for k, v in new.items():
                db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, v))
            flash("設定已儲存", "success")
        return redirect(url_for("admin_settings"))
    closed = db.execute("SELECT * FROM closed_dates WHERE date >= ? ORDER BY date", (date.today().isoformat(),)).fetchall()
    return render_template("admin/settings.html", closed=closed,
                           cw=closed_weekdays(get_settings()))


@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(400)
def handle_error(e):
    msgs = {403: "您沒有權限瀏覽此頁面", 404: "找不到此頁面", 400: getattr(e, "description", "請求有誤")}
    return render_template("error.html", code=e.code, message=msgs.get(e.code, "發生錯誤")), e.code


init_db()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    print(f"HAN REJUVE 預約系統啟動：http://127.0.0.1:{port}")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
