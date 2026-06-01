from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from core.base import db, now, layout
from core.auth import require_user
from core.points import ensure_points_schema, points_balance, add_points_entry

router = APIRouter()


@router.get("/allowance", response_class=HTMLResponse)
def allowance_admin(request: Request):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    ensure_points_schema()

    with db() as conn:
        children = conn.execute("""
        SELECT id, display_name
        FROM users
        WHERE role='child' AND active=1
        ORDER BY display_name
        """).fetchall()

        rewards = conn.execute("""
        SELECT *
        FROM reward_items
        WHERE active=1
        ORDER BY cost_points, title
        """).fetchall()

        redemptions = conn.execute("""
        SELECT rr.*, ri.title, u.display_name AS child_name
        FROM reward_redemptions rr
        JOIN reward_items ri ON ri.id=rr.reward_item_id
        JOIN users u ON u.id=rr.child_user_id
        ORDER BY rr.id DESC
        LIMIT 30
        """).fetchall()

        balances = {c["id"]: points_balance(c["id"], conn=conn) for c in children}

    child_cards = ""
    for child in children:
        child_cards += f"""
        <div class='card'>
          <h3>{child['display_name']}</h3>
          <div class='score'>{balances[child['id']]}</div>
          <p class='muted'>Saldo nuevo v0.8 basado en point_ledger.</p>
        </div>
        """

    reward_cards = ""
    for reward in rewards:
        reward_cards += f"""
        <div class='card'>
          <h3>{reward['title']}</h3>
          <p>{reward['description'] or ''}</p>
          <p><b>{reward['cost_points']}</b> puntos · {reward['reward_type']}</p>
        </div>
        """

    redemption_cards = ""
    for r in redemptions:
        actions = ""
        if r["status"] == "requested":
            actions = f"""
            <form method='post' action='/allowance/redemptions/{r['id']}/approve'>
              <button class='ok'>Aprobar</button>
            </form>
            <form method='post' action='/allowance/redemptions/{r['id']}/reject' style='margin-top:10px'>
              <button>Rechazar</button>
            </form>
            """

        redemption_cards += f"""
        <div class='card critical'>
          <h3>{r['child_name']} · {r['title']}</h3>
          <p><b>Estado:</b> {r['status']} · <b>Coste:</b> {r['cost_points']} puntos</p>
          <p class='muted'>{r['requested_at']}</p>
          {actions}
        </div>
        """

    body = f"""
    <div class='hero'>
      <h1>Puntos, premios y paga</h1>
      <p>Modelo nuevo v0.8 separado de rewards/reward_claims legacy.</p>
    </div>

    <div class='grid'>
      {child_cards}
    </div>

    <div class='card critical'>
      <h2>Crear premio</h2>
      <form method='post' action='/allowance/rewards/create'>
        <label>Título</label>
        <input name='title' required>

        <label>Descripción</label>
        <textarea name='description'></textarea>

        <label>Coste en puntos</label>
        <input name='cost_points' type='number' value='10' min='1'>

        <label>Tipo</label>
        <select name='reward_type'>
          <option value='other'>Otro</option>
          <option value='money'>Paga</option>
          <option value='privilege'>Privilegio</option>
          <option value='experience'>Experiencia</option>
        </select>

        <label>Valor paga en céntimos, opcional</label>
        <input name='allowance_value_cents' type='number' value='0' min='0'>

        <button>Crear premio</button>
      </form>
    </div>

    <div class='card'>
      <h2>Premios activos</h2>
      {reward_cards or '<p class="muted">Sin premios activos.</p>'}
    </div>

    <div class='card'>
      <h2>Solicitudes recientes</h2>
      {redemption_cards or '<p class="muted">Sin solicitudes todavía.</p>'}
    </div>
    """

    return layout("Puntos, premios y paga", body)


@router.post("/allowance/rewards/create")
def create_reward_item(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    cost_points: int = Form(...),
    reward_type: str = Form("other"),
    allowance_value_cents: int = Form(0),
):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    ensure_points_schema()

    with db() as conn:
        conn.execute("""
        INSERT INTO reward_items(
            code, title, description, cost_points,
            reward_type, allowance_value_cents, active, created_at
        )
        VALUES(?,?,?,?,?,?,1,?)
        """, (
            None,
            title.strip(),
            description.strip(),
            max(1, int(cost_points or 1)),
            reward_type,
            max(0, int(allowance_value_cents or 0)),
            now(),
        ))

    return RedirectResponse("/allowance", status_code=302)


@router.post("/allowance/redemptions/{redemption_id}/approve")
def approve_reward_redemption(request: Request, redemption_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    ensure_points_schema()

    with db() as conn:
        redemption = conn.execute("""
        SELECT rr.*, ri.title
        FROM reward_redemptions rr
        JOIN reward_items ri ON ri.id=rr.reward_item_id
        WHERE rr.id=? AND rr.status='requested'
        """, (redemption_id,)).fetchone()

        if not redemption:
            raise HTTPException(status_code=404)

        balance = points_balance(redemption["child_user_id"], conn=conn)
        if balance < redemption["cost_points"]:
            raise HTTPException(status_code=400, detail="Saldo insuficiente.")

        conn.execute("""
        UPDATE reward_redemptions
        SET status='approved', decided_by_user_id=?, decided_at=?
        WHERE id=? AND status='requested'
        """, (user["id"], now(), redemption_id))

        add_points_entry(
            redemption["child_user_id"],
            -int(redemption["cost_points"]),
            "reward_approved",
            redemption_id,
            f"Premio aprobado: {redemption['title']}",
            created_by_user_id=user["id"],
            conn=conn,
        )

    return RedirectResponse("/allowance", status_code=302)


@router.post("/allowance/redemptions/{redemption_id}/reject")
def reject_reward_redemption(request: Request, redemption_id: int):
    user = require_user(request)
    if user["role"] != "parent":
        raise HTTPException(status_code=403)

    ensure_points_schema()

    with db() as conn:
        conn.execute("""
        UPDATE reward_redemptions
        SET status='rejected', decided_by_user_id=?, decided_at=?
        WHERE id=? AND status='requested'
        """, (user["id"], now(), redemption_id))

    return RedirectResponse("/allowance", status_code=302)


@router.get("/my/rewards", response_class=HTMLResponse)
def my_rewards(request: Request):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    ensure_points_schema()

    with db() as conn:
        balance = points_balance(user["id"], conn=conn)

        rewards = conn.execute("""
        SELECT *
        FROM reward_items
        WHERE active=1
        ORDER BY cost_points, title
        """).fetchall()

        claims = conn.execute("""
        SELECT rr.*, ri.title
        FROM reward_redemptions rr
        JOIN reward_items ri ON ri.id=rr.reward_item_id
        WHERE rr.child_user_id=?
        ORDER BY rr.id DESC
        LIMIT 20
        """, (user["id"],)).fetchall()

    reward_cards = ""
    for reward in rewards:
        can_claim = balance >= reward["cost_points"]
        button = (
            f"<form method='post' action='/my/rewards/{reward['id']}/claim'><button>Canjear</button></form>"
            if can_claim
            else "<span class='pill'>Saldo insuficiente</span>"
        )

        reward_cards += f"""
        <div class='card'>
          <h3>{reward['title']}</h3>
          <p>{reward['description'] or ''}</p>
          <p><b>{reward['cost_points']}</b> puntos</p>
          {button}
        </div>
        """

    claim_cards = ""
    for c in claims:
        claim_cards += f"""
        <div class='card critical'>
          <h3>{c['title']}</h3>
          <p><b>Estado:</b> {c['status']} · <b>Coste:</b> {c['cost_points']} puntos</p>
          <p class='muted'>{c['requested_at']}</p>
        </div>
        """

    body = f"""
    <div class='hero'>
      <h1>Mis premios</h1>
      <div class='score'>{balance}</div>
      <p>Puntos disponibles.</p>
    </div>

    <div class='card'>
      <h2>Premios disponibles</h2>
      {reward_cards or '<p class="muted">Sin premios disponibles.</p>'}
    </div>

    <div class='card'>
      <h2>Mis solicitudes</h2>
      {claim_cards or '<p class="muted">Todavía no has pedido premios.</p>'}
    </div>
    """

    return layout("Mis premios", body)


@router.post("/my/rewards/{reward_item_id}/claim")
def claim_reward_item(request: Request, reward_item_id: int):
    user = require_user(request)
    if user["role"] != "child":
        raise HTTPException(status_code=403)

    ensure_points_schema()

    with db() as conn:
        reward = conn.execute("""
        SELECT *
        FROM reward_items
        WHERE id=? AND active=1
        """, (reward_item_id,)).fetchone()

        if not reward:
            raise HTTPException(status_code=404)

        balance = points_balance(user["id"], conn=conn)
        if balance < reward["cost_points"]:
            raise HTTPException(status_code=400, detail="Saldo insuficiente.")

        conn.execute("""
        INSERT INTO reward_redemptions(
            reward_item_id, child_user_id, status,
            cost_points, requested_at
        )
        VALUES(?,?,?,?,?)
        """, (
            reward_item_id,
            user["id"],
            "requested",
            int(reward["cost_points"]),
            now(),
        ))

    return RedirectResponse("/my/rewards", status_code=302)
