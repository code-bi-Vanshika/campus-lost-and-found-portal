// Thin wrapper around the Flask JSON API: session cookie + X-CSRF-Token handling.
export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

let csrfToken = null;

let csrfInFlight = null;
// One shared fetch: parallel requests must not each rotate the server-side token.
function fetchCsrf() {
  if (!csrfInFlight) {
    csrfInFlight = (async () => {
      const res = await fetch('/api/auth/csrf', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data || !data.csrf_token) throw new ApiError('Could not start a secure session. Please reload the page.', res.status, data);
      csrfToken = data.csrf_token;
      return csrfToken;
    })().finally(() => { csrfInFlight = null; });
  }
  return csrfInFlight;
}

function toQuery(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v); });
  const s = q.toString();
  return s ? '?' + s : '';
}

async function request(method, path, { json, form, query, retry = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken || await fetchCsrf();
  let body;
  if (json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(json); }
  else if (form) body = form; // browser sets the multipart boundary itself

  let res;
  try {
    res = await fetch(path + toQuery(query), { method, headers, body, credentials: 'same-origin' });
  } catch (e) {
    throw new ApiError('Cannot reach the server. Check your connection and try again.', 0, null);
  }
  const data = await res.json().catch(() => null);
  if (res.status === 403 && method !== 'GET' && retry && data && /csrf/i.test(data.error || '')) {
    csrfToken = null; // token went stale (e.g. another tab) - fetch a new one and retry once
    return request(method, path, { json, form, query, retry: false });
  }
  if (!res.ok) throw new ApiError((data && data.error) || `Request failed (${res.status}).`, res.status, data);
  return data;
}

const get = (p, query) => request('GET', p, { query });
const post = (p, json) => request('POST', p, { json: json === undefined ? {} : json });

const itemCache = new Map();

export const api = {
  // auth
  me: () => get('/api/auth/me'),
  register: (body) => post('/api/auth/register', body),
  async login(email, password) {
    if (!csrfToken) await fetchCsrf();
    const data = await post('/api/auth/login', { email, password });
    csrfToken = data.csrf_token; // login rotates the token
    return data;
  },
  async logout() { try { await post('/api/auth/logout'); } finally { csrfToken = null; } },
  // items
  meta: () => get('/api/items/meta'),
  items: (query) => get('/api/items', query),
  item: (id) => get(`/api/items/${id}`),
  itemCached(id) {
    if (!itemCache.has(id)) {
      itemCache.set(id, get(`/api/items/${id}`).then((d) => d.item).catch((e) => { itemCache.delete(id); throw e; }));
    }
    return itemCache.get(id);
  },
  clearItemCache: () => itemCache.clear(),
  createItem: (form) => request('POST', '/api/items', { form }),
  editItem: (id, body) => request('PATCH', `/api/items/${id}`, { json: body }),
  closeItem: (id) => post(`/api/items/${id}/close`),
  myItems: (query) => get('/api/items/mine', query),
  // claims
  submitClaim: (itemId, evidence) => post(`/api/claims/items/${itemId}`, { ownership_evidence: evidence }),
  myClaims: () => get('/api/claims/mine'),
  itemClaims: (itemId) => get(`/api/claims/items/${itemId}`),
  reviewQueue: () => get('/api/claims/review-queue'),
  finderQueue: (query) => get('/api/claims/finder-queue', query),
  handoverQueue: (query) => get('/api/claims/handover-queue', query),
  claim: (id) => get(`/api/claims/${id}`),
  finderDecision: (id, decision, remarks) => post(`/api/claims/${id}/finder-decision`, { decision, remarks: remarks || null }),
  adminDecision: (id, decision, remarks) => post(`/api/claims/${id}/admin-decision`, { decision, remarks: remarks || null }),
  cancelApproval: (id, reason) => post(`/api/claims/${id}/cancel-approval`, { reason }),
  recordHandover: (id, remarks) => post(`/api/claims/${id}/handover`, { remarks: remarks || null }),
  handover: (id) => get(`/api/claims/${id}/handover`),
  // notifications + admin
  notifications: (query) => get('/api/notifications', query),
  markRead: (id) => post(`/api/notifications/${id}/read`),
  dashboard: () => get('/api/admin/dashboard')
};
