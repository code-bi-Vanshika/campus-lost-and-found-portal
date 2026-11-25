// Renders the shared header/footer, enforces page access and shows the unread badge.
import { api } from './api.js';
import { getUser, setUser, homeFor } from './auth.js';
import { icon } from './icons.js';
import { esc, toast, $, $$ } from './ui.js';

function navLinks(user) {
  const links = [['items', 'items.html', 'Browse items'], ['lost', 'items.html?item_type=LOST', 'Lost'], ['found', 'items.html?item_type=FOUND', 'Found']];
  if (user && user.role === 'ADMIN') links.push(['admin', 'admin.html', 'Admin dashboard']);
  else if (user) links.push(['dashboard', 'dashboard.html', 'Dashboard'], ['reports', 'reports.html', 'My reports'], ['claims', 'claims.html', 'My claims'], ['review', 'review.html', 'Review claims']);
  return links;
}

window.addEventListener('pageshow', (e) => { if (e.persisted) location.reload(); });

export async function initLayout({ active = '', requireAuth = false, roles = null } = {}) {
  let user = null;
  try { user = await getUser(); } catch (e) { /* server unreachable: render logged-out shell */ }

  if (requireAuth && !user) { location.replace('login.html?next=' + encodeURIComponent(location.pathname.split('/').pop() + location.search)); return new Promise(() => {}); }
  if (roles && user && !roles.includes(user.role)) { location.replace(homeFor(user)); return new Promise(() => {}); }

  const canReport = user && user.role !== 'ADMIN';
  const links = navLinks(user).map(([k, href, label]) => `<a href="${href}" ${k === active ? 'aria-current="page"' : ''}>${label}</a>`).join('');
  const right = user
    ? `${canReport ? `<a class="btn btn-amber btn-sm" href="report.html">${icon('plus', 16)} Report an item</a>` : ''}
       <a class="bell" href="notifications.html" aria-label="Notifications"${active === 'notifications' ? ' aria-current="page"' : ''}>${icon('bell', 20)}<span class="count hidden" id="bell-count">0</span></a>
       <span class="user-chip" title="${esc(user.email)}">${esc(user.name)}</span>
       <button class="btn btn-ghost btn-sm" id="logout-btn" type="button" style="color:#fff">Log out</button>`
    : `<a class="btn btn-ghost btn-sm" href="login.html" style="color:#fff">Log in</a><a class="btn btn-amber btn-sm" href="register.html">Create account</a>`;

  $('#site-header').outerHTML = `<header class="site-header" id="site-header"><div class="container">
    <a class="brand" href="index.html"><span class="brand-mark">${icon('tag', 18)}</span>Campus Lost &amp; Found</a>
    <button class="menu-btn" id="menu-btn" type="button" aria-label="Open menu" aria-expanded="false">${icon('menu', 22)}</button>
    <nav class="nav" aria-label="Main">${links}</nav><div class="nav-right">${right}</div></div></header>`;
  $('#site-footer').outerHTML = `<footer class="site-footer"><div class="container row between">
    <span>Campus Lost &amp; Found Portal &middot; MCA DBMS project</span>
    <span>Ownership evidence stays private: only the claimant, the finder and administrators can see it.</span></div></footer>`;

  const header = $('#site-header');
  $('#menu-btn').addEventListener('click', (e) => { const o = header.classList.toggle('open'); e.currentTarget.setAttribute('aria-expanded', o); });
  const out = $('#logout-btn');
  if (out) out.addEventListener('click', async () => {
    out.disabled = true;
    try { await api.logout(); } catch (e) { /* session may already be gone */ }
    setUser(null); location.href = 'index.html';
  });
  if (user) refreshBell();
  return user;
}

export async function refreshBell() {
  try {
    const d = await api.notifications({ per_page: 1 });
    const b = $('#bell-count'); if (!b) return;
    b.textContent = d.unread_count > 99 ? '99+' : d.unread_count;
    b.classList.toggle('hidden', !d.unread_count);
  } catch (e) { /* bell is optional */ }
}
