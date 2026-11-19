// Desktop owl: double-click any owl in the workspace to send it to your desktop,
// and switch it on or off in Settings. The server starts or stops scripts/owl_pet.py.
(() => {
  'use strict';
  const OWLS = '.owl-mark, .owl-body';
  let state = { running: false, supported: true };
  let busy = false;
  let toastTimer = null;

  function toast(text) {
    let box = document.getElementById('pet-toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'pet-toast'; box.className = 'pet-toast';
      box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite');
      document.body.append(box);
    }
    box.textContent = text; box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 3500);
  }

  async function call(action) {
    const result = await api('/api/pet', { action });
    state = { running: !!result.running, supported: result.supported !== false };
    render();
    return state;
  }

  async function setPet(on) {
    if (busy) return;
    busy = true; render();
    try {
      const before = state.running;
      const after = await call(on ? 'start' : 'stop');
      if (on) toast(before ? 'The desktop owl is already out. Look at the edge of your screen.' : 'The owl is on your desktop now. Click it any time to come back here.');
      else toast(after.running ? 'The desktop owl could not be closed. Right-click it and choose Quit owl.' : 'The desktop owl is back in the workspace.');
    } catch (error) {
      toast(error.message || 'The desktop owl could not be changed.');
    } finally {
      busy = false; render();
    }
  }

  function render() {
    const toggle = document.getElementById('pet-toggle');
    if (!toggle) return;
    toggle.setAttribute('aria-checked', String(state.running));
    toggle.disabled = busy || !state.supported;
    document.getElementById('pet-toggle-state').textContent = busy ? 'Working…' : state.running ? 'On' : 'Off';
    document.getElementById('pet-toggle-note').hidden = state.supported;
  }

  function buildSettings() {
    const host = document.getElementById('appearance-settings');
    if (!host || document.getElementById('pet-settings')) return;
    const card = document.createElement('div');
    card.id = 'pet-settings'; card.className = 'pet-settings';
    const text = document.createElement('div');
    const title = document.createElement('h3'); title.id = 'pet-toggle-label'; title.textContent = 'Desktop owl';
    const hint = document.createElement('p'); hint.className = 'hint';
    hint.textContent = 'A small owl peeks out from the edge of your screen. Click it to come back to Outreach. Tip: double-click any owl on this page to turn it on.';
    const note = document.createElement('p'); note.id = 'pet-toggle-note'; note.className = 'hint'; note.hidden = true;
    note.textContent = 'The desktop owl runs on Windows.';
    text.append(title, hint, note);
    const toggle = document.createElement('button');
    toggle.type = 'button'; toggle.id = 'pet-toggle'; toggle.className = 'pet-switch';
    toggle.setAttribute('role', 'switch'); toggle.setAttribute('aria-labelledby', 'pet-toggle-label');
    toggle.setAttribute('aria-checked', 'false');
    const knob = document.createElement('span'); knob.className = 'pet-knob'; knob.setAttribute('aria-hidden', 'true');
    const label = document.createElement('span'); label.id = 'pet-toggle-state'; label.textContent = 'Off';
    toggle.append(knob, label);
    toggle.addEventListener('click', () => setPet(toggle.getAttribute('aria-checked') !== 'true'));
    card.append(text, toggle);
    const anchor = document.getElementById('owl-outfit-settings') || host.querySelector(':scope > .actions');
    if (anchor && anchor.id === 'owl-outfit-settings') anchor.after(card); else host.insertBefore(card, anchor || null);
    render();
  }

  document.addEventListener('dblclick', event => {
    const owl = event.target.closest?.(OWLS);
    if (!owl || owl.closest('.outfit-option')) return;
    event.preventDefault();
    window.getSelection?.()?.removeAllRanges();
    if (!state.supported) { toast('The desktop owl runs on Windows.'); return; }
    setPet(true);
  });

  // Settings is built by other scripts too; add the card once the page has settled.
  setTimeout(() => { buildSettings(); call('status').catch(() => {}); }, 0);
  window.OutreachPet = { start: () => setPet(true), stop: () => setPet(false), status: () => call('status') };
})();
