from datetime import date

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from core.base import db, now, layout
from core.auth import require_user

router = APIRouter()

def ensure_daily_actions():
    today = date.today().isoformat()
    with db() as conn:
        rows = conn.execute("SELECT id FROM actions WHERE active=1").fetchall()
        for r in rows:
            conn.execute(
                "INSERT OR IGNORE INTO daily_actions(action_id,event_date,status) VALUES(?,?,?)",
                (r["id"], today, "pending")
            )
    return today


@router.get("/today", response_class=HTMLResponse)
def today_responsibilities(request: Request):
    user = require_user(request)
    today = ensure_daily_actions()

    with db() as conn:
        rows = conn.execute("""
        SELECT da.*, a.name AS action_name, a.points, r.name AS responsibility_name,
               g.name AS goal_name, u.display_name AS claimed_by
        FROM daily_actions da
        JOIN actions a ON a.id=da.action_id
        JOIN responsibilities r ON r.id=a.responsibility_id
        JOIN goals g ON g.id=r.goal_id
        LEFT JOIN users u ON u.id=da.claimed_by_user_id
        WHERE da.event_date=?
        ORDER BY g.name, r.name, a.name
        """, (today,)).fetchall()

    cards = ""
    for x in rows:
        if x["status"] == "pending":
            action = f"<form method='post' action='/actions/{x['action_id']}/claim'><button>Yo me encargo</button></form>" if user["role"] == "child" else "<span class='pill'>Sin responsable</span>"
        elif x["status"] == "claimed":
            if user["role"] == "child" and x["claimed_by_user_id"] == user["id"]:
                action = f"<form method='post' action='/actions/{x['action_id']}/complete'><button class='ok'>Marcar realizada</button></form>"
            else:
                action = f"<span class='pill'>La ha asumido {x['claimed_by']}</span>"
        elif x["status"] == "completed":
            action = f"<span class='pill'>Realizada por {x['claimed_by']} · pendiente validar</span>"
        elif x["status"] == "validated":
            action = f"<span class='pill'>Validada</span>"
        else:
            action = f"<span class='pill'>{x['status']}</span>"

        cards += f"""
        <div class='card critical'>
          <h3>{x['action_name']}</h3>
          <p class='muted'>{x['goal_name']} · {x['responsibility_name']}</p>
          <p>Estado: <b>{x['status']}</b></p>
          <p>Puntos: <b>{x['points']}</b></p>
          {action}
        </div>
        """

    body = f"""
    <div class='hero'>
      <h1>Responsabilidades de hoy</h1>
      <p>{today}</p>
    </div>
    {cards}
    """

    return layout("Responsabilidades de hoy", body)


@router.post("/actions/{action_id}/claim")
def claim_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)
    today = ensure_daily_actions()
    with db() as conn:
        conn.execute("""
        UPDATE daily_actions
        SET status='claimed', claimed_by_user_id=?, claimed_at=?
        WHERE action_id=? AND event_date=? AND status='pending'
        """, (user["id"], now(), action_id, today))
        conn.execute("""
        INSERT INTO action_history(action_id,event_date,actor_user_id,event_type,notes)
        VALUES(?,?,?,?,?)
        """, (action_id, today, user["id"], "claimed", "asumió la acción"))
    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/complete")
def complete_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)
    today = ensure_daily_actions()
    with db() as conn:
        conn.execute("""
        UPDATE daily_actions
        SET status='completed', completed_by_user_id=?, completed_at=?
        WHERE action_id=? AND event_date=? AND claimed_by_user_id=? AND status='claimed'
        """, (user["id"], now(), action_id, today, user["id"]))
        conn.execute("""
        INSERT INTO action_history(action_id,event_date,actor_user_id,event_type,notes)
        VALUES(?,?,?,?,?)
        """, (action_id, today, user["id"], "completed", "marcó la acción como realizada"))
    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/validate")
def validate_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)
    today = ensure_daily_actions()
    with db() as conn:
        conn.execute("""
        UPDATE daily_actions
        SET status='validated', validated_by_user_id=?, validated_at=?
        WHERE action_id=? AND event_date=? AND status='completed'
        """, (user["id"], now(), action_id, today))
        conn.execute("""
        INSERT INTO action_history(action_id,event_date,actor_user_id,event_type,notes)
        VALUES(?,?,?,?,?)
        """, (action_id, today, user["id"], "validated", "validó la acción"))
    return RedirectResponse("/parent", status_code=302)


@router.post("/actions/{action_id}/reject-daily")
def reject_daily_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)
    today = ensure_daily_actions()
    with db() as conn:
        conn.execute("""
        UPDATE daily_actions
        SET status='rejected', validated_by_user_id=?, validated_at=?
        WHERE action_id=? AND event_date=? AND status='completed'
        """, (user["id"], now(), action_id, today))
        conn.execute("""
        INSERT INTO action_history(action_id,event_date,actor_user_id,event_type,notes)
        VALUES(?,?,?,?,?)
        """, (action_id, today, user["id"], "rejected", "rechazó la acción"))
    return RedirectResponse("/parent", status_code=302)
