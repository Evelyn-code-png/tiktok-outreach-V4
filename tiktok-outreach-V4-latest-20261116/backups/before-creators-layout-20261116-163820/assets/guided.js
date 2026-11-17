// Guided flow: theme colors, step progress, tips, brand cards, sample data and the tutorial.
// Works on top of app.js and engagement.js; it reuses their elements and API helpers.
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch {} }
  };

  // ---------- Theme color ----------
  const THEMES = ['forest', 'indigo', 'ocean', 'plum', 'coral', 'graphite'];
  function applyTheme(name) {
    const theme = THEMES.includes(name) ? name : 'forest';
    document.documentElement.dataset.theme = theme;
    for (const swatch of document.querySelectorAll('[data-theme-choice]')) {
      swatch.setAttribute('aria-checked', String(swatch.dataset.themeChoice === theme));
    }
    store.set('outreach-theme', theme);
  }
  for (const swatch of document.querySelectorAll('[data-theme-choice]')) {
    swatch.addEventListener('click', () => applyTheme(swatch.dataset.themeChoice));
  }
  applyTheme(store.get('outreach-theme'));

  // ---------- Step progress and tips ----------
  const STEP_OF = { brand: 1, discover: 2, contacts: 2, compose: 3, send: 4 };
  const TIPS = {
    brand: ['Start here.', 'Pick the brand you are promoting, or add a new one. Every match and email uses it.'],
    discover: ['Find creators.', 'Describe who you want and start a search, or switch to My lists and import to use your own list.'],
    contacts: ['Tick the creators you want.', 'Open a creator to see why they fit your brand. Check anyone flagged for review, then click Continue with selected.'],
    compose: ['Keep it short.', '$name is filled in for each creator. Edit the wording, then click Next: Preview emails. Nothing is sent yet.'],
    send: ['Last check.', 'Read each email. Tick the confirmation box only when every email looks right, then send.']
  };
  const currentPage = () => {
    const hash = location.hash.slice(1);
    if (Object.hasOwn(STEP_OF, hash) || hash === 'history' || hash === 'settings') return hash;
    return 'brand';
  };
  const tipsOn = () => store.get('outreach-tips') !== 'off';

  // ---------- Owl buddy and progress cheer ----------
  const BUDDY = {
    brand: [['Hoot! Let’s start with the ', 'brand'], [' you’re promoting. Pick one below or add a new one.']],
    discover: [['Great pick! Now find the ', 'creators'], [' who feel like a good fit for your brand.']],
    contacts: [['Great pick! Now tick the ', 'creators'], [' who feel like a good fit. I’ll check their emails for you.']],
    compose: [['Almost there! Make the ', 'email'], [' sound like you. $name becomes each creator’s name.']],
    send: [['Last look! Read each email, then hit ', 'Send'], ['. You’ve got this.']]
  };
  const header = document.querySelector('.workspace-header');
  const buddy = document.createElement('div');
  buddy.className = 'owl-buddy'; buddy.hidden = true;
  const buddyOwl = document.createElement('span'); buddyOwl.className = 'owl-body'; buddyOwl.setAttribute('aria-hidden', 'true');
  const bubble = document.createElement('p'); bubble.className = 'bubble'; bubble.setAttribute('aria-live', 'polite');
  buddy.append(buddyOwl, bubble);
  header?.firstElementChild?.append(buddy);
  const cheer = document.createElement('span');
  cheer.className = 'cheer'; cheer.hidden = true;
  const cheerText = document.createElement('span');
  const cheerBar = document.createElement('span'); cheerBar.className = 'bar'; cheerBar.setAttribute('aria-hidden', 'true');
  const cheerFill = document.createElement('i'); cheerBar.append(cheerFill);
  cheer.append(cheerText, cheerBar);
  const localBadge = document.querySelector('.workspace-local');
  localBadge?.after(cheer);
  let finished = false;
  function setCheer(done) {
    cheerText.textContent = done >= 4 ? '4 of 4 done · You did it!' : done ? done + ' of 4 done · Nice work!' : 'Let’s go!';
    cheerFill.style.width = Math.max(6, done * 25) + '%';
  }
  function updateBuddy(page, step) {
    const lines = BUDDY[page];
    buddy.hidden = !lines || !tipsOn();
    if (lines) {
      const [[lead, key], [tail]] = lines;
      const strong = document.createElement('b'); strong.textContent = key;
      bubble.replaceChildren(document.createTextNode(lead), strong, document.createTextNode(tail));
    }
    cheer.hidden = !step;
    if (localBadge) localBadge.hidden = !!step;
    if (step) setCheer(finished && step === 4 ? 4 : step - 1);
  }

  function updateProgress() {
    const page = currentPage();
    const step = STEP_OF[page] || 0;
    const stepper = byId('flow-stepper');
    stepper.hidden = !step;
    for (const item of stepper.querySelectorAll('li')) {
      const n = Number(item.dataset.step);
      item.classList.toggle('is-current', n === step);
      item.classList.toggle('is-done', n < step);
      const link = item.querySelector('a');
      if (n === step) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current');
    }
    for (const link of document.querySelectorAll('#workspace-navigation a[href^="#"]')) {
      const target = STEP_OF[link.getAttribute('href').slice(1)];
      link.classList.toggle('is-done', !!target && !!step && target < step);
    }
    const tip = byId('flow-tip');
    const text = TIPS[page];
    tip.hidden = !text || !tipsOn();
    if (text) { byId('flow-tip-title').textContent = text[0]; byId('flow-tip-text').textContent = text[1]; }
    if (page !== 'send') finished = false;
    updateBuddy(page, step);
    if (tour.open) renderTour();
  }

  // ---------- Send celebration (fires only after Gmail accepted at least one email) ----------
  const CONFETTI = ['#f59e0b', '#ec4899', '#0ea5e9', '#8b5cf6', '#22c55e', '#f43f5e'];
  let celebration = null;
  function celebrate(result) {
    const accepted = Number(result?.accepted) || 0;
    if (!accepted) return;
    finished = true;
    celebration?.remove();
    const card = document.createElement('div');
    card.className = 'celebrate'; card.setAttribute('role', 'status');
    for (let i = 0; i < 28; i++) {
      const bit = document.createElement('i');
      bit.className = 'confetti'; bit.setAttribute('aria-hidden', 'true');
      bit.style.left = (i * 3.6) + '%';
      bit.style.background = CONFETTI[i % CONFETTI.length];
      bit.style.animationDelay = (-(i % 7) * 0.3) + 's';
      card.append(bit);
    }
    const owl = document.createElement('span'); owl.className = 'owl-body'; owl.setAttribute('aria-hidden', 'true');
    const textBox = document.createElement('div');
    const title = document.createElement('h3');
    title.textContent = 'Woohoo! ' + accepted + (accepted === 1 ? ' email is' : ' emails are') + ' on their way';
    const line = document.createElement('p');
    line.textContent = 'Replies will show up in your Delivery log.';
    const stats = document.createElement('div'); stats.className = 'stats';
    const failed = Number(result?.failed_or_unknown) || 0, skipped = Number(result?.skipped) || 0;
    const brand = byId('brand-name')?.value.trim();
    for (const words of [accepted + ' sent', failed + ' need review', skipped + ' skipped', brand].filter(Boolean)) {
      const chip = document.createElement('span'); chip.textContent = words; stats.append(chip);
    }
    textBox.append(title, line, stats);
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'secondary close'; close.textContent = 'Close';
    close.addEventListener('click', () => { card.remove(); celebration = null; });
    card.append(owl, textBox, close);
    const head = byId('send')?.querySelector('.section-head');
    if (head) head.after(card); else byId('send')?.prepend(card);
    celebration = card;
    updateProgress();
  }
  window.addEventListener('outreach:sent', e => celebrate(e.detail));
  function setTips(on) {
    store.set('outreach-tips', on ? 'on' : 'off');
    byId('tips-toggle').checked = on;
    updateProgress();
  }
  byId('flow-tip-hide').addEventListener('click', () => setTips(false));
  byId('tips-toggle').checked = tipsOn();
  byId('tips-toggle').addEventListener('change', e => setTips(e.target.checked));

  // ---------- Brand cards (built from the saved brand list) ----------
  const brandSelect = byId('library-brand');
  function appliedBrandLabel() {
    const name = byId('brand-name').value.trim(), product = byId('brand-product').value.trim();
    return name ? name + ' · ' + product : '';
  }
  function renderBrandCards() {
    const root = byId('brand-cards');
    const applied = appliedBrandLabel();
    const cards = [];
    for (const option of brandSelect.options) {
      if (!option.value) continue;
      const [name, ...rest] = option.text.split(' · ');
      const selected = option.text === applied;
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'brand-card' + (selected ? ' is-selected' : '');
      card.setAttribute('aria-pressed', String(selected));
      const badge = document.createElement('span'); badge.className = 'brand-initial'; badge.setAttribute('aria-hidden', 'true');
      badge.textContent = (name.trim()[0] || '?').toUpperCase();
      const title = document.createElement('strong'); title.textContent = name;
      const product = document.createElement('span'); product.className = 'brand-product'; product.textContent = rest.join(' · ');
      const state = document.createElement('span'); state.className = 'brand-state'; state.textContent = selected ? 'In use for this campaign' : 'Use this brand';
      card.append(badge, title, product, state);
      card.addEventListener('click', () => {
        brandSelect.value = option.value;
        byId('apply-brand').click();
      });
      cards.push(card);
    }
    const add = document.createElement('button');
    add.type = 'button'; add.className = 'brand-card brand-card-new';
    const plus = document.createElement('span'); plus.className = 'brand-plus'; plus.setAttribute('aria-hidden', 'true'); plus.textContent = '+';
    const label = document.createElement('strong'); label.textContent = 'Add a new brand';
    add.append(plus, label);
    add.addEventListener('click', () => byId('new-brand').click());
    cards.push(add);
    root.replaceChildren(...cards);
  }
  new MutationObserver(renderBrandCards).observe(brandSelect, { childList: true });
  new MutationObserver(renderBrandCards).observe(byId('email-brand-summary'), { childList: true, characterData: true, subtree: true });
  renderBrandCards();

  // ---------- Sample data ----------
  const SAMPLE_TITLE = 'Sample creators (demo)';
  const SAMPLE_CSV = [
    'name,username,profile_url,email,followers,region,language,source',
    'Sample Creator Alex,sample_alex,https://www.tiktok.com/@sample_alex,sample.alex@example.com,182000,US,en,SAMPLE DATA',
    'Sample Creator Maya,sample_maya,https://www.tiktok.com/@sample_maya,sample.maya@example.com,64000,US,en,SAMPLE DATA',
    'Sample Creator Sam,sample_sam,https://www.tiktok.com/@sample_sam,sample.sam@example.com,120000,US,en,SAMPLE DATA'
  ].join('\n');
  async function loadSampleData() {
    const status = byId('welcome-status');
    status.textContent = 'Loading sample data…';
    try {
      const runs = (await api('/api/runs')).runs || [];
      let run = runs.find(r => r.title === SAMPLE_TITLE);
      if (!run) run = await api('/api/import', { csv_text: SAMPLE_CSV, title: SAMPLE_TITLE });
      const hasSampleBrand = [...brandSelect.options].some(o => o.text.startsWith('Luma (sample)'));
      if (!hasSampleBrand) {
        await api('/api/brand-brief', {
          name: 'Luma (sample)', product: 'Vitamin C serum', goal: 'Paid TikTok posts with US skincare creators',
          offer: 'Paid fee and a product sample', language: 'English', regions: 'US', content_keywords: 'skincare, vitamin C', signature: '[Your name]'
        });
      }
      await refreshRuns();
      byId('run-select').value = run.id;
      await loadRun(run.id);
      status.textContent = '';
      closeWelcome();
      window.OutreachPages.go('brand');
      openTour(0);
    } catch (error) {
      status.textContent = 'Sample data could not be loaded: ' + error.message;
    }
  }

  // ---------- Welcome dialog ----------
  const welcome = byId('welcome-dialog');
  let lastFocus = null;
  function openWelcome() {
    closeTour();
    lastFocus = document.activeElement;
    welcome.hidden = false;
    byId('help-fab').hidden = true;
    byId('welcome-tour').focus();
  }
  function closeWelcome() {
    welcome.hidden = true;
    store.set('outreach-welcome-seen', '1');
    byId('help-fab').hidden = tour.open;
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }
  byId('welcome-skip').addEventListener('click', closeWelcome);
  byId('welcome-tour').addEventListener('click', () => { closeWelcome(); window.OutreachPages.go('brand'); openTour(0); });
  byId('welcome-sample').addEventListener('click', loadSampleData);
  welcome.addEventListener('keydown', e => { if (e.key === 'Escape') closeWelcome(); });
  welcome.addEventListener('click', e => { if (e.target === welcome) closeWelcome(); });
  byId('open-tutorial').addEventListener('click', openWelcome);
  byId('replay-tutorial').addEventListener('click', openWelcome);

  // ---------- Tour card ----------
  const TOUR = [
    { page: 'brand', title: '1. Choose a brand', text: 'Pick the brand you are promoting, or add a new one. Creator matches and emails are written for it.' },
    { page: 'discover', title: '2. Choose creators', text: 'Search EasyKOL, or switch to My lists and import to upload your own list. Tick the creators you want to contact.' },
    { page: 'compose', title: '3. Confirm the template', text: 'Load a saved template or edit the wording. $name is filled in for each creator.' },
    { page: 'send', title: '4. Preview and send', text: 'Read each email, tick the confirmation box, then send. Replies appear in the Delivery log.' }
  ];
  const tour = { open: false };
  function tourIndex() {
    const step = STEP_OF[currentPage()];
    return step ? step - 1 : 0;
  }
  function renderTour() {
    const i = tourIndex(), item = TOUR[i];
    byId('tour-count').textContent = 'Tutorial · Step ' + (i + 1) + ' of 4';
    byId('tour-title').textContent = item.title;
    byId('tour-text').textContent = item.text;
    byId('tour-back').disabled = i === 0;
    byId('tour-next').textContent = i === TOUR.length - 1 ? 'Finish' : 'Next';
    byId('tour-card').querySelectorAll('.tour-dots span').forEach((dot, n) => dot.classList.toggle('is-on', n <= i));
  }
  function openTour(index) {
    tour.open = true;
    if (typeof index === 'number') window.OutreachPages.go(TOUR[index].page);
    byId('tour-card').hidden = false;
    byId('help-fab').hidden = true;
    renderTour();
    byId('tour-next').focus();
  }
  function closeTour() {
    tour.open = false;
    byId('tour-card').hidden = true;
    byId('help-fab').hidden = !welcome.hidden;
  }
  byId('tour-close').addEventListener('click', closeTour);
  byId('tour-back').addEventListener('click', () => { const i = tourIndex(); if (i > 0) window.OutreachPages.go(TOUR[i - 1].page); });
  byId('tour-next').addEventListener('click', () => {
    const i = tourIndex();
    if (i >= TOUR.length - 1) closeTour(); else window.OutreachPages.go(TOUR[i + 1].page);
  });
  byId('tour-card').addEventListener('keydown', e => { if (e.key === 'Escape') closeTour(); });
  byId('help-fab').addEventListener('click', () => openTour());

  window.addEventListener('hashchange', updateProgress);
  updateProgress();
  if (store.get('outreach-welcome-seen') !== '1') openWelcome();
  window.OutreachGuide = { openWelcome, openTour, closeTour, applyTheme, celebrate };
})();
