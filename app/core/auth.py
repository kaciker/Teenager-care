from fastapi import Request, HTTPException
from .base import db, sessions

def current_user(request: Request):
    token = request.cookies.get("cb_session")
    if not token or token not in sessions:
        return None
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE id=? AND active=1", (sessions[token],)).fetchone()

def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
