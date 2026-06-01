import secrets
from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.base import UPLOAD_DIR, db, now, sessions, password_hash, layout
from core.auth import current_user, require_user
from routes.responsibilities import router as responsibilities_router, ensure_daily_actions
from routes.incidents import router as incidents_router
from routes.admin_goals import router as admin_goals_router

app = FastAPI(title="Teenager-care", version="0.4.2")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.include_router(responsibilities_router)
app.include_router(incidents_router)
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
    return """
    <!doctype html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ControlBabies</title>
    <style>
    body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:linear-gradient(180deg,#eef2ff,#f5f5f7);margin:0;padding:24px}
    .card{max-width:420px;margin:8vh auto;background:white;border-radius:28px;padding:24px;box-shadow:0 18px 45px #0002}
    input,button{width:100%;padding:14px;margin:8px 0;border-radius:14px;border:1px solid #ddd;font-size:16px}
    button{background:#111827;color:white;border:0;font-weight:700}
    .hint{font-size:13px;color:#666;line-height:1.4}
    </style></head><body>
    <div class="card">
      <h1>ControlBabies</h1>
      <p>Responsabilidades, puntos, premios y paga semanal.</p>
      <form method="post" action="/login">
        <input name="username" placeholder="Usuario" required>
        <input name="password" placeholder="Contraseña" type="password" required>
        <button>Entrar</button>
      </form>
      <p class="hint">
        Usuarios iniciales:<br>
        Marcos: <b>marcos / padre123</b><br>
        Neli: <b>neli / madre123</b><br>
        Marcos Jr.: <b>marcosjr / hijo123</b><br>
        Lidia: <b>lidia / hijo123</b>
      </p>
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
        return RedirectResponse("/child", status_code=302)

    with db() as conn:
        children = conn.execute("SELECT * FROM users WHERE role='child' AND active=1").fetchall()
        tasks = conn.execute("SELECT id, name AS title FROM actions WHERE active=1").fetchall()
        events = conn.execute("""
        SELECT e.*, t.title, u.display_name AS completed_by
        FROM task_events e
        JOIN tasks t ON t.id=e.task_id
        LEFT JOIN users u ON u.id=e.completed_by_user_id
        ORDER BY e.created_at DESC LIMIT 20
        """).fetchall()
        penalties = conn.execute("""
        SELECT p.*, c.display_name AS child, pa.display_name AS parent, t.title AS task_title
        FROM penalties p
        JOIN users c ON c.id=p.child_user_id
        JOIN users pa ON pa.id=p.parent_user_id
        LEFT JOIN tasks t ON t.id=p.task_id
        ORDER BY p.created_at DESC LIMIT 20
        """).fetchall()

    child_cards = "".join([f"<div class='card'><h3>{c['display_name']}</h3><p>Puntos actuales: <b>{points_for_child(c['id'])}</b></p></div>" for c in children])

    task_options = "".join([f"<option value='{t['id']}'>{t['title']}</option>" for t in tasks])
    child_options = "".join([f"<option value='{c['id']}'>{c['display_name']}</option>" for c in children])

    event_rows = "".join([
        f"<div class='card'><b>{e['title']}</b><br><span class='pill'>{e['status']}</span><p class='muted'>Hecha por: {e['completed_by'] or '-'} · {e['created_at']}</p>"
        f"<form method='post' action='/events/{e['id']}/approve'><button class='ok'>Aprobar</button></form>"
        f"<form method='post' action='/events/{e['id']}/reject'><button class='danger'>Rechazar</button></form></div>"
        for e in events
    ])

    penalty_rows = "".join([
        f"<div class='card'><b>{p['child']}</b> -{p['points']} puntos <span class='pill'>{p['severity']}</span>"
        f"<p>{p['reason']}</p><p class='muted'>{p['task_title'] or 'Sin tarea'} · {p['created_at']}</p>"
        f"{('<img src=' + chr(34) + p['image_path'] + chr(34) + '>') if p['image_path'] else ''}</div>"
        for p in penalties
    ])

    ensure_daily_actions()
    with db() as conn:
        today_rows = conn.execute("""
        SELECT da.*, a.name AS action_name, u.display_name AS claimed_by
        FROM daily_actions da
        JOIN actions a ON a.id=da.action_id
        LEFT JOIN users u ON u.id=da.claimed_by_user_id
        WHERE da.event_date=date('now')
        ORDER BY a.name
        """).fetchall()

    today_cards = ""
    for x in today_rows:
        controls = ""
        if x["status"] == "completed":
            controls = f"<form method='post' action='/actions/{x['action_id']}/validate'><button class='ok'>Validar</button></form><form method='post' action='/actions/{x['action_id']}/reject-daily'><button class='danger'>Rechazar</button></form>"
        today_cards += f"<div class='card critical'><b>{x['action_name']}</b><p>Estado: {x['status']} · Responsable: {x['claimed_by'] or '-'}</p>{controls}</div>"

    body = f"""
    <div class="card"><h2>Responsabilidades de hoy</h2>{today_cards}</div>
    <div class="grid">{child_cards}</div>

    <div class="card">
      <h2>Aplicar penalización</h2>
      <form method="post" action="/penalties" enctype="multipart/form-data">
        <select name="child_user_id">{child_options}</select>
        <select name="task_id"><option value="">Sin tarea concreta</option>{task_options}</select>
        <select name="severity">
          <option value="leve">Leve</option>
          <option value="media">Media</option>
          <option value="grave">Grave</option>
        </select>
        <input name="points" type="number" value="10" min="1">
        <select name="affects_allowance">
          <option value="0">No afecta directamente a paga</option>
          <option value="1">Puede afectar a paga semanal</option>
        </select>
        <input name="punishment" placeholder="Castigo opcional">
        <textarea name="reason" placeholder="Motivo de la penalización" required></textarea>
        <input name="image" type="file" accept="image/*">
        <button class="danger">Penalizar</button>
      </form>
    </div>

    <div class="card"><h2>Tareas enviadas por hijos</h2>{event_rows or '<p class="muted">Sin eventos todavía.</p>'}</div>
    <div class="card"><h2>Penalizaciones recientes</h2>{penalty_rows or '<p class="muted">Sin penalizaciones todavía.</p>'}</div>
    """
    body = """
    <div class='hero'>
      <h1>ControlBabies</h1>
      <p>Responsabilidades familiares: Arlo, Ares, puntos, paga y premios.</p>
    </div>
    """ + body
    return layout("Panel padres", body)


@app.get("/child", response_class=HTMLResponse)
def child_dashboard(request: Request):
    user = require_user(request)
    if user["role"] != "child":
        return RedirectResponse("/parent", status_code=302)

    with db() as conn:
        tasks = conn.execute("SELECT * FROM tasks WHERE active=1").fetchall()
        rewards = conn.execute("SELECT * FROM rewards WHERE active=1").fetchall()
        penalties = conn.execute("""
        SELECT p.*, t.title AS task_title
        FROM penalties p
        LEFT JOIN tasks t ON t.id=p.task_id
        WHERE p.child_user_id=?
        ORDER BY p.created_at DESC LIMIT 10
        """, (user["id"],)).fetchall()

    task_cards = "".join([
        f"<div class='card critical'><h3>{t['title']}</h3><p>{t['description']}</p><span class='pill'>OBLIGATORIA</span> <span class='pill'>{t['schedule_hint']}</span>"
        f"<p><b>+{t['points']}</b> puntos si se aprueba · <b>-{t['penalty_points']}</b> si no se hace</p>"
        f"<form method='post' action='/tasks/{t['id']}/done'><textarea name='comment' placeholder='Comentario opcional'></textarea><button class='ok'>Marcar como hecha</button></form></div>"
        for t in tasks
    ])

    reward_cards = "".join([
        f"<div class='card'><b>{r['title']}</b><p>{r['description']}</p><p>Coste: {r['cost_points']} puntos</p>"
        f"<form method='post' action='/rewards/{r['id']}/claim'><button>Canjear</button></form></div>"
        for r in rewards
    ])

    penalty_cards = "".join([
        f"<div class='card'><b>-{p['points']} puntos</b> <span class='pill'>{p['severity']}</span><p>{p['reason']}</p>"
        f"<p class='muted'>{p['task_title'] or 'Sin tarea'} · {p['created_at']}</p>"
        f"{('<img src=' + chr(34) + p['image_path'] + chr(34) + '>') if p['image_path'] else ''}</div>"
        for p in penalties
    ])

    body = f"""
    <div class="hero">
      <h2>Hola, {user['display_name']}</h2>
      <div class="score">{points_for_child(user['id'])}</div>
      <p>puntos actuales</p>
    </div>
    <div class="card"><h2>Tareas obligatorias</h2></div>
    {task_cards}
    <div class="card"><h2>Premios</h2>{reward_cards}</div>
    <div class="card"><h2>Mis penalizaciones</h2>{penalty_cards or '<p class="muted">Sin penalizaciones.</p>'}</div>
    """
    return layout("Panel hijos", body)


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
    return RedirectResponse("/child", status_code=302)


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
    return RedirectResponse("/child", status_code=302)


@app.get("/api/health")
def health():
    return JSONResponse({"status": "ok", "service": "ControlBabies", "version": "0.7.0"})


