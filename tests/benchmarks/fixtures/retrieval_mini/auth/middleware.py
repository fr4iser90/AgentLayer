"""Authentication middleware for the mini benchmark workspace."""

from __future__ import annotations


class AuthMiddleware:
    def verify_token(self, token):
        return bool(token and token.startswith("bench_"))


# bench_verify_token
def verify_token(token):
    return AuthMiddleware().verify_token(token)
