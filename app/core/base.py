import os
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path

DB_PATH = os.getenv("CONTROLBABIES_DB", "/data/controlbabies.sqlite3")
UPLOAD_DIR = Path(os.getenv("CONTROLBABIES_UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

sessions = {}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.now().isoformat(timespec="seconds")

def password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def layout(title: str, body: str):
    return f"""
    <!doctype html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
    body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:linear-gradient(180deg,#eef2ff,#f5f5f7);margin:0;color:#111827}}
    header{{position:sticky;top:0;background:#ffffffcc;backdrop-filter:blur(10px);padding:14px 18px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center}}
    main{{padding:16px;max-width:900px;margin:auto}}
    .card{{background:white;border-radius:24px;padding:18px;margin:12px 0;box-shadow:0 12px 30px #00000012}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
    input,select,textarea,button{{width:100%;box-sizing:border-box;padding:12px;margin:6px 0;border-radius:14px;border:1px solid #ddd;font-size:15px}}
    button,.btn{{background:#111827;color:white;border:0;font-weight:700;text-decoration:none;display:inline-block;text-align:center;padding:12px;border-radius:14px}}
    .danger{{background:#b91c1c}}
    .ok{{background:#047857}}
    .muted{{color:#6b7280;font-size:13px}}
    .pill{{display:inline-block;padding:6px 10px;border-radius:999px;background:#eef2ff;font-size:12px;margin:2px;font-weight:700}}
    .hero{{background:#111827;color:white;border-radius:28px;padding:22px;margin:12px 0;box-shadow:0 16px 35px #0002}}
    .score{{font-size:42px;font-weight:900;line-height:1}}
    .critical{{border:2px solid #f59e0b;background:#fffbeb}}
    img{{max-width:100%;border-radius:14px}}
    </style></head><body>
    <header><strong>{title}</strong><a href="/logout">Salir</a></header>
    <main>{body}</main>
    </body></html>
    """
