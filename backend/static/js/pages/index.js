import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { itemCard, hydrateThumbs } from '../item-cards.js';
import { $, showError, skeletons, emptyState } from '../ui.js';

const user = await initLayout();
if (user) { const r = $('#cta-register'); if (r) r.remove(); }

const box = $('#recent');
async function load() {
  box.innerHTML = skeletons(6);
  try {
    const d = await api.items({ per_page: 6 });
    box.innerHTML = d.items.length ? d.items.map(itemCard).join('') : emptyState('No reports yet', 'Be the first to report a lost or found item.');
    hydrateThumbs(box);
  } catch (e) { box.classList.remove('items-grid'); showError(box, e, load); }
}
load();
