from core.base import db, now


def ensure_points_schema(conn=None):
    """Create the new point/reward/allowance model without touching legacy rewards."""
    def apply(c):
        c.execute("""
        CREATE TABLE IF NOT EXISTS point_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_user_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id INTEGER,
            description TEXT NOT NULL DEFAULT '',
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS allowance_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_user_id INTEGER NOT NULL UNIQUE,
            weekly_allowance_cents INTEGER NOT NULL DEFAULT 0,
            points_to_cents INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS reward_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT NOT NULL,
            description TEXT,
            cost_points INTEGER NOT NULL,
            reward_type TEXT NOT NULL DEFAULT 'other',
            allowance_value_cents INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS reward_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reward_item_id INTEGER NOT NULL,
            child_user_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('requested','approved','rejected')),
            cost_points INTEGER NOT NULL,
            requested_at TEXT NOT NULL,
            decided_by_user_id INTEGER,
            decided_at TEXT
        )
        """)

        c.execute("""
        CREATE INDEX IF NOT EXISTS idx_point_ledger_child
        ON point_ledger(child_user_id, created_at)
        """)

        c.execute("""
        CREATE INDEX IF NOT EXISTS idx_reward_redemptions_child
        ON reward_redemptions(child_user_id, status)
        """)

        defaults = [
            ("extra_allowance_1", "Extra de paga", "Canjear puntos por paga extra.", 50, "money", 100),
            ("choose_movie", "Elegir película", "Elegir la película familiar.", 20, "privilege", 0),
            ("extra_screen_time", "Tiempo extra de pantalla", "Tiempo extra pactado con los padres.", 30, "privilege", 0),
        ]

        for item in defaults:
            c.execute("""
            INSERT OR IGNORE INTO reward_items(
                code, title, description, cost_points,
                reward_type, allowance_value_cents, active, created_at
            )
            VALUES(?,?,?,?,?,?,1,?)
            """, (*item, now()))

    if conn is not None:
        apply(conn)
        return

    with db() as own_conn:
        apply(own_conn)


def add_points_entry(
    child_user_id: int,
    points: int,
    source_type: str,
    source_id: int | None,
    description: str,
    created_by_user_id: int | None = None,
    conn=None,
):
    """Add one entry to the point ledger and return its id."""
    points = int(points or 0)
    if points == 0:
        return None

    ensure_points_schema(conn=conn)

    sql = """
    INSERT INTO point_ledger(
        child_user_id, points, source_type, source_id,
        description, created_by_user_id, created_at
    )
    VALUES(?,?,?,?,?,?,?)
    """
    params = (
        child_user_id,
        points,
        source_type,
        source_id,
        description,
        created_by_user_id,
        now(),
    )

    if conn is not None:
        return conn.execute(sql, params).lastrowid

    with db() as own_conn:
        return own_conn.execute(sql, params).lastrowid


def points_balance(child_user_id: int, conn=None) -> int:
    """Return current balance for one child."""
    ensure_points_schema(conn=conn)

    sql = "SELECT COALESCE(SUM(points),0) AS value FROM point_ledger WHERE child_user_id=?"

    if conn is not None:
        return int(conn.execute(sql, (child_user_id,)).fetchone()["value"])

    with db() as own_conn:
        return int(own_conn.execute(sql, (child_user_id,)).fetchone()["value"])
