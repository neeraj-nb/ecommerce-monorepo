"""Stateless JWT authentication for service-to-service / gateway requests.

Tokens are issued by the user-service and signed with the shared ``JWT_SECRET``
(``settings.SECRET_KEY``). This service verifies the signature locally and trusts
the claims, so no database lookup or network call to the user-service is needed
on the hot path. The authenticated principal is a lightweight, DB-free user.
"""

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


class RemoteUser:
    """A user authenticated purely from JWT claims (no local DB row)."""

    def __init__(self, user_id, email=None, role="user"):
        self.id = user_id
        self.pk = user_id
        self.email = email
        self.role = role

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_staff(self):
        return self.role == "admin"

    def __str__(self):
        return self.email or str(self.id)


class ServiceJWTAuthentication(BaseAuthentication):
    """Verify a Bearer access token locally using the shared signing key."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword + " "):
            return None  # No credentials -> let DRF treat as anonymous.

        raw_token = header[len(self.keyword) + 1:].strip()
        try:
            token = AccessToken(raw_token)  # verifies signature, type and expiry
        except TokenError:
            raise AuthenticationFailed("Invalid or expired token")

        user = RemoteUser(
            user_id=token["user_id"],
            email=token.get("email"),
            role=token.get("role", "user"),
        )
        return (user, raw_token)

    def authenticate_header(self, request):
        return self.keyword
