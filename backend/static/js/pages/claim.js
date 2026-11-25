import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { renderClaimCard, attachHandovers } from '../claims-ui.js';
import { $, esc, param, itemStatusBadge, typeTag, emptyState, showError, skeletons } from '../ui.js';

const user = await initLayout({ requireAuth: true });
const id = Number(param('id'));
const root = $('#claim-root');

async function load() {
  if (!id) { root.innerHTML = emptyState('Claim not found', 'The link is missing a claim number.'); return; }
  root.innerHTML = skeletons(1, 260);
  try {
    const { claim } = await api.claim(id);
    let item = null; try { item = await api.itemCached(claim.item_id); } catch (e) { /* show claim without item */ }
    await attachHandovers([claim]);
    const back = $('#back-link');
    if (user.role === 'ADMIN') { back.href = 'admin.html'; back.textContent = '\u2190 Back to admin dashboard'; }
    else if (user.user_id !== claim.claimant_id) { back.href = 'review.html'; back.textContent = '\u2190 Back to review claims'; }
    root.innerHTML = `${item ? `<div class="card flat row between" style="margin-bottom:18px"><div><div class="row" style="gap:8px">${typeTag(item.item_type)}${itemStatusBadge(item.status)}</div><h3 style="margin:8px 0 0"><a href="item.html?id=${item.item_id}">${esc(item.title)}</a></h3></div><a class="btn btn-secondary btn-sm" href="item.html?id=${item.item_id}">View item</a></div>` : ''}<div id="card"></div>`;
    $('#card').appendChild(renderClaimCard(claim, { me: user, item, handover: claim._handover, onChange: load }));
  } catch (e) {
    if (e.status === 404 || e.status === 403) root.innerHTML = emptyState(e.status === 404 ? 'Claim not found' : 'You cannot view this claim', e.message, '<a class="btn btn-primary" href="dashboard.html">Go to dashboard</a>');
    else showError(root, e, load);
  }
}
load();
