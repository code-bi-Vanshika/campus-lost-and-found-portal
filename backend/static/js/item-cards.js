// Item card rendering + lazy thumbnails (the list API has no image info, so we fetch the first image id on demand).
import { api } from './api.js';
import { icon } from './icons.js';
import { esc, fmtDate, itemStatusBadge, typeTag, $$ } from './ui.js';

export function itemCard(it) {
  const dim = ['RETURNED', 'CLOSED'].includes(it.status) ? ' dim' : '';
  return `<a class="item-card${dim}" href="item.html?id=${it.item_id}">
    <div class="thumb" data-thumb="${it.item_id}">${typeTag(it.item_type)}<span data-ph>${icon('image', 36)}</span></div>
    <div class="item-body">
      <div class="row between">${itemStatusBadge(it.status)}<span class="muted small">${esc(fmtDate(it.item_date))}</span></div>
      <h3>${esc(it.title)}</h3>
      <p class="clamp">${esc(it.description)}</p>
      <div class="item-meta"><span>${icon('tag', 14)} ${esc(it.category.category_name)}</span><span>${icon('pin', 14)} ${esc(it.location.location_name)}</span></div>
    </div></a>`;
}

export function hydrateThumbs(root = document) {
  const load = async (el) => {
    try {
      const item = await api.itemCached(Number(el.dataset.thumb));
      if (!item.images.length) return;
      const img = new Image();
      img.alt = ''; img.src = item.images[0].url;
      img.onload = () => { const ph = el.querySelector('[data-ph]'); if (ph) ph.remove(); el.prepend(img); };
    } catch (e) { /* keep placeholder */ }
  };
  const targets = $$('[data-thumb]', root);
  if (!('IntersectionObserver' in window)) { targets.forEach(load); return; }
  const io = new IntersectionObserver((entries) => entries.forEach((en) => { if (en.isIntersecting) { io.unobserve(en.target); load(en.target); } }), { rootMargin: '200px' });
  targets.forEach((t) => io.observe(t));
}
