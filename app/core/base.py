import os
import sqlite3
import hashlib
import html
from datetime import datetime
from pathlib import Path

DB_PATH = os.getenv("CONTROLBABIES_DB", "/data/controlbabies.sqlite3")
UPLOAD_DIR = Path(os.getenv("CONTROLBABIES_UPLOAD_DIR", "/app/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

sessions = {}

PROFILE_PHOTOS = {
    "marcos": "marcos.png",
    "neli": "neli.png",
    "marcosjr": "marcos_jr.png",
    "lidia": "lidia.png",
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().isoformat(timespec="seconds")


def password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _safe_user_value(user, key, default=""):
    try:
        return user[key] or default
    except Exception:
        return default


def user_photo_url(user) -> str:
    username = _safe_user_value(user, "username", "").lower()
    filename = PROFILE_PHOTOS.get(username, f"{username}.png")
    return f"/uploads/profiles/{filename}"


def initials_from_name(name: str) -> str:
    parts = [p for p in (name or "?").replace("·", " ").split() if p]
    if not parts:
        return "?"
    return "".join(p[0].upper() for p in parts[:2])


def avatar_html(user, size="sm") -> str:
    display = html.escape(_safe_user_value(user, "display_name", "Usuario"))
    initials = html.escape(initials_from_name(display))
    src = html.escape(user_photo_url(user))
    return (
        f'<span class="avatar-wrap {size}" title="{display}">'
        f'<span class="avatar-initials">{initials}</span>'
        f'<img src="{src}" alt="{display}" loading="lazy" onerror="this.remove();">'
        f'</span>'
    )


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

    if user:
        who = f"""
        <div class="user-chip">
          {avatar_html(user)}
          <span>{html.escape(user['display_name'])}</span>
        </div>
        """
    else:
        who = ""

    return f"""
    <!doctype html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="manifest" href="/manifest.json">
    <link rel="icon" href="/icon.svg" type="image/svg+xml">
    <link rel="icon" href="/icon-192.png" sizes="192x192" type="image/png">
    <link rel="apple-touch-icon" href="/icon-192.png">
    <meta name="theme-color" content="#7c3aed">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="Teenager-care">
    <style>
    :root{{
      --ink:#111827;
      --muted:#6b7280;
      --bg1:#fff7ed;
      --bg2:#eef2ff;
      --brand:#7c3aed;
      --brand2:#06b6d4;
      --ok:#10b981;
      --warn:#f59e0b;
      --danger:#ef4444;
      --card:#ffffffd9;
    }}
    *{{box-sizing:border-box}}
    body{{
      font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;
      background:
        radial-gradient(circle at top left,#fde68a 0,#fde68a55 24%,transparent 44%),
        radial-gradient(circle at top right,#a78bfa66 0,#a78bfa44 24%,transparent 42%),
        linear-gradient(180deg,var(--bg1),var(--bg2));
      margin:0;
      min-height:100vh;
      color:var(--ink);
    }}
    header{{
      position:sticky;top:0;z-index:10;
      background:#ffffffcc;
      backdrop-filter:blur(16px);
      padding:12px 14px;
      border-bottom:1px solid #ffffffaa;
      display:flex;
      gap:10px;
      justify-content:space-between;
      align-items:center;
      flex-wrap:wrap;
      box-shadow:0 8px 28px #1f29370f;
    }}
    main{{padding:16px;max-width:1040px;margin:auto}}
    .brand{{
      display:flex;align-items:center;gap:10px;
      font-weight:950;letter-spacing:-.04em;font-size:19px;
    }}
    .brand::before{{
      content:"";
      width:34px;height:34px;border-radius:13px;
      background:linear-gradient(135deg,var(--brand),var(--brand2));
      box-shadow:0 10px 24px #7c3aed55;
    }}
    .topnav{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .navlink{{
      background:#fff;
      color:#312e81;
      text-decoration:none;
      font-weight:850;
      padding:9px 12px;
      border-radius:999px;
      font-size:13px;
      box-shadow:0 7px 18px #1f293714;
    }}
    .logout{{
      background:linear-gradient(135deg,#111827,#374151);
      color:white;text-decoration:none;font-weight:850;
      padding:9px 12px;border-radius:999px;font-size:13px;
      box-shadow:0 8px 20px #11182733;
    }}
    .user-chip{{
      display:flex;align-items:center;gap:8px;
      background:#ffffff;
      border-radius:999px;
      padding:5px 10px 5px 5px;
      font-size:13px;
      font-weight:850;
      color:#374151;
      box-shadow:0 8px 22px #1f293714;
    }}
    .avatar-wrap{{
      width:34px;height:34px;
      border-radius:999px;
      display:inline-grid;
      place-items:center;
      position:relative;
      overflow:hidden;
      flex:none;
      background:linear-gradient(135deg,#7c3aed,#06b6d4);
      color:white;
      box-shadow:0 8px 22px #7c3aed40;
      vertical-align:middle;
    }}
    .avatar-wrap.lg{{width:74px;height:74px;border-radius:24px}}
    .avatar-wrap.xl{{width:96px;height:96px;border-radius:30px}}
    .avatar-initials{{font-weight:950;font-size:13px;letter-spacing:-.02em}}
    .avatar-wrap.lg .avatar-initials{{font-size:22px}}
    .avatar-wrap.xl .avatar-initials{{font-size:28px}}
    .avatar-wrap img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:inherit}}
    .card{{
      background:var(--card);
      border:1px solid #ffffffaa;
      border-radius:28px;
      padding:18px;
      margin:13px 0;
      box-shadow:0 18px 42px #1f293716;
    }}
    .person-card{{display:flex;align-items:center;gap:14px}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
    input,select,textarea,button{{
      width:100%;box-sizing:border-box;
      padding:13px;margin:7px 0;
      border-radius:16px;
      border:1px solid #e5e7eb;
      font-size:15px;
      background:white;
    }}
    button,.btn{{
      background:linear-gradient(135deg,var(--brand),#4f46e5);
      color:white;border:0;font-weight:900;
      text-decoration:none;display:inline-block;text-align:center;
      padding:13px;border-radius:16px;
      box-shadow:0 12px 26px #7c3aed33;
    }}
    .danger{{background:linear-gradient(135deg,#ef4444,#b91c1c)}}
    .ok{{background:linear-gradient(135deg,#10b981,#047857)}}
    .muted{{color:var(--muted);font-size:13px}}
    .pill{{
      display:inline-block;padding:7px 11px;border-radius:999px;
      background:#ede9fe;color:#5b21b6;
      font-size:12px;margin:2px;font-weight:900;
    }}
    .hero{{
      background:linear-gradient(135deg,#7c3aed,#2563eb 55%,#06b6d4);
      color:white;
      border-radius:34px;
      padding:24px;
      margin:14px 0;
      box-shadow:0 20px 48px #2563eb33;
      overflow:hidden;
      position:relative;
    }}
    .hero::after{{
      content:"";
      position:absolute;right:-40px;top:-40px;
      width:150px;height:150px;border-radius:50%;
      background:#ffffff22;
    }}
    .hero h1{{margin:0 0 8px;font-size:34px;letter-spacing:-.06em}}
    .hero p{{margin:0;color:#eef2ff}}
    .score{{font-size:46px;font-weight:950;line-height:1;letter-spacing:-.06em}}
    .critical{{border:2px solid #fbbf24;background:#fffbebdd}}
    img{{max-width:100%;border-radius:16px}}
    @media(max-width:620px){{
      header{{align-items:flex-start}}
      .topnav{{width:100%;overflow:auto;flex-wrap:nowrap;padding-bottom:2px}}
      .navlink,.logout{{white-space:nowrap}}
      main{{padding:12px}}
      .hero h1{{font-size:28px}}
    }}
    </style></head><body>
    <header>
      <div class="brand">Teenager-care</div>
      {who}
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
