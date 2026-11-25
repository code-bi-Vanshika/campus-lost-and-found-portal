import { initLayout } from '../layout.js';
import { renderClaimCard, loadFinderClaims, attachHandovers } from '../claims-ui.js';
import { $, $$, skeletons, emptyState, showError } from '../ui.js';

const user = await initLayout({ active: 'review', requireAuth: true, roles: ['STUDENT', 'STAFF'] });
let claims = [], tab = 'todo';
const todo = (c) => c.status === 'PENDING' && c.finder_decision === 'PENDING';

function render() {
  const t = claims.filter(todo), d = claims.filter((c) => !todo(c));
  $('#tabs').innerHTML = [['todo', 'Needs your review', t.length], ['done', 'Already reviewed', d.length]].map(([k, l, n]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}<span class="n">${n}</span></button>`).join('');
  $$('#tabs button').forEach((b) => b.addEventListener('click', () => { tab = b.dataset.tab; render(); }));
  const list = $('#list'); list.innerHTML = '';
  const shown = tab === 'todo' ? t : d;
  if (!shown.length) { list.innerHTML = emptyState(tab === 'todo' ? 'No claims waiting for you' : 'Nothing reviewed yet', tab === 'todo' ? 'When someone claims an item you found, you will be notified and the claim will appear here.' : 'Claims you approve or reject will be listed here.'); return; }
  shown.forEach((c) => list.appendChild(renderClaimCard(c, { me: user, item: c._item, handover: c._handover, showItem: true, link: true, onChange: load })));
}

async function load() {
  $('#list').innerHTML = skeletons(2, 200);
  try { claims = await loadFinderClaims('all'); await attachHandovers(claims); render(); }
  catch (e) { showError($('#list'), e, load); }
}
load();
