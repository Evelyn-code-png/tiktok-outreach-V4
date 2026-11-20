// Business and Customer page: switch between the cards with the tabs or the arrow buttons.
(() => {
  'use strict';
  const root = document.getElementById('business');
  if (!root) return;
  const pages = [...root.querySelectorAll('.r-card')];
  const tabs = [...root.querySelectorAll('.r-tab')];
  const prev = root.querySelector('.r-prev');
  const next = root.querySelector('.r-next');
  const count = root.querySelector('.r-count');
  let index = 0;

  function show(n) {
    index = Math.max(0, Math.min(pages.length - 1, n));
    pages.forEach((page, k) => { page.hidden = k !== index; });
    tabs.forEach((tab, k) => {
      tab.setAttribute('aria-selected', String(k === index));
      tab.tabIndex = k === index ? 0 : -1;
    });
    count.textContent = `${index + 1} / ${pages.length}`;
    prev.disabled = index === 0;
    next.disabled = index === pages.length - 1;
  }

  tabs.forEach((tab, k) => tab.addEventListener('click', () => show(k)));
  root.querySelector('.r-tabs').addEventListener('keydown', event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    show(index + (event.key === 'ArrowRight' ? 1 : -1));
    tabs[index].focus();
  });
  prev.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));
  show(0);
  window.OutreachBusiness = { show, current: () => index };
})();
