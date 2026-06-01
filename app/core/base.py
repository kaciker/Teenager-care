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

def layout(title: str, body: str, user=None):
    role = user["role"] if user else None

    if role == "parent":
        nav_links = [
            ("/parent", "Inicio"),
            ("/today", "Hoy"),
            ("/admin/goals", "Objetivos"),
            ("/incidents", "Incidentes"),
            ("/allowance", "Puntos"),
        ]
    elif role == "child":
        nav_links = [
            ("/today", "Hoy"),
            ("/my/rewards", "Premios"),
            ("/my/incidents", "Incidentes"),
        ]
    else:
        nav_links = []

    nav = "".join([f'<a class="navlink" href="{href}">{label}</a>' for href, label in nav_links])
    who = f"<span class='who'>{user['display_name']}</span>" if user else ""

    return f"""
    <!doctype html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="manifest" href="/manifest.json">
    <link rel="icon" href="/icon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/icon.svg">
    <meta name="theme-color" content="#111827">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="Teenager-care">
    <style>
    body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:linear-gradient(180deg,#eef2ff,#f5f5f7);margin:0;color:#111827}}
    header{{position:sticky;top:0;z-index:10;background:#ffffffdd;backdrop-filter:blur(10px);padding:12px 14px;border-bottom:1px solid #eee;display:flex;gap:10px;justify-content:space-between;align-items:center;flex-wrap:wrap}}
    main{{padding:16px;max-width:980px;margin:auto}}
    .brand{{font-weight:900;letter-spacing:-.02em}}
    .topnav{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .navlink{{background:#eef2ff;color:#111827;text-decoration:none;font-weight:800;padding:8px 10px;border-radius:999px;font-size:13px}}
    .logout{{background:#111827;color:white;text-decoration:none;font-weight:800;padding:8px 10px;border-radius:999px;font-size:13px}}
    .who{{color:#6b7280;font-size:13px;font-weight:700}}
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
    <header>
      <div><span class="brand">Teenager-care</span> {who}</div>
      <nav class="topnav">{nav}<a class="logout" href="/logout">Salir</a></nav>
    </header>
    <main>{body}</main>
    <script>
    if ('serviceWorker' in navigator) {{
      navigator.serviceWorker.register('/service-worker.js').catch(() => {{}});
    }}
    </script>
    </body></html>
    """
