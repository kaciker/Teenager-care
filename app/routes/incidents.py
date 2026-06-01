from datetime import datetime
from pathlib import Path
import secrets

from fastapi import APIRouter, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse

from core.base import db, now, layout, UPLOAD_DIR
from core.auth import require_user
from core.points import add_points_entry

router = APIRouter()


def ensure_incident_schema():
    """Create the new incidents/consequences model without touching legacy penalties."""
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_user_id INTEGER NOT NULL,
            parent_user_id INTEGER NOT NULL,
            action_id INTEGER,
            event_date TEXT,
            severity TEXT NOT NULL CHECK(severity IN ('leve','media','grave')),
            points INTEGER NOT NULL DEFAULT 0,
            affects_allowance INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            image_path TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS consequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            consequence_type TEXT NOT NULL DEFAULT 'manual',
            description TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            affects_allowance INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_child_created
        ON incidents(child_user_id, created_at)
        """)

        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_consequences_incident
        ON consequences(incident_id)
        """)


def _action_options(actions, selected_id=None):
    html = "<option value=''>Sin acción concreta</option>"
    for a in actions:
        selected = " selected" if selected_id and int(selected_id) == a["id"] else ""
        html += f"<option value='{a['id']}'{selected}>{a['name']}</option>"
    return html


@router.get("/incidents", response_class=HTMLResponse)
def incidents_admin(request: Request):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    ensure_incident_schema()

    with db() as conn:
        children = conn.execute("""
        SELECT id, display_name
        FROM users
        WHERE role='child' AND active=1
        ORDER BY display_name
        """).fetchall()

        actions = conn.execute("""
        SELECT id, name
        FROM actions
        WHERE active=1
        ORDER BY name
        """).fetchall()

        incidents = conn.execute("""
        SELECT i.*, cu.display_name AS child_name, pu.display_name AS parent_name,
               a.name AS action_name, c.description AS consequence_text
        FROM incidents i
        JOIN users cu ON cu.id=i.child_user_id
        JOIN users pu ON pu.id=i.parent_user_id
        LEFT JOIN actions a ON a.id=i.action_id
        LEFT JOIN consequences c ON c.incident_id=i.id AND c.active=1
        ORDER BY i.id DESC
        LIMIT 30
        """).fetchall()

    child_options = "".join(
        f"<option value='{c['id']}'>{c['display_name']}</option>"
        for c in children
    )

    incident_cards = ""
    for i in incidents:
        action_name = i["action_name"] or "Sin acción concreta"
        consequence = i["consequence_text"] or "Sin consecuencia registrada"
        allowance = "Sí" if i["affects_allowance"] else "No"
        incident_cards += f"""
        <div class='card'>
          <h3>{i['child_name']} · {i['severity']}</h3>
          <p class='muted'>{i['created_at']} · {action_name}</p>
          <p><b>Motivo:</b> {i['reason']}</p>
          <p><b>Consecuencia:</b> {consequence}</p>
          <p><b>Puntos:</b> -{i['points']} · <b>Afecta paga:</b> {allowance}</p>
        </div>
        """

    body = f"""
    <div class='hero'>
      <h1>Incidentes y consecuencias</h1>
      <p>Modelo nuevo separado de las penalizaciones legacy.</p>
    </div>

    <div class='card critical'>
      <h2>Registrar incidente</h2>
      <form method='post' action='/incidents/create' enctype='multipart/form-data'>
        <label>Hijo/a</label>
        <select name='child_user_id'>{child_options}</select>

        <label>Acción relacionada</label>
        <select name='action_id'>{_action_options(actions)}</select>

        <label>Gravedad</label>
        <select name='severity'>
          <option value='leve'>Leve</option>
          <option value='media'>Media</option>
          <option value='grave'>Grave</option>
        </select>

        <label>Puntos a descontar</label>
        <input name='points' type='number' value='0' min='0'>

        <label>
          <input type='checkbox' name='affects_allowance' value='1'>
          Afecta a la paga
        </label>

        <label>Motivo</label>
        <textarea name='reason' required></textarea>

        <label>Consecuencia</label>
        <textarea name='consequence_text'></textarea>

        <label>Evidencia opcional</label>
        <input name='image' type='file' accept='image/*'>

        <button>Registrar incidente</button>
      </form>
    </div>

    <div class='card'>
      <h2>Incidentes recientes</h2>
      {incident_cards or '<p class="muted">Sin incidentes todavía.</p>'}
    </div>
    """

    return layout("Incidentes y consecuencias", body)


@router.post("/incidents/create")
async def create_incident(
    request: Request,
    child_user_id: int = Form(...),
    action_id: str = Form(""),
    severity: str = Form(...),
    points: int = Form(0),
    affects_allowance: int = Form(0),
    reason: str = Form(...),
    consequence_text: str = Form(""),
    image: UploadFile | None = File(None),
):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    ensure_incident_schema()

    parsed_action_id = int(action_id) if str(action_id).strip() else None
    image_path = None

    if image and image.filename:
        suffix = Path(image.filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(status_code=400, detail="Formato de imagen no permitido.")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{suffix}"
        target = UPLOAD_DIR / filename
        target.write_bytes(await image.read())
        image_path = f"/uploads/{filename}"

    with db() as conn:
        child = conn.execute("""
        SELECT id
        FROM users
        WHERE id=? AND role='child' AND active=1
        """, (child_user_id,)).fetchone()

        if not child:
            raise HTTPException(status_code=400, detail="Hijo/a no válido.")

        if parsed_action_id is not None:
            action = conn.execute("""
            SELECT id
            FROM actions
            WHERE id=? AND active=1
            """, (parsed_action_id,)).fetchone()

            if not action:
                raise HTTPException(status_code=400, detail="Acción no válida.")

        incident_id = conn.execute("""
        INSERT INTO incidents(
            child_user_id, parent_user_id, action_id, event_date,
            severity, points, affects_allowance, reason, image_path,
            status, created_at
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            child_user_id,
            user["id"],
            parsed_action_id,
            datetime.now().date().isoformat(),
            severity,
            max(0, int(points or 0)),
            1 if affects_allowance else 0,
            reason.strip(),
            image_path,
            "open",
            now(),
        )).lastrowid

        clean_points = max(0, int(points or 0))

        if consequence_text.strip():
            conn.execute("""
            INSERT INTO consequences(
                incident_id, consequence_type, description,
                points, affects_allowance, active, created_at
            )
            VALUES(?,?,?,?,?,?,?)
            """, (
                incident_id,
                "manual",
                consequence_text.strip(),
                clean_points,
                1 if affects_allowance else 0,
                1,
                now(),
            ))

        if clean_points:
            add_points_entry(
                child_user_id,
                -clean_points,
                "incident",
                incident_id,
                f"Incidente: {reason.strip()}",
                created_by_user_id=user["id"],
                conn=conn,
            )

    return RedirectResponse("/incidents", status_code=302)


@router.get("/my/incidents", response_class=HTMLResponse)
def my_incidents(request: Request):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    ensure_incident_schema()

    with db() as conn:
        rows = conn.execute("""
        SELECT i.*, a.name AS action_name, c.description AS consequence_text
        FROM incidents i
        LEFT JOIN actions a ON a.id=i.action_id
        LEFT JOIN consequences c ON c.incident_id=i.id AND c.active=1
        WHERE i.child_user_id=?
        ORDER BY i.id DESC
        LIMIT 30
        """, (user["id"],)).fetchall()

    cards = ""
    for i in rows:
        action_name = i["action_name"] or "Sin acción concreta"
        consequence = i["consequence_text"] or "Sin consecuencia registrada"
        allowance = "Sí" if i["affects_allowance"] else "No"
        cards += f"""
        <div class='card critical'>
          <h3>{i['severity']} · -{i['points']} puntos</h3>
          <p class='muted'>{i['created_at']} · {action_name}</p>
          <p><b>Motivo:</b> {i['reason']}</p>
          <p><b>Consecuencia:</b> {consequence}</p>
          <p><b>Afecta paga:</b> {allowance}</p>
        </div>
        """

    body = f"""
    <div class='hero'>
      <h1>Mis incidentes</h1>
      <p>Incidentes y consecuencias registrados.</p>
    </div>
    {cards or '<div class="card"><p class="muted">No tienes incidentes registrados.</p></div>'}
    """

    return layout("Mis incidentes", body)
