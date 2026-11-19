// Owl outfits: optional accessories for the owl logo and the owl buddy.
// Everyday items use theme-color classes from outfits.css; holiday items and the grad cap keep fixed colors.
// The plain owl stays a CSS mask; a dressed owl is drawn as inline SVG so accessories can extend past it.
(() => {
  'use strict';
  const KEY = 'outreach-owl-outfit';
  const OWL_SELECTOR = '.owl-mark, .owl-body';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const VIEWBOX = '-90 -290 920 1330';
  const store = {
    get() { try { return localStorage.getItem(KEY); } catch { return null; } },
    set(value) { try { localStorage.setItem(KEY, value); } catch {} }
  };

  const RED = '#d7263d', RED_DARK = '#a3162b', WHITE = '#fffaf2', BROWN = '#8a5a35', GOLD = '#f2c94c';
  const antler = '<path d="M450 200 C460 90 480 -10 520 -110 M490 20 C540 0 590 -20 640 -80 M512 -50 C490 -100 478 -150 482 -200 M520 -110 C555 -150 580 -195 585 -245 M600 -55 C630 -60 655 -80 675 -110" fill="none" stroke="' + BROWN + '" stroke-width="40" stroke-linecap="round" stroke-linejoin="round"/>';
  const scarf = (base, stripe, fringe) => `
    <path class="${base}" d="M105 490 C230 560 500 560 625 485 L640 575 C500 660 230 660 95 580 Z"/>
    <path class="${stripe}" d="M190 540 L175 625 M290 560 L280 645 M390 566 L392 650 M495 552 L505 635" fill="none" stroke-width="22"/>
    <path class="${base}" d="M515 575 C540 660 548 750 530 840 L615 846 C632 750 625 660 600 565 Z"/>
    <path class="${stripe}" d="M526 665 L618 662 M530 755 L622 752" fill="none" stroke-width="22"/>
    <path class="${fringe}" d="M535 846 L527 890 M556 848 L552 894 M578 849 L578 895 M600 850 L604 894" fill="none" stroke-width="12" stroke-linecap="round"/>`;

  // Each outfit: label, Chinese label, group, whether it follows the theme, and SVG drawn behind / in front of the owl.
  const OUTFITS = {
    classic: { label: 'Classic', group: 'everyday', theme: true, back: '', front: '' },
    headphones: {
      label: 'Headphones', group: 'everyday', theme: true,
      back: '<path class="os-mid" d="M55 380 C30 130 190 -50 365 -50 C540 -50 700 130 675 380" fill="none" stroke-width="40" stroke-linecap="round"/>',
      front: `<rect class="oc-mid" x="-20" y="275" width="125" height="200" rx="58"/><rect class="oc-light" x="40" y="300" width="58" height="150" rx="29"/>
        <rect class="oc-mid" x="625" y="275" width="125" height="200" rx="58"/><rect class="oc-light" x="632" y="300" width="58" height="150" rx="29"/>
        <path d="M5 330 C5 305 20 292 40 290" fill="none" stroke="#fff" stroke-width="12" stroke-linecap="round" opacity=".6"/>`
    },
    beret: {
      label: 'Beret', group: 'everyday', theme: true, back: '',
      front: `<path class="oc-mid" d="M140 118 C128 52 245 8 365 8 C485 8 602 52 590 118 C584 152 482 168 365 168 C248 168 146 152 140 118 Z"/>
        <path class="oc-acc" d="M175 140 C250 166 480 166 555 140 L552 158 C480 184 250 184 178 158 Z" opacity=".6"/>
        <path class="os-light" d="M210 70 C255 40 310 28 365 26" fill="none" stroke-width="16" stroke-linecap="round"/>
        <path class="os-acc" d="M365 10 C365 -12 371 -26 382 -34" fill="none" stroke-width="16" stroke-linecap="round"/><circle class="oc-acc" cx="386" cy="-38" r="14"/>`
    },
    bowtie: {
      label: 'Bow tie', group: 'everyday', theme: true, back: '',
      front: `<g transform="translate(365 565) scale(1.35) translate(-365 -565)">
        <path class="oc-mid" d="M365 560 L250 500 C222 486 205 500 205 532 L205 598 C205 630 222 644 250 630 Z"/>
        <path class="oc-mid" d="M365 560 L480 500 C508 486 525 500 525 532 L525 598 C525 630 508 644 480 630 Z"/>
        <path class="os-light" d="M240 520 L300 548 M240 610 L300 578 M490 520 L430 548 M490 610 L430 578" fill="none" stroke-width="10" stroke-linecap="round"/>
        <rect class="oc-acc" x="333" y="528" width="64" height="66" rx="20"/></g>`
    },
    scarf: { label: 'Striped scarf', group: 'everyday', theme: true, back: '', front: scarf('oc-mid', 'os-light', 'os-acc') },
    gradcap: {
      label: 'Grad cap', group: 'everyday', theme: false, back: '',
      front: `<path d="M200 125 L212 40 C300 12 430 12 518 40 L530 125 C430 104 300 104 200 125 Z" fill="#2f3340"/>
        <path d="M365 -110 L700 0 L365 110 L30 0 Z" fill="#3d4250"/><path d="M365 -110 L700 0 L365 20 Z" fill="#4a5060"/>
        <path d="M365 0 C520 30 600 60 640 110 L640 230" fill="none" stroke="${GOLD}" stroke-width="14" stroke-linecap="round"/>
        <path d="M618 222 L662 222 L676 305 L604 305 Z" fill="${GOLD}"/><circle cx="365" cy="0" r="20" fill="${GOLD}"/>`
    },
    reindeer: {
      label: 'Reindeer', group: 'holiday', theme: false,
      back: `<g>${antler}</g><g transform="translate(730 0) scale(-1 1)">${antler}</g><circle cx="365" cy="455" r="88" fill="${RED}" opacity=".16"/>`,
      front: `<circle cx="365" cy="455" r="56" fill="${RED}"/><circle cx="346" cy="436" r="16" fill="#fff" opacity=".85"/>`
    },
    'holiday-scarf': {
      label: 'Christmas scarf', group: 'holiday', theme: false, back: '',
      front: `<path fill="${RED}" d="M105 490 C230 560 500 560 625 485 L640 575 C500 660 230 660 95 580 Z"/>
        <path stroke="${WHITE}" d="M190 540 L175 625 M290 560 L280 645 M390 566 L392 650 M495 552 L505 635" fill="none" stroke-width="22"/>
        <path fill="${RED}" d="M515 575 C540 660 548 750 530 840 L615 846 C632 750 625 660 600 565 Z"/>
        <path stroke="${WHITE}" d="M526 665 L618 662 M530 755 L622 752" fill="none" stroke-width="22"/>
        <path stroke="${RED_DARK}" d="M535 846 L527 890 M556 848 L552 894 M578 849 L578 895 M600 850 L604 894" fill="none" stroke-width="12" stroke-linecap="round"/>`
    }
  };

  let owlPath = '';
  let outerPath = '';
  const owlReady = fetch('/owl.svg').then(r => r.text()).then(text => {
    owlPath = (text.match(/ d="([^"]+)"/) || [])[1] || '';
    outerPath = owlPath ? 'M' + owlPath.split('M')[1] : '';
  }).catch(() => {});

  const current = () => (OUTFITS[store.get()] ? store.get() : 'classic');

  function drawOwl(el, id) {
    el.querySelector(':scope > svg.owl-art')?.remove();
    const outfit = OUTFITS[id] || OUTFITS.classic;
    el.dataset.outfit = id;
    if (id === 'classic' || !owlPath) { el.classList.remove('owl-dressed'); return; }
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', VIEWBOX);
    svg.setAttribute('class', 'owl-art');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.innerHTML = outfit.back
      + `<path class="oc-fill" d="${outerPath}"/>`
      + `<path class="oc-owl" fill-rule="evenodd" d="${owlPath}"/>`
      + outfit.front;
    el.classList.add('owl-dressed');
    el.prepend(svg);
  }

  function dressAll(root = document) {
    const id = current();
    const owls = root.matches?.(OWL_SELECTOR) ? [root] : [...root.querySelectorAll(OWL_SELECTOR)];
    for (const el of owls) {
      if (el.dataset.outfitPreview) continue;  // previews in Settings always show their own outfit
      if (el.dataset.outfit !== id || (id !== 'classic' && !el.querySelector(':scope > svg.owl-art'))) drawOwl(el, id);
    }
  }

  function setOutfit(id) {
    if (!OUTFITS[id]) id = 'classic';
    store.set(id);
    for (const option of document.querySelectorAll('[data-outfit-choice]')) {
      option.setAttribute('aria-checked', String(option.dataset.outfitChoice === id));
    }
    dressAll();
  }

  // Settings: an "Owl outfit" card under the theme color picker.
  function buildSettings() {
    const host = document.getElementById('appearance-settings');
    if (!host || document.getElementById('owl-outfit-settings')) return;
    const card = document.createElement('div');
    card.id = 'owl-outfit-settings';
    card.className = 'outfit-settings';
    const title = document.createElement('h3'); title.textContent = 'Owl outfit';
    const hint = document.createElement('p'); hint.className = 'hint';
    hint.textContent = 'Dress up the owl logo and the owl hints. Headphones, beret, bow tie and scarf follow your theme color; the grad cap and holiday outfits keep their own colors.';
    card.append(title, hint);
    for (const [group, heading] of [['everyday', 'Everyday'], ['holiday', 'Holiday']]) {
      const label = document.createElement('p'); label.className = 'outfit-group'; label.textContent = heading;
      const grid = document.createElement('div'); grid.className = 'outfit-grid';
      grid.setAttribute('role', 'radiogroup'); grid.setAttribute('aria-label', heading + ' owl outfits');
      for (const [id, outfit] of Object.entries(OUTFITS)) {
        if (outfit.group !== group) continue;
        const option = document.createElement('button');
        option.type = 'button'; option.className = 'outfit-option'; option.setAttribute('role', 'radio');
        option.dataset.outfitChoice = id;
        const owl = document.createElement('span'); owl.className = 'owl-mark outfit-preview'; owl.setAttribute('aria-hidden', 'true');
        owl.dataset.outfitPreview = id;
        const name = document.createElement('strong'); name.textContent = outfit.label;
        const note = document.createElement('span'); note.className = 'outfit-note';
        note.textContent = outfit.theme ? 'Theme color' : 'Fixed colors';
        option.append(owl, name, note);
        option.addEventListener('click', () => setOutfit(id));
        grid.append(option);
      }
      card.append(label, grid);
    }
    const actions = host.querySelector(':scope > .actions');
    host.insertBefore(card, actions || null);
    owlReady.then(() => { for (const el of card.querySelectorAll('[data-outfit-preview]')) drawOwl(el, el.dataset.outfitPreview); });
  }

  buildSettings();
  setOutfit(current());
  owlReady.then(() => dressAll());

  // Owls added later (owl buddy, send celebration, tutorial) get the outfit too.
  new MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) {
      if (node.nodeType === 1 && (node.matches(OWL_SELECTOR) || node.querySelector(OWL_SELECTOR))) dressAll(node);
    }
  }).observe(document.body, { childList: true, subtree: true });

  window.OutreachOutfits = { list: () => Object.keys(OUTFITS), current, set: setOutfit };
})();
