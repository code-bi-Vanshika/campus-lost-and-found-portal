// Shared UI helpers: escaping, formatting, badges, toasts, dialogs, small utilities.
import { icon } from './icons.js';

export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}
export function fmtDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}
export const todayISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
export const debounce = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const param = (name) => new URLSearchParams(location.search).get(name);

// Only allow redirects to pages inside this site (prevents open redirects).
export function safeNext(next, fallback) {
  return next && /^[A-Za-z0-9_\-./?=&%]+$/.test(next) && !next.startsWith('/') && !next.includes('..') && !next.includes('//') ? next : fallback;
}

// ---- Status badges ----
const ITEM_STATUS = {
  ACTIVE: ['Open', 'b-active'], CLAIM_PENDING: ['Claim under review', 'b-pending'],
  CLAIMED: ['Claim approved', 'b-info'], RETURNED: ['Returned to owner', 'b-done'], CLOSED: ['Closed', 'b-grey']
};
export const itemStatusLabel = (s) => (ITEM_STATUS[s] || [s])[0];
export const itemStatusBadge = (s) => `<span class="badge ${(ITEM_STATUS[s] || [0, 'b-grey'])[1]}">${esc(itemStatusLabel(s))}</span>`;
export const typeTag = (t) => `<span class="tag ${t === 'LOST' ? 'tag-lost' : 'tag-found'}">${t === 'LOST' ? 'Lost' : 'Found'}</span>`;
export const stageBadge = (stage) => `<span class="badge ${stage.tone}">${esc(stage.label)}</span>`;

// ---- Toasts ----
export function toast(message, type = 'info') {
  let box = $('.toasts');
  if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
  const t = document.createElement('div');
  t.className = `toast ${type}`; t.setAttribute('role', type === 'error' ? 'alert' : 'status'); t.textContent = message;
  box.appendChild(t);
  setTimeout(() => t.remove(), type === 'error' ? 7000 : 4000);
}

// ---- Loading / error / empty states ----
export const skeletons = (n = 6, h = 220) => Array.from({ length: n }, () => `<div class="skel" style="min-height:${h}px"></div>`).join('');
export function showError(el, err, retry) {
  if (err && err.status === 401) { location.href = 'login.html?next=' + encodeURIComponent(location.pathname.split('/').pop() + location.search); return; }
  el.innerHTML = `<div class="alert alert-error" role="alert">${icon('alert')}<div><strong>Something went wrong.</strong><br>${esc((err && err.message) || 'Unexpected error.')}${retry ? '<br><button class="btn btn-secondary btn-sm" type="button" data-retry style="margin-top:8px">Try again</button>' : ''}</div></div>`;
  if (retry) $('[data-retry]', el).addEventListener('click', retry);
}
export const emptyState = (title, text, actionHtml = '') => `<div class="empty"><h3>${esc(title)}</h3><p>${esc(text)}</p>${actionHtml}</div>`;
export function inlineError(el, msg) { el.innerHTML = msg ? `<div class="alert alert-error" role="alert">${icon('alert')}<div>${esc(msg)}</div></div>` : ''; }

// Disable a button and show a spinner while an async action runs.
export async function busy(btn, fn) {
  if (btn.disabled) return;
  btn.disabled = true; btn.classList.add('busy');
  try { return await fn(); } finally { btn.disabled = false; btn.classList.remove('busy'); }
}

// ---- Dialogs ----
function openDialog(html) {
  return new Promise((resolve) => {
    const dlg = document.createElement('dialog');
    dlg.innerHTML = html;
    document.body.appendChild(dlg);
    const done = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    dlg.addEventListener('cancel', (e) => { e.preventDefault(); done(null); });
    dlg.addEventListener('click', (e) => { if (e.target === dlg) done(null); });
    dlg.showModal();
    dlg._done = done;
    $('[data-cancel]', dlg).addEventListener('click', () => done(null));
    const form = $('form', dlg);
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const ta = $('textarea', dlg);
      if (ta && ta.required && !ta.value.trim()) { ta.classList.add('invalid'); ta.focus(); return; }
      done(ta ? ta.value.trim() : true);
    });
    const first = $('textarea', dlg) || $('[type=submit]', dlg);
    first && first.focus();
  });
}
// Resolves to the entered text ('' allowed when optional), or null if cancelled.
export const askText = ({ title, label, required = false, confirmText = 'Confirm', danger = false, help = '' }) => openDialog(
  `<form method="dialog"><h3>${esc(title)}</h3>${help ? `<p class="muted small">${esc(help)}</p>` : ''}
   <label class="label" for="dlg-text">${esc(label)}${required ? '' : ' (optional)'}</label>
   <textarea id="dlg-text" class="input" maxlength="2000" ${required ? 'required' : ''}></textarea>
   <div class="dialog-actions"><button type="button" class="btn btn-secondary" data-cancel>Cancel</button>
   <button type="submit" class="btn ${danger ? 'btn-danger' : 'btn-primary'}">${esc(confirmText)}</button></div></form>`);
export const confirmBox = ({ title, text, confirmText = 'Confirm', danger = false }) => openDialog(
  `<form method="dialog"><h3>${esc(title)}</h3><p>${esc(text)}</p>
   <div class="dialog-actions"><button type="button" class="btn btn-secondary" data-cancel>Cancel</button>
   <button type="submit" class="btn ${danger ? 'btn-danger' : 'btn-primary'}">${esc(confirmText)}</button></div></form>`);
