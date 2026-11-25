import { initLayout, refreshBell } from '../layout.js';
import { api } from '../api.js';
import { $, $$, esc, fmtDateTime, skeletons, emptyState, showError, toast, busy } from '../ui.js';

await initLayout({ active: 'notifications', requireAuth: true });
const PER = 20; let page = 1, data = null;

function render() {
  const list = $('#list');
  $('#mark-all').classList.toggle('hidden', !data.unread_count);
  if (!data.notifications.length) { list.innerHTML = emptyState(page > 1 ? 'No more notifications' : 'No notifications yet', 'You will be told here when a claim is submitted, reviewed or handed over.'); }
  else list.innerHTML = data.notifications.map((n) => `<button type="button" class="notif ${n.is_read ? 'read' : 'unread'}" data-id="${n.notification_id}" data-claim="${n.claim_id || ''}"><span class="dot"></span><span style="flex:1"><span style="display:block;font-weight:${n.is_read ? 400 : 600}">${esc(n.message)}</span><span class="muted small">${esc(fmtDateTime(n.created_at))}${n.claim_id ? ' &middot; View claim' : ''}</span></span></button>`).join('');
  $('#pager').innerHTML = page > 1 || data.notifications.length === PER ? `<button class="btn btn-secondary btn-sm" id="prev" ${page === 1 ? 'disabled' : ''}>Newer</button><span class="muted small">Page ${page}</span><button class="btn btn-secondary btn-sm" id="next" ${data.notifications.length < PER ? 'disabled' : ''}>Older</button>` : '';
  $('#prev') && $('#prev').addEventListener('click', () => { page--; load(); });
  $('#next') && $('#next').addEventListener('click', () => { page++; load(); });
  $$('.notif', list).forEach((el) => el.addEventListener('click', async () => {
    try { if (el.classList.contains('unread')) await api.markRead(Number(el.dataset.id)); } catch (e) { toast(e.message, 'error'); return; }
    if (el.dataset.claim) location.href = 'claim.html?id=' + el.dataset.claim;
    else { el.classList.replace('unread', 'read'); refreshBell(); }
  }));
}

async function load() {
  $('#list').innerHTML = skeletons(4, 70);
  try { data = await api.notifications({ page, per_page: PER }); render(); refreshBell(); }
  catch (e) { showError($('#list'), e, load); }
}
$('#mark-all').addEventListener('click', (e) => busy(e.currentTarget, async () => {
  const unread = data.notifications.filter((n) => !n.is_read);
  const res = await Promise.allSettled(unread.map((n) => api.markRead(n.notification_id)));
  if (res.some((r) => r.status === 'rejected')) toast('Some notifications could not be updated.', 'error'); else toast('All marked as read.', 'ok');
  load();
}));
load();
