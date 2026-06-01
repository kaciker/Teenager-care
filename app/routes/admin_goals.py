from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from core.base import db, layout
from core.auth import require_user

router = APIRouter()

def require_parent(request):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)
    return user

@router.get("/admin/goals", response_class=HTMLResponse)
def admin_goals(request: Request):
    require_parent(request)
    with db() as conn:
        goals = conn.execute("SELECT * FROM goals ORDER BY active DESC, name").fetchall()
        responsibilities = conn.execute("""
            SELECT r.*, g.name AS goal_name
            FROM responsibilities r JOIN goals g ON g.id=r.goal_id
            ORDER BY r.active DESC, g.name, r.name
        """).fetchall()
        actions = conn.execute("""
            SELECT a.*, r.name AS responsibility_name, g.name AS goal_name
            FROM actions a
            JOIN responsibilities r ON r.id=a.responsibility_id
            JOIN goals g ON g.id=r.goal_id
            ORDER BY a.active DESC, g.name, r.name, a.name
        """).fetchall()

    goal_opts = "".join([f"<option value='{g['id']}'>{g['name']}</option>" for g in goals if g["active"]])
    resp_opts = "".join([f"<option value='{r['id']}'>{r['goal_name']} · {r['name']}</option>" for r in responsibilities if r["active"]])

    body = f"""
    <div class='hero'><h1>Admin familiar</h1><p>Objetivos, responsabilidades y acciones editables.</p></div>

    <div class='card'>
      <h2>Crear objetivo</h2>
      <form method='post' action='/admin/goals/create'>
        <input name='name' placeholder='Ej: Orden y limpieza' required>
        <textarea name='description' placeholder='Descripción opcional'></textarea>
        <button>Crear objetivo</button>
      </form>
    </div>

    <div class='card'>
      <h2>Crear responsabilidad</h2>
      <form method='post' action='/admin/responsibilities/create'>
        <select name='goal_id'>{goal_opts}</select>
        <input name='name' placeholder='Ej: Habitación Marcos Jr.' required>
        <textarea name='description' placeholder='Descripción opcional'></textarea>
        <button>Crear responsabilidad</button>
      </form>
    </div>

    <div class='card'>
      <h2>Crear acción</h2>
      <form method='post' action='/admin/actions/create'>
        <select name='responsibility_id'>{resp_opts}</select>
        <input name='name' placeholder='Ej: Hacer la cama' required>
        <textarea name='description' placeholder='Descripción opcional'></textarea>
        <input name='points' type='number' value='10' min='0'>
        <select name='frequency'><option value='daily'>Diaria</option><option value='weekly'>Semanal</option><option value='manual'>Manual</option></select>
        <button>Crear acción</button>
      </form>
    </div>

    <div class='card'><h2>Objetivos</h2>
    {''.join([f"<p><b>{g['name']}</b> · {'activo' if g['active'] else 'inactivo'} <a href='/admin/goals/{g['id']}/toggle'>cambiar</a></p>" for g in goals])}
    </div>

    <div class='card'><h2>Responsabilidades</h2>
    {''.join([f"<p><b>{r['goal_name']}</b> · {r['name']} · {'activa' if r['active'] else 'inactiva'} <a href='/admin/responsibilities/{r['id']}/toggle'>cambiar</a></p>" for r in responsibilities])}
    </div>

    <div class='card'><h2>Acciones</h2>
    {''.join([f"<p><b>{a['goal_name']}</b> · {a['responsibility_name']} · {a['name']} · {a['points']} pts · {'activa' if a['active'] else 'inactiva'} <a href='/admin/actions/{a['id']}/toggle'>cambiar</a></p>" for a in actions])}
    </div>
    """
    return layout("Admin objetivos", body)

@router.post("/admin/goals/create")
def create_goal(request: Request, name: str = Form(...), description: str = Form("")):
    require_parent(request)
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO goals(name,description,active) VALUES(?,?,1)", (name.strip(), description.strip()))
    return RedirectResponse("/admin/goals", status_code=302)

@router.post("/admin/responsibilities/create")
def create_responsibility(request: Request, goal_id: int = Form(...), name: str = Form(...), description: str = Form("")):
    require_parent(request)
    with db() as conn:
        conn.execute("INSERT INTO responsibilities(goal_id,name,description,active) VALUES(?,?,?,1)", (goal_id, name.strip(), description.strip()))
    return RedirectResponse("/admin/goals", status_code=302)

@router.post("/admin/actions/create")
def create_action(request: Request, responsibility_id: int = Form(...), name: str = Form(...), description: str = Form(""), points: int = Form(10), frequency: str = Form("daily")):
    require_parent(request)
    with db() as conn:
        conn.execute("INSERT INTO actions(responsibility_id,name,description,frequency,points,active) VALUES(?,?,?,?,?,1)", (responsibility_id, name.strip(), description.strip(), frequency, points))
    return RedirectResponse("/admin/goals", status_code=302)

@router.get("/admin/goals/{item_id}/toggle")
def toggle_goal(request: Request, item_id: int):
    require_parent(request)
    with db() as conn:
        conn.execute("UPDATE goals SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (item_id,))
    return RedirectResponse("/admin/goals", status_code=302)

@router.get("/admin/responsibilities/{item_id}/toggle")
def toggle_responsibility(request: Request, item_id: int):
    require_parent(request)
    with db() as conn:
        conn.execute("UPDATE responsibilities SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (item_id,))
    return RedirectResponse("/admin/goals", status_code=302)

@router.get("/admin/actions/{item_id}/toggle")
def toggle_action(request: Request, item_id: int):
    require_parent(request)
    with db() as conn:
        conn.execute("UPDATE actions SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (item_id,))
    return RedirectResponse("/admin/goals", status_code=302)
