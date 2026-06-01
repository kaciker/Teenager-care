from datetime import date

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from core.base import db, now, layout
from core.auth import require_user
from core.history import add_history
from core.points import add_points_entry

router = APIRouter()


def ensure_transfer_schema():
    """Keep the transfer table compatible with the daily action model."""
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS action_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id INTEGER NOT NULL,
            event_date TEXT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            responded_at TEXT
        )
        """)

        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(action_transfers)").fetchall()
        }

        if "event_date" not in cols:
            conn.execute("ALTER TABLE action_transfers ADD COLUMN event_date TEXT")

        if "responded_at" not in cols:
            conn.execute("ALTER TABLE action_transfers ADD COLUMN responded_at TEXT")

        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_transfers_daily
        ON action_transfers(action_id, event_date, status)
        """)


def ensure_daily_actions():
    ensure_transfer_schema()
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
               g.name AS goal_name, u.display_name AS claimed_by,
               tr.id AS transfer_id,
               tr.from_user_id AS transfer_from_user_id,
               tr.to_user_id AS transfer_to_user_id,
               tu.display_name AS transfer_to_name,
               fu.display_name AS transfer_from_name
        FROM daily_actions da
        JOIN actions a ON a.id=da.action_id
        JOIN responsibilities r ON r.id=a.responsibility_id
        JOIN goals g ON g.id=r.goal_id
        LEFT JOIN users u ON u.id=da.claimed_by_user_id
        LEFT JOIN action_transfers tr
          ON tr.action_id=da.action_id
         AND tr.event_date=da.event_date
         AND tr.status='pending'
        LEFT JOIN users tu ON tu.id=tr.to_user_id
        LEFT JOIN users fu ON fu.id=tr.from_user_id
        WHERE da.event_date=?
        ORDER BY g.name, r.name, a.name
        """, (today,)).fetchall()

        children = conn.execute("""
        SELECT id, display_name
        FROM users
        WHERE role='child' AND active=1
        ORDER BY display_name
        """).fetchall()

    cards = ""
    for x in rows:
        action = ""

        if x["status"] == "pending":
            if user["role"] == "child":
                action = f"<form method='post' action='/actions/{x['action_id']}/claim'><button>Yo me encargo</button></form>"
            else:
                action = "<span class='pill'>Sin responsable</span>"

        elif x["status"] == "claimed":
            if user["role"] == "child" and x["claimed_by_user_id"] == user["id"]:
                options = "".join(
                    f"<option value='{c['id']}'>{c['display_name']}</option>"
                    for c in children
                    if c["id"] != user["id"]
                )

                transfer_form = ""
                if options:
                    transfer_form = f"""
                    <form method='post' action='/actions/{x['action_id']}/transfer-request' style='margin-top:10px'>
                      <select name='to_user_id'>{options}</select>
                      <button>Ceder acción</button>
                    </form>
                    """

                action = f"""
                <form method='post' action='/actions/{x['action_id']}/complete'>
                  <button class='ok'>Marcar realizada</button>
                </form>
                {transfer_form}
                """
            else:
                action = f"<span class='pill'>La ha asumido {x['claimed_by']}</span>"

        elif x["status"] == "transfer_requested":
            if user["role"] == "child" and x["transfer_to_user_id"] == user["id"]:
                action = f"""
                <p class='muted'>{x['transfer_from_name']} quiere cederte esta acción.</p>
                <form method='post' action='/actions/{x['action_id']}/transfer-accept'>
                  <button class='ok'>Aceptar cesión</button>
                </form>
                <form method='post' action='/actions/{x['action_id']}/transfer-reject' style='margin-top:10px'>
                  <button>Rechazar cesión</button>
                </form>
                """
            elif user["role"] == "child" and x["transfer_from_user_id"] == user["id"]:
                action = f"<span class='pill'>Has pedido ceder la acción a {x['transfer_to_name']}</span>"
            else:
                action = f"<span class='pill'>Cesión pendiente: {x['transfer_from_name']} → {x['transfer_to_name']}</span>"

        elif x["status"] == "completed":
            action = f"<span class='pill'>Realizada por {x['claimed_by']} · pendiente validar</span>"

        elif x["status"] == "validated":
            action = "<span class='pill'>Validada</span>"

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

    return layout("Responsabilidades de hoy", body, user=user)


@router.post("/actions/{action_id}/claim")
def claim_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    today = ensure_daily_actions()

    with db() as conn:
        cur = conn.execute("""
        UPDATE daily_actions
        SET status='claimed', claimed_by_user_id=?, claimed_at=?
        WHERE action_id=? AND event_date=? AND status='pending'
        """, (user["id"], now(), action_id, today))

        if cur.rowcount:
            add_history(action_id, user["id"], "claimed", "asumió la acción", event_date=today, conn=conn)

    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/complete")
def complete_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    today = ensure_daily_actions()

    with db() as conn:
        cur = conn.execute("""
        UPDATE daily_actions
        SET status='completed', completed_by_user_id=?, completed_at=?
        WHERE action_id=? AND event_date=? AND claimed_by_user_id=? AND status='claimed'
        """, (user["id"], now(), action_id, today, user["id"]))

        if cur.rowcount:
            add_history(action_id, user["id"], "completed", "marcó la acción como realizada", event_date=today, conn=conn)

    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/transfer-request")
def request_transfer(request: Request, action_id: int, to_user_id: int = Form(...)):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    if to_user_id == user["id"]:
        raise HTTPException(status_code=400, detail="No puedes cederte una acción a ti mismo.")

    today = ensure_daily_actions()

    with db() as conn:
        target = conn.execute("""
        SELECT id, display_name
        FROM users
        WHERE id=? AND role='child' AND active=1
        """, (to_user_id,)).fetchone()

        if not target:
            raise HTTPException(status_code=400, detail="Usuario destino no válido.")

        cur = conn.execute("""
        UPDATE daily_actions
        SET status='transfer_requested'
        WHERE action_id=? AND event_date=? AND claimed_by_user_id=? AND status='claimed'
        """, (action_id, today, user["id"]))

        if cur.rowcount:
            conn.execute("""
            UPDATE action_transfers
            SET status='rejected', responded_at=?
            WHERE action_id=? AND event_date=? AND status='pending'
            """, (now(), action_id, today))

            conn.execute("""
            INSERT INTO action_transfers(action_id, event_date, from_user_id, to_user_id, status, created_at)
            VALUES(?,?,?,?,?,?)
            """, (action_id, today, user["id"], to_user_id, "pending", now()))

            add_history(
                action_id,
                user["id"],
                "transfer_requested",
                f"solicitó ceder la acción a {target['display_name']}",
                target_user_id=to_user_id,
                event_date=today,
                conn=conn,
            )

    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/transfer-accept")
def accept_transfer(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    today = ensure_daily_actions()

    with db() as conn:
        tr = conn.execute("""
        SELECT tr.*, fu.display_name AS from_name
        FROM action_transfers tr
        JOIN users fu ON fu.id=tr.from_user_id
        WHERE tr.action_id=? AND tr.event_date=? AND tr.to_user_id=? AND tr.status='pending'
        ORDER BY tr.id DESC
        LIMIT 1
        """, (action_id, today, user["id"])).fetchone()

        if tr:
            cur = conn.execute("""
            UPDATE action_transfers
            SET status='accepted', responded_at=?
            WHERE id=? AND status='pending'
            """, (now(), tr["id"]))

            if cur.rowcount:
                conn.execute("""
                UPDATE daily_actions
                SET status='claimed', claimed_by_user_id=?, claimed_at=?
                WHERE action_id=? AND event_date=? AND status='transfer_requested'
                """, (user["id"], now(), action_id, today))

                add_history(
                    action_id,
                    user["id"],
                    "transfer_accepted",
                    f"aceptó la acción cedida por {tr['from_name']}",
                    target_user_id=tr["from_user_id"],
                    event_date=today,
                    conn=conn,
                )
                add_history(
                    action_id,
                    tr["from_user_id"],
                    "transferred",
                    f"cedió la acción a {user['display_name']}",
                    target_user_id=user["id"],
                    event_date=today,
                    conn=conn,
                )

    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/transfer-reject")
def reject_transfer(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    today = ensure_daily_actions()

    with db() as conn:
        tr = conn.execute("""
        SELECT tr.*, fu.display_name AS from_name
        FROM action_transfers tr
        JOIN users fu ON fu.id=tr.from_user_id
        WHERE tr.action_id=? AND tr.event_date=? AND tr.to_user_id=? AND tr.status='pending'
        ORDER BY tr.id DESC
        LIMIT 1
        """, (action_id, today, user["id"])).fetchone()

        if tr:
            cur = conn.execute("""
            UPDATE action_transfers
            SET status='rejected', responded_at=?
            WHERE id=? AND status='pending'
            """, (now(), tr["id"]))

            if cur.rowcount:
                conn.execute("""
                UPDATE daily_actions
                SET status='claimed'
                WHERE action_id=? AND event_date=? AND status='transfer_requested'
                """, (action_id, today))

                add_history(
                    action_id,
                    user["id"],
                    "transfer_rejected",
                    f"rechazó la cesión de la acción de {tr['from_name']}",
                    target_user_id=tr["from_user_id"],
                    event_date=today,
                    conn=conn,
                )

    return RedirectResponse("/today", status_code=302)


@router.post("/actions/{action_id}/validate")
def validate_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    today = ensure_daily_actions()

    with db() as conn:
        target = conn.execute("""
        SELECT da.claimed_by_user_id, a.points, a.name AS action_name
        FROM daily_actions da
        JOIN actions a ON a.id=da.action_id
        WHERE da.action_id=? AND da.event_date=? AND da.status='completed'
        """, (action_id, today)).fetchone()

        cur = conn.execute("""
        UPDATE daily_actions
        SET status='validated', validated_by_user_id=?, validated_at=?
        WHERE action_id=? AND event_date=? AND status='completed'
        """, (user["id"], now(), action_id, today))

        if cur.rowcount:
            add_history(action_id, user["id"], "validated", "validó la acción", event_date=today, conn=conn)

            if target and target["claimed_by_user_id"]:
                add_points_entry(
                    target["claimed_by_user_id"],
                    int(target["points"] or 0),
                    "action_validated",
                    action_id,
                    f"Acción validada: {target['action_name']}",
                    created_by_user_id=user["id"],
                    conn=conn,
                )

    return RedirectResponse("/parent", status_code=302)


@router.post("/actions/{action_id}/reject-daily")
def reject_daily_action(request: Request, action_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    today = ensure_daily_actions()

    with db() as conn:
        cur = conn.execute("""
        UPDATE daily_actions
        SET status='rejected', validated_by_user_id=?, validated_at=?
        WHERE action_id=? AND event_date=? AND status='completed'
        """, (user["id"], now(), action_id, today))

        if cur.rowcount:
            add_history(action_id, user["id"], "rejected", "rechazó la acción", event_date=today, conn=conn)

    return RedirectResponse("/parent", status_code=302)
