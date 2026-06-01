import secrets
import struct
import zlib
from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from core.base import UPLOAD_DIR, db, now, sessions, password_hash, layout, avatar_html, profile_photo_url
from core.auth import current_user, require_user
from routes.responsibilities import router as responsibilities_router, ensure_daily_actions
from routes.incidents import router as incidents_router
from routes.allowance import router as allowance_router
from routes.admin_goals import router as admin_goals_router

app = FastAPI(title="Teenager-care", version="0.11.6")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.include_router(responsibilities_router)
app.include_router(incidents_router)
app.include_router(allowance_router)
app.include_router(admin_goals_router)


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('parent','child')),
            password_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            mandatory INTEGER NOT NULL DEFAULT 1,
            points INTEGER NOT NULL DEFAULT 10,
            penalty_points INTEGER NOT NULL DEFAULT 10,
            schedule_hint TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            assigned_to_user_id INTEGER,
            completed_by_user_id INTEGER,
            status TEXT NOT NULL CHECK(status IN ('pending','done','approved','rejected')),
            event_date TEXT NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS penalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_user_id INTEGER NOT NULL,
            parent_user_id INTEGER NOT NULL,
            task_id INTEGER,
            severity TEXT NOT NULL CHECK(severity IN ('leve','media','grave')),
            points INTEGER NOT NULL,
            affects_allowance INTEGER NOT NULL DEFAULT 0,
            punishment TEXT,
            reason TEXT NOT NULL,
            image_path TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            cost_points INTEGER NOT NULL,
            reward_type TEXT NOT NULL DEFAULT 'other',
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS reward_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reward_id INTEGER NOT NULL,
            child_user_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('requested','approved','rejected')),
            created_at TEXT NOT NULL,
            decided_at TEXT
        );

        CREATE TABLE IF NOT EXISTS daily_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id INTEGER NOT NULL,
            event_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            claimed_by_user_id INTEGER,
            completed_by_user_id INTEGER,
            validated_by_user_id INTEGER,
            claimed_at TEXT,
            completed_at TEXT,
            validated_at TEXT,
            UNIQUE(action_id, event_date)
        );
        """)

        default_users = [
            ("marcos", "Marcos", "parent", "padre123"),
            ("neli", "Neli", "parent", "madre123"),
            ("marcosjr", "Marcos Jr. · 14 años", "child", "hijo123"),
            ("lidia", "Lidia · 17 años", "child", "hijo123"),
        ]
        for username, display_name, role, password in default_users:
            conn.execute("""
            INSERT OR IGNORE INTO users(username, display_name, role, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (username, display_name, role, password_hash(password), now()))

        default_tasks = [
            ("🐶 Sacar a Arlo al mediodía", "Responsabilidad obligatoria: Arlo depende de vosotros al mediodía. Debe quedar claro quién lo ha hecho.", "arlo", 1, 20, 25, "Mediodía"),
            ("🐱 Limpiar ecosistema de Ares", "La caja/ecosistema de Ares debe mantenerse limpio entre Marcos Jr. y Lidia.", "ares", 1, 20, 25, "Diario"),
        ]
        for t in default_tasks:
            conn.execute("""
            INSERT OR IGNORE INTO tasks(title, description, category, mandatory, points, penalty_points, schedule_hint)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, t)

        default_rewards = [
            ("Extra de paga", "Canjear puntos por paga extra semanal.", 50, "money"),
            ("Tiempo extra de consola", "Tiempo adicional autorizado por los padres.", 35, "time"),
            ("Elegir cena", "Elegir una cena familiar.", 40, "choice"),
        ]
        for r in default_rewards:
            conn.execute("""
            INSERT OR IGNORE INTO rewards(title, description, cost_points, reward_type)
            VALUES (?, ?, ?, ?)
            """, r)


def points_for_child(child_id: int):
    with db() as conn:
        approved = conn.execute("""
        SELECT COALESCE(SUM(t.points),0) AS value
        FROM task_events e
        JOIN tasks t ON t.id=e.task_id
        WHERE e.completed_by_user_id=? AND e.status='approved'
        """, (child_id,)).fetchone()["value"]

        penalties = conn.execute("""
        SELECT COALESCE(SUM(points),0) AS value
        FROM penalties
        WHERE child_user_id=?
        """, (child_id,)).fetchone()["value"]

        claims = conn.execute("""
        SELECT COALESCE(SUM(r.cost_points),0) AS value
        FROM reward_claims c
        JOIN rewards r ON r.id=c.reward_id
        WHERE c.child_user_id=? AND c.status='approved'
        """, (child_id,)).fetchone()["value"]

        return approved - penalties - claims



@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    """Send expired/missing browser sessions back to login instead of showing raw 401."""
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=302)
    raise exc


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/parent" if user["role"] == "parent" else "/today", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    marcos_photo = profile_photo_url("marcos.png")
    neli_photo = profile_photo_url("neli.png")
    marcos_jr_photo = profile_photo_url("marcos_jr.png")
    lidia_photo = profile_photo_url("lidia.png")
    arlo_photo = profile_photo_url("arlo.png")
    ares_photo = profile_photo_url("ares.png")

    return f"""
    <!doctype html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Teenager-care</title>
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="/icon-192.png">
    <meta name="theme-color" content="#7c3aed">
    <style>
    *{{box-sizing:border-box}}
    body{{
      font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;
      margin:0;
      min-height:100vh;
      background:
        radial-gradient(circle at top left,#fde68a 0,#fde68a66 26%,transparent 45%),
        radial-gradient(circle at bottom right,#93c5fd88 0,#93c5fd55 28%,transparent 52%),
        linear-gradient(160deg,#fff7ed,#eef2ff);
      color:#111827;
      padding:20px;
      display:grid;
      place-items:center;
    }}
    .shell{{width:100%;max-width:520px}}
    .brand{{
      display:flex;align-items:center;gap:12px;
      font-weight:950;font-size:28px;letter-spacing:-.06em;
      margin-bottom:14px;
    }}
    .brand-icon{{
      width:48px;height:48px;border-radius:18px;
      background:linear-gradient(135deg,#7c3aed,#06b6d4);
      box-shadow:0 16px 34px #7c3aed55;
    }}
    .card{{
      background:#ffffffdd;
      border:1px solid #ffffffaa;
      border-radius:36px;
      padding:26px;
      box-shadow:0 24px 70px #1f293724;
      backdrop-filter:blur(14px);
    }}
    h1{{margin:0;font-size:40px;letter-spacing:-.07em}}
    .subtitle{{color:#6b7280;line-height:1.35;margin:8px 0 18px}}
    input,button{{
      width:100%;padding:15px;margin:8px 0;
      border-radius:18px;border:1px solid #e5e7eb;font-size:16px;
    }}
    button{{
      background:linear-gradient(135deg,#7c3aed,#2563eb);
      color:white;border:0;font-weight:950;
      box-shadow:0 14px 30px #7c3aed44;
    }}
    .family-strip{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}
    .pets-strip{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:16px}}
    .member,.pet-card{{text-align:center;font-size:12px;font-weight:850;color:#374151}}
    .photo{{
      width:66px;height:66px;margin:0 auto 6px;border-radius:22px;
      display:grid;place-items:center;overflow:hidden;
      background:linear-gradient(135deg,#7c3aed,#06b6d4);
      color:white;font-weight:950;
      box-shadow:0 12px 28px #1f293722;
      position:relative;
    }}
    .pet-photo{{
      width:100%;height:112px;border-radius:26px;
      display:grid;place-items:center;overflow:hidden;
      background:
        radial-gradient(circle at top left,#fbbf24 0,#fbbf2455 34%,transparent 56%),
        linear-gradient(135deg,#ecfeff,#eef2ff);
      color:#312e81;font-size:28px;font-weight:950;
      box-shadow:0 12px 28px #1f293716;
      margin-bottom:7px;
      position:relative;
    }}
    .photo img,.pet-photo img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:inherit}}
    .small-note{{font-size:13px;color:#6b7280;text-align:center;margin-top:12px;font-weight:850}}
    </style></head><body>
    <div class="shell">
      <div class="brand"><div class="brand-icon"></div><span>Teenager-care</span></div>
      <div class="card">
        <h1>Familia en marcha</h1>
        <p class="subtitle">Responsabilidades, puntos, premios, incidentes y colaboración familiar en una app privada.</p>

        <div class="family-strip">
          <div class="member"><div class="photo">M<img src="{marcos_photo}" onerror="this.remove()"></div>Marcos</div>
          <div class="member"><div class="photo">N<img src="{neli_photo}" onerror="this.remove()"></div>Neli</div>
          <div class="member"><div class="photo">MJ<img src="{marcos_jr_photo}" onerror="this.remove()"></div>Marcos Jr.</div>
          <div class="member"><div class="photo">L<img src="{lidia_photo}" onerror="this.remove()"></div>Lidia</div>
        </div>

        <form method="post" action="/login">
          <input name="username" placeholder="Usuario" required>
          <input name="password" placeholder="Contraseña" type="password" required>
          <button>Entrar</button>
        </form>

        <div class="pets-strip">
          <div class="pet-card"><div class="pet-photo">Arlo<img src="{arlo_photo}" onerror="this.remove()"></div>Arlo</div>
          <div class="pet-card"><div class="pet-photo">Ares<img src="{ares_photo}" onerror="this.remove()"></div>Ares</div>
        </div>

        <p class="small-note">Ellos te lo agradecerán...</p>
      </div>
    </div>
    </body></html>
    """

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
    if not user or not password_hash(password)==user["password_hash"]:
        return RedirectResponse("/login", status_code=302)
    token = secrets.token_urlsafe(32)
    sessions[token] = user["id"]
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("cb_session", token, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("cb_session")
    if token:
        sessions.pop(token, None)
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("cb_session")
    return response


@app.get("/parent", response_class=HTMLResponse)
def parent_dashboard(request: Request):
    user = require_user(request)
    if user["role"] != "parent":
        return RedirectResponse("/today", status_code=302)

    ensure_daily_actions()

    from core.points import points_balance

    with db() as conn:
        children = conn.execute("""
        SELECT id, username, display_name
        FROM users
        WHERE role='child' AND active=1
        ORDER BY display_name
        """).fetchall()

        today_rows = conn.execute("""
        SELECT da.*, a.name AS action_name, a.points, u.display_name AS claimed_by
        FROM daily_actions da
        JOIN actions a ON a.id=da.action_id
        LEFT JOIN users u ON u.id=da.claimed_by_user_id
        WHERE da.event_date=date('now')
        ORDER BY a.name
        """).fetchall()

        incidents = conn.execute("""
        SELECT i.*, u.display_name AS child_name
        FROM incidents i
        JOIN users u ON u.id=i.child_user_id
        ORDER BY i.id DESC
        LIMIT 5
        """).fetchall() if conn.execute("select name from sqlite_master where type='table' and name='incidents'").fetchone() else []

        redemptions = conn.execute("""
        SELECT rr.*, ri.title, u.display_name AS child_name
        FROM reward_redemptions rr
        JOIN reward_items ri ON ri.id=rr.reward_item_id
        JOIN users u ON u.id=rr.child_user_id
        ORDER BY rr.id DESC
        LIMIT 5
        """).fetchall() if conn.execute("select name from sqlite_master where type='table' and name='reward_redemptions'").fetchone() else []

        child_cards = "".join([
            f"<div class='card person-card'>{avatar_html(c, 'lg')}<div><h3>{c['display_name']}</h3><div class='score'>{points_balance(c['id'], conn=conn)}</div><p class='muted'>puntos actuales</p></div></div>"
            for c in children
        ])

    today_cards = ""
    for x in today_rows:
        controls = ""
        if x["status"] == "completed":
            controls = f"<form method='post' action='/actions/{x['action_id']}/validate'><button class='ok'>Validar</button></form><form method='post' action='/actions/{x['action_id']}/reject-daily'><button class='danger'>Rechazar</button></form>"
        today_cards += f"<div class='card critical'><b>{x['action_name']}</b><p>Estado: {x['status']} · Responsable: {x['claimed_by'] or '-'}</p>{controls}</div>"

    incident_cards = "".join([
        f"<div class='card'><b>{i['child_name']}</b> · <span class='pill'>{i['severity']}</span><p>{i['reason']}</p></div>"
        for i in incidents
    ])

    redemption_cards = "".join([
        f"<div class='card'><b>{r['child_name']}</b> pide <b>{r['title']}</b><p>Estado: {r['status']} · Coste: {r['cost_points']} puntos</p></div>"
        for r in redemptions
    ])

    body = f"""
    <div class='hero'>
      <h1>Panel familiar</h1>
      <p>Responsabilidades, incidentes, puntos, premios y paga.</p>
    </div>

    <div class='grid'>{child_cards}</div>

    <div class='card'>
      <h2>Responsabilidades de hoy</h2>
      {today_cards or '<p class="muted">Sin responsabilidades para hoy.</p>'}
      <a class='btn' href='/today'>Ver detalle diario</a>
    </div>

    <div class='grid'>
      <div class='card'>
        <h2>Incidentes recientes</h2>
        {incident_cards or '<p class="muted">Sin incidentes.</p>'}
        <a class='btn' href='/incidents'>Gestionar incidentes</a>
      </div>

      <div class='card'>
        <h2>Premios y paga</h2>
        {redemption_cards or '<p class="muted">Sin solicitudes.</p>'}
        <a class='btn' href='/allowance'>Gestionar puntos</a>
      </div>
    </div>

    <div class='card'>
      <h2>Administración</h2>
      <a class='btn' href='/admin/goals'>Objetivos, responsabilidades y acciones</a>
    </div>
    """

    return layout("Panel familiar", body, user=user)


@app.get("/child", response_class=HTMLResponse)
def child_dashboard(request: Request):
    user = require_user(request)
    if user["role"] != "child":
        return RedirectResponse("/parent", status_code=302)
    return RedirectResponse("/today", status_code=302)


@app.post("/tasks/{task_id}/done")
def mark_done(request: Request, task_id: int, comment: Optional[str] = Form(None)):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)
    with db() as conn:
        conn.execute("""
        INSERT INTO task_events(task_id, completed_by_user_id, status, event_date, comment, created_at, updated_at)
        VALUES (?, ?, 'done', ?, ?, ?, ?)
        """, (task_id, user["id"], date.today().isoformat(), comment, now(), now()))
    return RedirectResponse("/today", status_code=302)


@app.post("/events/{event_id}/approve")
def approve_event(request: Request, event_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)
    with db() as conn:
        conn.execute("UPDATE task_events SET status='approved', updated_at=? WHERE id=?", (now(), event_id))
    return RedirectResponse("/parent", status_code=302)


@app.post("/events/{event_id}/reject")
def reject_event(request: Request, event_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)
    with db() as conn:
        conn.execute("UPDATE task_events SET status='rejected', updated_at=? WHERE id=?", (now(), event_id))
    return RedirectResponse("/parent", status_code=302)


@app.post("/penalties")
async def create_penalty(
    request: Request,
    child_user_id: int = Form(...),
    task_id: Optional[str] = Form(None),
    severity: str = Form(...),
    points: int = Form(...),
    affects_allowance: int = Form(0),
    punishment: Optional[str] = Form(None),
    reason: str = Form(...),
    image: Optional[UploadFile] = File(None),
):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    image_path = None
    if image and image.filename:
        ext = Path(image.filename).suffix.lower() or ".jpg"
        filename = f"penalty_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{ext}"
        target = UPLOAD_DIR / filename
        target.write_bytes(await image.read())
        image_path = f"/uploads/{filename}"

    real_task_id = int(task_id) if task_id else None
    with db() as conn:
        conn.execute("""
        INSERT INTO penalties(child_user_id, parent_user_id, task_id, severity, points, affects_allowance, punishment, reason, image_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (child_user_id, user["id"], real_task_id, severity, points, affects_allowance, punishment, reason, image_path, now()))

    return RedirectResponse("/parent", status_code=302)


@app.post("/rewards/{reward_id}/claim")
def claim_reward(request: Request, reward_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)
    with db() as conn:
        conn.execute("""
        INSERT INTO reward_claims(reward_id, child_user_id, status, created_at)
        VALUES (?, ?, 'requested', ?)
        """, (reward_id, user["id"], now()))
    return RedirectResponse("/today", status_code=302)



@app.get("/manifest.json")
def manifest():
    return JSONResponse({
        "name": "Teenager-care",
        "short_name": "Teenager-care",
        "description": "Responsabilidades, puntos, premios y colaboración familiar.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#eef2ff",
        "theme_color": "#111827",
        "icons": [
            {
                "src": "/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            },
            {
                "src": "/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })


@app.get("/service-worker.js")
def service_worker():
    js = """
const CACHE_NAME = "teenager-care-v0.11.6";
const CORE_ASSETS = ["/", "/manifest.json", "/favicon.ico", "/apple-touch-icon.png", "/icon.svg", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(CORE_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
"""
    return Response(js, media_type="application/javascript")


@app.get("/icon.svg")
def app_icon():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'>
<rect width='512' height='512' rx='112' fill='#111827'/>
<circle cx='170' cy='190' r='58' fill='#f59e0b'/>
<circle cx='342' cy='190' r='58' fill='#60a5fa'/>
<path d='M118 346c35-62 241-62 276 0' fill='none' stroke='#ffffff' stroke-width='38' stroke-linecap='round'/>
<path d='M166 305l55 55 126-138' fill='none' stroke='#34d399' stroke-width='34' stroke-linecap='round' stroke-linejoin='round'/>
</svg>"""
    return Response(svg, media_type="image/svg+xml")



def _png_chunk(tag, data):
    raw = tag + data
    return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xffffffff)


def _teenager_care_png(size: int) -> bytes:
    """Generate a simple valid RGBA PNG without external dependencies."""
    bg = (17, 24, 39, 255)
    amber = (245, 158, 11, 255)
    blue = (96, 165, 250, 255)
    green = (52, 211, 153, 255)
    white = (255, 255, 255, 255)

    pixels = []
    cx1, cy1, r1 = int(size * 0.33), int(size * 0.35), int(size * 0.11)
    cx2, cy2, r2 = int(size * 0.67), int(size * 0.35), int(size * 0.11)

    for y in range(size):
        row = bytearray()
        for x in range(size):
            color = bg

            if (x - cx1) ** 2 + (y - cy1) ** 2 <= r1 ** 2:
                color = amber
            elif (x - cx2) ** 2 + (y - cy2) ** 2 <= r2 ** 2:
                color = blue

            # Soft smile arc.
            yy = int(size * 0.67)
            if abs(y - yy) < max(2, size // 48) and int(size * 0.23) < x < int(size * 0.77):
                color = white

            # Check mark approximation.
            if int(size * 0.31) < x < int(size * 0.70):
                d1 = abs((y - int(size * 0.66)) - (x - int(size * 0.31)) * 0.65)
                d2 = abs((y - int(size * 0.76)) + (x - int(size * 0.47)) * 0.82)
                if d1 < max(3, size // 34) or d2 < max(3, size // 34):
                    if int(size * 0.43) < y < int(size * 0.82):
                        color = green

            row.extend(color)
        pixels.append(b"\x00" + bytes(row))

    raw = b"".join(pixels)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


@app.get("/icon-192.png")
def app_icon_192():
    return Response(_teenager_care_png(192), media_type="image/png")


@app.get("/icon-512.png")
def app_icon_512():
    return Response(_teenager_care_png(512), media_type="image/png")



@app.get("/api/runtime-status")
def runtime_status():
    return JSONResponse({
        "status": "ok",
        "service": "Teenager-care",
        "version": "0.11.6",
        "runtime": {
            "containerized": True,
            "git_available_in_container": False,
            "database_path": "/data/controlbabies.sqlite3"
        },
        "pwa": {
            "manifest_url": "/manifest.json",
            "service_worker_url": "/service-worker.js",
            "service_worker_cache": "teenager-care-v0.11.6",
            "icons": [
                "/icon.svg",
                "/icon-192.png",
                "/icon-512.png"
            ]
        }
    })



def _ico_from_pngs(items):
    """Build a simple ICO file containing PNG images."""
    count = len(items)
    header = b"\x00\x00\x01\x00" + count.to_bytes(2, "little")
    directory = bytearray()
    data = bytearray()
    offset = 6 + 16 * count

    for size, png in items:
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        directory.extend(bytes([width, height, 0, 0]))
        directory.extend((1).to_bytes(2, "little"))
        directory.extend((32).to_bytes(2, "little"))
        directory.extend(len(png).to_bytes(4, "little"))
        directory.extend(offset.to_bytes(4, "little"))
        data.extend(png)
        offset += len(png)

    return header + bytes(directory) + bytes(data)


@app.get("/favicon.ico")
def favicon_ico():
    return Response(
        _ico_from_pngs([
            (32, _teenager_care_png(32)),
            (64, _teenager_care_png(64)),
        ]),
        media_type="image/x-icon",
    )


@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    return Response(_teenager_care_png(180), media_type="image/png")


@app.get("/api/health")
def health():
    return JSONResponse({"status": "ok", "service": "Teenager-care", "version": "0.11.6"})


