"""Offline tests for the API token checks (locally signed tokens, fake key set)."""
import os
import sys
import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "api"))
TENANT, API, SPA = "11111111-2222-3333-4444-555555555555", "aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"
os.environ.update({"AUTH_TENANT_ID": TENANT, "AUTH_API_CLIENT_ID": API, "AUTH_ALLOWED_CLIENT_IDS": SPA,
                   "AUTH_ALLOWED_DOMAINS": "contoso.day", "AUTH_ALLOW_GUESTS": "false"})
from availability_api import auth  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _Signing:
    key = KEY.public_key()


class _Jwks:
    def get_signing_key_from_jwt(self, token):
        return _Signing()


auth._jwks = _Jwks()


def token(key=KEY, **over):
    now = int(time.time())
    c = {"iss": "https://login.microsoftonline.com/%s/v2.0" % TENANT, "aud": API, "tid": TENANT,
         "azp": SPA, "scp": "Availability.Read", "preferred_username": "bibrani@contoso.day",
         "name": "bibrani", "iat": now, "nbf": now, "exp": now + 3600}
    c.update(over)
    c = {k: v for k, v in c.items() if v is not None}
    return "Bearer " + jwt.encode(c, key, algorithm="RS256")


class AuthTest(unittest.TestCase):
    def code(self, header):
        try:
            auth.validate(header)
            return "ok"
        except auth.AuthError as e:
            return e.code

    def test_cases(self):
        self.assertEqual(self.code(token()), "ok")
        self.assertEqual(self.code(token(aud="api://" + API)), "ok")
        self.assertEqual(self.code(None), "missing_token")
        self.assertEqual(self.code(token(key=OTHER)), "invalid_token")
        self.assertEqual(self.code(token(exp=int(time.time()) - 600)), "token_expired")
        self.assertEqual(self.code(token(aud="api://someone-else")), "invalid_token")
        self.assertEqual(self.code(token(iss="https://login.microsoftonline.com/other/v2.0")), "wrong_tenant")
        self.assertEqual(self.code(token(tid="other")), "wrong_tenant")
        self.assertEqual(self.code(token(scp="User.Read")), "missing_scope")
        self.assertEqual(self.code(token(azp="cccccccc-0000-0000-0000-000000000003")), "client_not_allowed")
        self.assertEqual(self.code(token(idp="https://sts.windows.net/another-tenant/")), "guest_not_allowed")
        self.assertEqual(self.code(token(preferred_username="someone@fabrikam.com")), "domain_not_allowed")
        self.assertEqual(self.code(token(preferred_username="BIBRANI@CONTOSO.DAY")), "ok")


if __name__ == "__main__":
    unittest.main()
