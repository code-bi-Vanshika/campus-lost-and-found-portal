import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { renderClaimCard, loadAwaitingHandover, loadCompletedHandovers } from '../claims-ui.js';
import { $, $$, esc, fmtDate, itemStatusBadge, typeTag, debounce, skeletons, emptyState, showError } from '../ui.js';

const user = await initLayout({ active: 'admin', requireAuth: true, roles: ['ADMIN'] });
let tab = 'decisions', queue = [], handovers = [], completed = [], hview = 'pending';
const lst = { q: '', item_type: '', status: '', page: 1 }, PER = 20;

async function loadStats() {
  try {
    const d = await api.dashboard(), i = d.items_by_status || {}, c = d.claims_by_status || {};
    const tiles = [
      ['Awaiting your decision', d.claims_awaiting_admin, d.claims_awaiting_admin ? 'hot' : ''],
      ['Awaiting finder review', d.claims_awaiting_finder, ''],
      ['Awaiting handover', i.CLAIMED || 0, i.CLAIMED ? 'hot' : ''],
      ['Open reports', (i.ACTIVE || 0) + (i.CLAIM_PENDING || 0), ''],
      ['Items returned', i.RETURNED || 0, ''],
      ['Claims rejected', c.REJECTED || 0, '']
    ];
    $('#stats').innerHTML = tiles.map(([l, n, cls]) => `<div class="stat ${cls}"><b>${n}</b><span>${l}</span></div>`).join('');
  } catch (e) { showError($('#stats'), e, loadStats); }
}

function tabsHtml() {
  $('#tabs').innerHTML = [['decisions', 'Claims to decide', queue.length], ['handovers', 'Handovers', handovers.length], ['listings', 'All listings', null]]
    .map(([k, l, n]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}${n === null ? '' : `<span class="n">${n}</span>`}</button>`).join('');
  $$('#tabs button').forEach((b) => b.addEventListener('click', () => { tab = b.dataset.tab; tabsHtml(); renderPanel(); }));
}

const refresh = () => { loadStats(); loadWork(); };

function renderPanel() {
  const p = $('#panel'); p.innerHTML = '';
  if (tab === 'decisions') {
    if (!queue.length) { p.innerHTML = emptyState('No claims waiting', 'Claims appear here after the finder has approved them.'); return; }
    p.className = 'stack';
    queue.forEach((c) => p.appendChild(renderClaimCard(c, { me: user, item: { title: c.item_title, status: c.item_status }, showItem: true, link: true, onChange: refresh })));
  } else if (tab === 'handovers') {
    const bar = document.createElement('div'); bar.className = 'seg'; bar.style.marginBottom = '16px';
    bar.innerHTML = `<button type="button" data-v="pending" aria-pressed="${hview === 'pending'}">Awaiting handover (${handovers.length})</button><button type="button" data-v="completed" aria-pressed="${hview === 'completed'}">Completed (${completed.length})</button>`;
    bar.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { hview = b.dataset.v; renderPanel(); }));
    const list = document.createElement('div'); list.className = 'stack';
    p.append(bar, list);
    const rows = hview === 'pending' ? handovers : completed;
    if (!rows.length) { list.innerHTML = emptyState(hview === 'pending' ? 'No handovers pending' : 'No completed handovers', hview === 'pending' ? 'Approved claims waiting for the item to be handed over appear here.' : 'Items you hand over will be listed here.'); return; }
    rows.forEach(({ claim, item, handover }) => list.appendChild(renderClaimCard(claim, { me: user, item, handover: hview === 'pending' ? null : handover, showItem: true, link: true, onChange: refresh })));
  } else renderListings();
}

async function loadWork() {
  $('#panel').className = ''; if (tab !== 'listings') $('#panel').innerHTML = skeletons(2, 180);
  const [q, h, d] = await Promise.allSettled([api.reviewQueue(), loadAwaitingHandover(), loadCompletedHandovers()]);
  const bad = [q, h, d].find((r) => r.status === 'rejected');
  if (bad) { showError($('#panel'), bad.reason, loadWork); return; }
  queue = q.value.claims; handovers = h.value; completed = d.value;
  tabsHtml(); renderPanel();
}

async function renderListings() {
  const p = $('#panel'); p.className = '';
  p.innerHTML = `<div class="filters" style="margin-bottom:16px"><div class="field wide"><label for="aq">Search</label><input id="aq" class="input" type="search" placeholder="Title or description" value="${esc(lst.q)}"></div>
    <div class="field"><label for="at">Type</label><select id="at" class="input"><option value="">All</option><option value="LOST">Lost</option><option value="FOUND">Found</option></select></div>
    <div class="field"><label for="as">Status</label><select id="as" class="input"><option value="">Any</option><option value="ACTIVE">Open</option><option value="CLAIM_PENDING">Claim under review</option><option value="CLAIMED">Claim approved</option><option value="RETURNED">Returned</option><option value="CLOSED">Closed</option></select></div></div><div id="lt"></div>`;
  $('#at').value = lst.item_type; $('#as').value = lst.status;
  $('#aq').addEventListener('input', debounce((e) => { lst.q = e.target.value.trim(); lst.page = 1; fillTable(); }));
  $('#at').addEventListener('change', (e) => { lst.item_type = e.target.value; lst.page = 1; fillTable(); });
  $('#as').addEventListener('change', (e) => { lst.status = e.target.value; lst.page = 1; fillTable(); });
  fillTable();
}
async function fillTable() {
  const box = $('#lt'); box.innerHTML = skeletons(1, 200);
  try {
    const d = await api.items({ ...lst, per_page: PER });
    if (!d.items.length) { box.innerHTML = emptyState('No listings found', 'Try different filters.'); return; }
    box.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Item</th><th>Type</th><th>Category</th><th>Location</th><th>Date</th><th>Status</th></tr></thead><tbody>${d.items.map((it) => `<tr><td><a href="item.html?id=${it.item_id}">${esc(it.title)}</a></td><td>${typeTag(it.item_type)}</td><td>${esc(it.category.category_name)}</td><td>${esc(it.location.location_name)}</td><td>${esc(fmtDate(it.item_date))}</td><td>${itemStatusBadge(it.status)}</td></tr>`).join('')}</tbody></table></div>
      <div class="pager"><button class="btn btn-secondary btn-sm" id="pp" ${lst.page === 1 ? 'disabled' : ''}>Previous</button><span class="muted small">Page ${lst.page}</span><button class="btn btn-secondary btn-sm" id="pn" ${d.items.length < PER ? 'disabled' : ''}>Next</button></div>`;
    $('#pp').addEventListener('click', () => { lst.page--; fillTable(); });
    $('#pn').addEventListener('click', () => { lst.page++; fillTable(); });
  } catch (e) { showError(box, e, fillTable); }
}

loadStats(); loadWork();
