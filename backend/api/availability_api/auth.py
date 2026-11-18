"""Microsoft Entra ID access-token validation for the availability API.

The dashboard (a single-page app on GitHub Pages) signs users in with the
authorization code flow + PKCE and sends the access token as a bearer token.
This module checks, for every request:
  * signature (tenant signing keys), expiry, audience (this API) and issuer (this tenant)
  * the delegated scope (Availability.Read)
  * the calling client app (the dashboard's client ID)
  * the user: no guest accounts and, optionally, an allowed UPN domain (contoso.day)
"""
import os

import jwt
from jwt import PyJWKClient

TENANT_ID = os.environ.get("AUTH_TENANT_ID", "")
API_CLIENT_ID = os.environ.get("AUTH_API_CLIENT_ID", "")
APP_ID_URI = os.environ.get("AUTH_API_APP_ID_URI") or ("api://" + API_CLIENT_ID)
REQUIRED_SCOPE = os.environ.get("AUTH_REQUIRED_SCOPE", "Availability.Read")
ALLOWED_CLIENTS = {c.strip() for c in os.environ.get("AUTH_ALLOWED_CLIENT_IDS", "").split(",") if c.strip()}
ALLOWED_DOMAINS = {d.strip().lower().lstrip("@") for d in os.environ.get("AUTH_ALLOWED_DOMAINS", "").split(",") if d.strip()}
ALLOW_GUESTS = os.environ.get("AUTH_ALLOW_GUESTS", "false").lower() == "true"

ISSUERS = {"https://login.microsoftonline.com/%s/v2.0" % TENANT_ID, "https://sts.windows.net/%s/" % TENANT_ID}
_jwks = PyJWKClient("https://login.microsoftonline.com/%s/discovery/v2.0/keys" % TENANT_ID,
                    cache_keys=True, lifespan=21600, timeout=10)


class AuthError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def validate(authorization):
    if not TENANT_ID or not API_CLIENT_ID:
        raise AuthError(500, "auth_not_configured", "API authentication settings are missing.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError(401, "missing_token", "Sign in is required.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=[API_CLIENT_ID, APP_ID_URI],
                            options={"require": ["exp", "iss", "aud"]}, leeway=120)
    except jwt.ExpiredSignatureError:
        raise AuthError(401, "token_expired", "The access token has expired.")
    except (jwt.PyJWTError, jwt.PyJWKClientError) as e:
        raise AuthError(401, "invalid_token", "The access token is not valid (%s)." % type(e).__name__)

    if claims.get("iss") not in ISSUERS or claims.get("tid") != TENANT_ID:
        raise AuthError(401, "wrong_tenant", "The token was not issued by the expected tenant.")
    if REQUIRED_SCOPE not in (claims.get("scp") or "").split():
        raise AuthError(403, "missing_scope", "The token does not carry the %s scope." % REQUIRED_SCOPE)
    client = claims.get("azp") or claims.get("appid")
    if ALLOWED_CLIENTS and client not in ALLOWED_CLIENTS:
        raise AuthError(403, "client_not_allowed", "This client application is not allowed to call the API.")
    idp = claims.get("idp")
    if not ALLOW_GUESTS and idp and idp not in ISSUERS:
        raise AuthError(403, "guest_not_allowed", "Guest accounts can't use this dashboard.")
    user = (claims.get("preferred_username") or claims.get("upn") or claims.get("unique_name") or "").lower()
    if ALLOWED_DOMAINS and user.rsplit("@", 1)[-1] not in ALLOWED_DOMAINS:
        raise AuthError(403, "domain_not_allowed",
                        "Only %s accounts can use this dashboard." % ", ".join(sorted(ALLOWED_DOMAINS)))
    return claims
