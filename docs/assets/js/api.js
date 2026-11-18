// Calls the availability API with the user's Entra ID access token.
import { accessToken } from "./auth.js";

const cfg = window.ASA_CONFIG || {};
const cache = new Map();

export class ApiError extends Error {
  constructor(status, code, message) { super(message || code); this.status = status; this.code = code; }
}

export async function get(path, { fresh = false } = {}) {
  if (!fresh && cache.has(path)) return cache.get(path);
  const p = (async () => {
    let tok = await accessToken();
    if (!tok) throw new ApiError(401, "signed_out", "Please sign in.");
    let res = await call(path, tok);
    if (res.status === 401) {               // token expired or revoked: refresh once
      tok = await accessToken(true);
      if (!tok) throw new ApiError(401, "signed_out", "Your session ended. Please sign in again.");
      res = await call(path, tok);
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, body?.error?.code || "http_" + res.status, body?.error?.message || res.statusText);
    return body;
  })();
  cache.set(path, p);
  p.catch(() => cache.delete(path));
  return p;
}

async function call(path, tok) {
  try {
    return await fetch(cfg.apiBase.replace(/\/$/, "") + path, { headers: { Authorization: "Bearer " + tok } });
  } catch (e) {
    throw new ApiError(0, "network", "The API can't be reached (network or CORS).");
  }
}

export function clearCache() { cache.clear(); }
