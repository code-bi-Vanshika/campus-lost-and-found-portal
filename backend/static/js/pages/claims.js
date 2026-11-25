import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { renderClaimCard, claimStage, attachHandovers, mapLimit } from '../claims-ui.js';
import { $, $$, esc, skeletons, emptyState, showError } from '../ui.js';

const user = await initLayout({ active: 'claims', requireAuth: true, roles: ['STUDENT', 'STAFF'] });
let claims = [], tab = 'all';
const TABS = [['all', 'All'], ['progress', 'In progress'], ['approved', 'Approved'], ['returned', 'Returned'], ['rejected', 'Rejected']];
const inTab = (c, t) => { const k = claimStage(c, c._handover).key; return t === 'all' || (t === 'progress' && k.startsWith('awaiting')) || t === k; };

function render() {
  $('#tabs').innerHTML = TABS.map(([k, l]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}<span class="n">${claims.filter((c) => inTab(c, k)).length}</span></button>`).join('');
  $$('#tabs button').forEach((b) => b.addEventListener('click', () => { tab = b.dataset.tab; render(); }));
  const list = $('#list'); list.innerHTML = '';
  const shown = claims.filter((c) => inTab(c, tab));
  if (!shown.length) { list.innerHTML = emptyState(claims.length ? 'No claims in this view' : 'You have not submitted any claims', claims.length ? 'Pick another tab to see the rest.' : 'Found something that looks like yours? Browse the found items and submit a claim.', claims.length ? '' : '<a class="btn btn-primary" href="items.html?item_type=FOUND">Browse found items</a>'); return; }
  shown.forEach((c) => list.appendChild(renderClaimCard(c, { me: user, item: c._item, handover: c._handover, showItem: true, link: true, onChange: load })));
}

async function load() {
  $('#list').innerHTML = skeletons(3, 180);
  try {
    claims = (await api.myClaims()).claims;
    await mapLimit(claims, 6, async (c) => { try { c._item = await api.itemCached(c.item_id); } catch (e) { /* keep id-only title */ } });
    await attachHandovers(claims);
    render();
  } catch (e) { showError($('#list'), e, load); }
}
load();
