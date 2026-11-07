// ---------- Add-ons ----------
// Small extras people can install from Settings › Add-ons. Each add-on is one script that calls UFE.addon({...}).
// The catalogue (addons/catalog.json) lists what can be installed: id, title, description, author, icon, script.
// An add-on draws into a "slot" the page offers (for now "header", next to the clock), keeps its own settings, and
// can add rows to its page in Settings. See docs/ADDONS.md for how to write one and submit it.
const ADDONS = { catalog: [], loaded: {}, defs: {} };
const addonState = () => { try { return JSON.parse(localStorage.getItem('fe-addons') || '{}'); } catch { return {}; } };
const addonSave = st => { try { localStorage.setItem('fe-addons', JSON.stringify(st)); } catch {} };

// What an add-on script sees
const UFE = {
  version: 1,
  // register: { id, mount(slotElement, api), unmount?(), options?() -> Settings rows }
  addon(def) { ADDONS.defs[def.id] = def; if (addonState()[def.id]?.installed) addonMount(def.id); },
  slot(name) { return document.querySelector(`[data-addon-slot="${name}"]`); },
  settings(id) { return addonState()[id]?.settings || {}; },
  saveSettings(id, patch) { const st = addonState(); st[id] = { ...(st[id] || {}), settings: { ...(st[id]?.settings || {}), ...patch } }; addonSave(st); addonRefresh(id); },
  timezone: () => PROFILE.timezone,
  ask: (label, done, max = 60) => openSearch(null, text => done(text.trim()), { id: 'addon', label, max }),  // the on-screen keyboard
  toast: (text, ms) => toast(text, ms),
};

function addonMount(id) {
  const def = ADDONS.defs[id];
  if (!def || ADDONS.loaded[id]) return;
  try { ADDONS.loaded[id] = true; def.mount?.(UFE); } catch (e) { console.error(e); }
}
function addonUnmount(id) {
  const def = ADDONS.defs[id];
  if (!ADDONS.loaded[id]) return;
  try { def?.unmount?.(UFE); } catch (e) { console.error(e); }
  ADDONS.loaded[id] = false;
}
function addonRefresh(id) { if (ADDONS.loaded[id]) { addonUnmount(id); addonMount(id); } }
function addonLoad(entry) {
  if (ADDONS.defs[entry.id]) return addonMount(entry.id);
  const s = document.createElement('script');
  s.src = entry.script;
  document.head.appendChild(s);  // the script registers itself with UFE.addon
}
function addonSet(entry, installed) {
  const st = addonState();
  st[entry.id] = { ...(st[entry.id] || {}), installed };
  addonSave(st);
  if (installed) addonLoad(entry); else addonUnmount(entry.id);
  toast(installed ? `${entry.title} installed` : `${entry.title} removed`, 2500);
  renderPanel();
}
// Settings › Add-ons
function addonRows() {
  if (!ADDONS.catalog.length) return [{ kind: 'note', label: 'No add-ons yet.' }];
  const st = addonState();
  return ADDONS.catalog.flatMap(a => {
    const on = !!st[a.id]?.installed;
    return [
      { kind: 'head', label: a.title },
      { kind: 'row', ic: `<img class="paddon" src="${esc(a.icon)}" alt="">`, label: a.title, sub: `${a.description} · by ${a.author}`, value: on ? 'Remove' : 'Install', act: () => addonSet(a, !on) },
      ...(on && ADDONS.defs[a.id]?.options ? ADDONS.defs[a.id].options(UFE) : []),
    ];
  });
}
// every installed add-on starts with the page
fetch('addons/catalog.json').then(r => r.json()).then(list => {
  ADDONS.catalog = list;
  const st = addonState();
  list.filter(a => st[a.id]?.installed).forEach(addonLoad);
}).catch(() => {});
