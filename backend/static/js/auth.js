// Session helpers. The server keeps the session in an HttpOnly cookie; we only cache /auth/me.
import { api } from './api.js';

let cached;       // undefined = not loaded yet, null = logged out
export async function getUser(force = false) {
  if (cached !== undefined && !force) return cached;
  try { cached = (await api.me()).user; }
  catch (e) { if (e.status === 401) cached = null; else throw e; }
  return cached;
}
export function setUser(u) { cached = u; }
export const homeFor = (u) => (u && u.role === 'ADMIN' ? 'admin.html' : 'dashboard.html');
