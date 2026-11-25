import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { icon } from '../icons.js';
import { renderClaimCard, loadFinderClaims, claimStage, attachHandovers } from '../claims-ui.js';
import { $, esc, fmtDateTime, showError, itemStatusBadge, typeTag } from '../ui.js';

const user = await initLayout({ active: 'dashboard', requireAuth: true, roles: ['STUDENT', 'STAFF'] });
$('#hello').textContent = 'Hello, ' + user.name.split(' ')[0];

async function load() {
  const [claimsR, finderR, notifR] = await Promise.allSettled([api.myClaims(), loadFinderClaims('pending'), api.notifications({ per_page: 5 })]);
  const claims = claimsR.status === 'fulfilled' ? claimsR.value.claims : null;
  const finder = finderR.status === 'fulfilled' ? finderR.value : null;
  const notif = notifR.status === 'fulfilled' ? notifR.value : null;

  const stages = claims ? claims.map((c) => claimStage(c).key) : [];
  const toReview = finder || [];
  $('#stats').innerHTML = [
    ['My claims', claims ? claims.length : '-', ''],
    ['In progress', claims ? stages.filter((s) => s.startsWith('awaiting')).length : '-', ''],
    ['Awaiting my review', finder ? toReview.length : '-', toReview.length ? 'hot' : ''],
    ['Unread notifications', notif ? notif.unread_count : '-', notif && notif.unread_count ? 'hot' : '']
  ].map(([l, n, cls]) => `<div class="stat ${cls}"><b>${n}</b><span>${l}</span></div>`).join('');

  // Needs my review (as finder)
  const rv = $('#review-box');
  if (!finder) showError(rv, finderR.reason);
  else if (!toReview.length) rv.innerHTML = '<p class="muted" style="margin:0">Nothing waiting. When someone claims an item you found, it will show up here.</p>';
  else { rv.innerHTML = ''; toReview.slice(0, 3).forEach((c) => rv.appendChild(renderClaimCard(c, { me: user, item: c._item, showItem: true, link: true, onChange: load }))); }

  // My claims
  const mc = $('#claims-box');
  if (!claims) showError(mc, claimsR.reason);
  else if (!claims.length) mc.innerHTML = '<p class="muted" style="margin:0">You have not claimed any item yet. <a href="items.html?item_type=FOUND">Browse found items</a>.</p>';
  else {
    const latest = claims.slice(0, 4);
    await Promise.allSettled(latest.map(async (c) => { try { c._item = await api.itemCached(c.item_id); } catch (e) { /* ignore */ } }));
    await attachHandovers(latest).catch(() => {});
    mc.innerHTML = '<ul class="list">' + latest.map((c) => { const s = claimStage(c, c._handover); return `<li><div><a href="claim.html?id=${c.claim_id}"><strong>${esc(c._item ? c._item.title : 'Item #' + c.item_id)}</strong></a><div class="muted small">${esc(fmtDateTime(c.claim_date))}</div></div><span class="badge ${s.tone}">${esc(s.label)}</span></li>`; }).join('') + '</ul>';
  }

  // Notifications
  const nb = $('#notif-box');
  if (!notif) showError(nb, notifR.reason);
  else nb.innerHTML = notif.notifications.length
    ? '<ul class="list">' + notif.notifications.map((n) => `<li><div>${n.is_read ? '' : '<span class="badge b-pending">New</span> '}${n.claim_id ? `<a href="claim.html?id=${n.claim_id}">${esc(n.message)}</a>` : esc(n.message)}<div class="muted small">${esc(fmtDateTime(n.created_at))}</div></div></li>`).join('') + '</ul>'
    : '<p class="muted" style="margin:0">No notifications yet.</p>';
}

async function loadReports() {
  const box = $('#reports-box');
  try {
    const d = await api.myItems({ per_page: 5 });
    box.innerHTML = d.items.length
      ? '<ul class="list">' + d.items.map((it) => `<li><div><a href="item.html?id=${it.item_id}"><strong>${esc(it.title)}</strong></a><div class="row" style="gap:8px;margin-top:4px">${typeTag(it.item_type)}${itemStatusBadge(it.status)}${it.claims_awaiting_review ? `<span class="badge b-pending">${it.claims_awaiting_review} to review</span>` : ''}</div></div></li>`).join('') + '</ul>'
      : '<p class="muted" style="margin:0">You have not reported anything yet. <a href="report.html">Report an item</a>.</p>';
  } catch (e) { showError(box, e, loadReports); }
}

load(); loadReports();
