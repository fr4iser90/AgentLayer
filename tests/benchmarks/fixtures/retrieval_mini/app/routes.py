"""HTTP routes for the mini benchmark workspace."""

from auth.middleware import verify_token

# bench_login_handler
def bench_login(username, password):
    if not verify_token(password):
        return {"ok": False, "error": "invalid credentials"}
    return {"ok": True, "user": username}
