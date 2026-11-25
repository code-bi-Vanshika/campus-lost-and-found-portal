import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { itemCard, hydrateThumbs } from '../item-cards.js';
import { $, skeletons, emptyState, showError } from '../ui.js';

await initLayout({ active: 'reports', requireAuth: true, roles: ['STUDENT', 'STAFF'] });
const PER = 12;
let page = 1;

const claimLine = (it) => {
  if (it.item_type !== 'FOUND' || !it.claim_count) return '';
  const waiting = it.claims_awaiting_review;
  return `<a class="small" href="item.html?id=${it.item_id}">${it.claim_count} claim${it.claim_count === 1 ? '' : 's'}${waiting ? ` &middot; <span class="badge b-pending">${waiting} awaiting your review</span>` : ''}</a>`;
};

async function load() {
  const grid = $('#grid'), pager = $('#pager');
  grid.className = 'items-grid'; grid.innerHTML = skeletons(PER); pager.innerHTML = '';
  try {
    const d = await api.myItems({ page, per_page: PER });
    if (!d.items.length) {
      grid.className = '';
      grid.innerHTML = emptyState(page > 1 ? 'No more reports' : 'You have not reported anything yet', 'Lost something or found something on campus? Report it so it can be matched.', '<a class="btn btn-primary" href="report.html">Report an item</a>');
      return;
    }
    grid.innerHTML = d.items.map((it) => `<div class="stack" style="gap:8px">${itemCard(it)}${claimLine(it)}</div>`).join('');
    hydrateThumbs(grid);
    pager.innerHTML = page > 1 || d.items.length === PER
      ? `<button class="btn btn-secondary btn-sm" id="prev" ${page === 1 ? 'disabled' : ''}>Previous</button><span class="muted small">Page ${page}</span><button class="btn btn-secondary btn-sm" id="next" ${d.items.length < PER ? 'disabled' : ''}>Next</button>` : '';
    const go = (n) => { page = n; load(); window.scrollTo({ top: 0 }); };
    $('#prev') && $('#prev').addEventListener('click', () => go(page - 1));
    $('#next') && $('#next').addEventListener('click', () => go(page + 1));
  } catch (e) { grid.className = ''; showError(grid, e, load); }
}
load();
