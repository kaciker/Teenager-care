from core.base import db, now

def add_history(
    action_id,
    actor_user_id,
    event_type,
    notes="",
    target_user_id=None,
    event_date=None
):
    with db() as conn:
        conn.execute(
            """
            INSERT INTO action_history
            (
                action_id,
                event_date,
                actor_user_id,
                event_type,
                target_user_id,
                notes
            )
            VALUES (?,?,?,?,?,?)
            """,
            (
                action_id,
                event_date or now()[:10],
                actor_user_id,
                event_type,
                target_user_id,
                notes
            )
        )
