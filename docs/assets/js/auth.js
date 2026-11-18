// Microsoft Entra ID sign-in for a static single-page app (no secret):
// OAuth 2.0 authorization code flow with PKCE against the v2.0 endpoints.
// Tokens live in sessionStorage for this browser tab only.
const cfg = window.ASA_CONFIG || {};
const KEY = "asa.session";
const PKCE = "asa.pkce";

export class AuthError extends Error {
  constructor(code, message) { super(message || code); this.code = code; }
}

export const configured = () => Boolean(cfg.tenantId && cfg.clientId && cfg.apiScope && cfg.apiBase);
const authority = () => `https://login.microsoftonline.com/${cfg.tenantId}/oauth2/v2.0`;
const redirectUri = () => location.origin + location.pathname.replace(/index\.html$/, "");
const scopes = () => ["openid", "profile", "offline_access", cfg.apiScope].join(" ");

function b64url(buf) {
  let s = "";
  new Uint8Array(buf).forEach((b) => { s += String.fromCharCode(b); });
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function random(bytes = 48) {
  const a = new Uint8Array(bytes);
  crypto.getRandomValues(a);
  return b64url(a);
}
function decodeJwt(t) {
  try {
    const p = t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(decodeURIComponent(escape(atob(p + "===".slice((p.length + 3) % 4)))));
  } catch { return {}; }
}

export async function signIn() {
  const verifier = random(48), state = random(18), nonce = random(18);
  sessionStorage.setItem(PKCE, JSON.stringify({ verifier, state, nonce, hash: location.hash }));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const q = new URLSearchParams({
    client_id: cfg.clientId, response_type: "code", redirect_uri: redirectUri(), response_mode: "query",
    scope: scopes(), state, nonce, code_challenge: challenge, code_challenge_method: "S256", prompt: "select_account",
  });
  if (cfg.domainHint) q.set("domain_hint", cfg.domainHint);
  location.assign(`${authority()}/authorize?${q}`);
}

async function token(params) {
  const res = await fetch(`${authority()}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: cfg.clientId, scope: scopes(), ...params }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new AuthError(body.error || "token_error", body.error_description || res.statusText);
  return body;
}

function save(t, previous) {
  const id = t.id_token ? decodeJwt(t.id_token) : null;
  const s = {
    accessToken: t.access_token,
    expiresAt: Date.now() + (Number(t.expires_in || 3600) - 120) * 1000,
    refreshToken: t.refresh_token || previous?.refreshToken || null,
    account: id ? { name: id.name, username: id.preferred_username, tenantId: id.tid } : previous?.account || null,
  };
  sessionStorage.setItem(KEY, JSON.stringify(s));
  return s;
}

const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return null; } };

// Completes sign-in when Entra ID redirects back with ?code=... Returns the account or null.
export async function handleRedirect() {
  const q = new URLSearchParams(location.search);
  if (!q.has("code") && !q.has("error")) return null;
  const saved = JSON.parse(sessionStorage.getItem(PKCE) || "null");
  sessionStorage.removeItem(PKCE);
  history.replaceState(null, "", redirectUri() + (saved?.hash || ""));
  if (q.has("error")) throw new AuthError(q.get("error"), q.get("error_description"));
  if (!saved || saved.state !== q.get("state")) throw new AuthError("state_mismatch", "The sign-in response didn't match this browser tab. Please sign in again.");
  const t = await token({ grant_type: "authorization_code", code: q.get("code"), redirect_uri: redirectUri(), code_verifier: saved.verifier });
  if (t.id_token && decodeJwt(t.id_token).nonce !== saved.nonce) throw new AuthError("nonce_mismatch", "The sign-in response failed validation. Please sign in again.");
  return save(t).account;
}

export function account() { return load()?.account || null; }

export async function accessToken(force = false) {
  const s = load();
  if (!s) return null;
  if (!force && Date.now() < s.expiresAt) return s.accessToken;
  if (!s.refreshToken) return null;
  try {
    return save(await token({ grant_type: "refresh_token", refresh_token: s.refreshToken }), s).accessToken;
  } catch {
    sessionStorage.removeItem(KEY);
    return null;
  }
}

export function signOut() {
  sessionStorage.removeItem(KEY);
  const q = new URLSearchParams({ post_logout_redirect_uri: redirectUri() });
  location.assign(`${authority()}/logout?${q}`);
}
