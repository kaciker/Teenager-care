from datetime import date

from core.base import db, now


def add_history(
    action_id: int,
    actor_user_id: int,
    event_type: str,
    notes: str = "",
    target_user_id: int | None = None,
    event_date: str | None = None,
    conn=None,
):
    """Insert one action history event.

    A caller can pass an existing SQLite connection to avoid nested writes.
    """
    event_date = event_date or date.today().isoformat()

    sql = """
    INSERT INTO action_history(
        action_id, event_date, actor_user_id, event_type,
        target_user_id, notes, created_at
    )
    VALUES(?,?,?,?,?,?,?)
    """
    params = (
        action_id,
        event_date,
        actor_user_id,
        event_type,
        target_user_id,
        notes,
        now(),
    )

    if conn is not None:
        conn.execute(sql, params)
        return

    with db() as own_conn:
        own_conn.execute(sql, params)
