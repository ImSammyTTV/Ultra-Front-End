// ---------- Add-ons ----------
// Small extras people can install from Settings › Add-ons. Each add-on is one script that calls UFE.addon({...}).
// The catalogue (addons/catalog.json) lists what can be installed: id, title, description, author, icon, script.
// Each add-on gets its own api (see ADDONS.md): places to draw, events, the library, the song playing, sound, its own
// settings and storage, its own rows in Quick Access and Settings. Everything it adds through the api (listeners,
// timers, styles, rows, elements) is taken away again when it's removed, so a removed add-on leaves nothing behind.
const ADDONS = { catalog: [], loaded: {}, defs: {}, ctx: {}, events: {}, qa: {} };
const addonState = () => { try { return JSON.parse(localStorage.getItem('fe-addons') || '{}'); } catch { return {}; } };
const addonSave = st => { try { localStorage.setItem('fe-addons', JSON.stringify(st)); } catch {} };

// events: the app calls addonEmit; add-ons listen with api.on(name, fn)
function addonEmit(name, data) {
  let used = false;
  for (const fn of [...(ADDONS.events[name] || [])]) { try { if (fn(data) === true) used = true; } catch (e) { console.error(e); } }
  return used;  // for 'input': true when an add-on took the press
}
// the song playing, asked for only while an add-on listens for 'song'
let addonSongKey = null;
setInterval(async () => {
  if (!ADDONS.events.song?.length || typeof api !== 'function') return;
  try {
    const s = await api('/api/nowplaying'), key = s?.title ? `${s.title}|${s.artist}|${s.playing}` : '';
    if (key !== addonSongKey) { addonSongKey = key; addonEmit('song', s?.title ? s : null); }
  } catch {}
}, 5000);

// one add-on's own api: the same for every add-on, but what it adds is remembered so it can be taken away
function addonApi(id) {
  const own = { off: [], timers: [], els: [], styles: [] };
  const ctx = {
    id, version: 2,
    // where it can draw: 'header' (by the clock), 'home' (a layer over the home screen), 'quickaccess' (top of Quick Access)
    slot: name => document.querySelector(`[data-addon-slot="${name}"]`),
    add(slotName, el) { const s = ctx.slot(slotName); if (!s || !el) return null; slotName === 'header' && s.querySelector('#clock') ? s.querySelector('#clock').before(el) : s.append(el); own.els.push(el); return el; },
    css(text) { const st = document.createElement('style'); st.dataset.addon = id; st.textContent = text; document.head.append(st); own.styles.push(st); return st; },
    // events: 'game:start' {game}, 'game:running' {games}, 'game:exit' {game}, 'song' {title, artist, playing, art} or null,
    // 'quickaccess:open', 'quickaccess:close', 'input' (the button pressed: return true to take it), 'library' (games list)
    on(name, fn) { (ADDONS.events[name] ||= []).push(fn); const off = () => { ADDONS.events[name] = (ADDONS.events[name] || []).filter(f => f !== fn); }; own.off.push(off); return off; },
    every(ms, fn) { const t = setInterval(fn, Math.max(1000, ms)); own.timers.push(t); return t; },  // at most once a second
    after(ms, fn) { const t = setTimeout(fn, ms); own.timers.push(t); return t; },
    // the library and what's running
    games: () => LIB.map(g => ({ id: g.id, title: g.title, platform: g.platform, cover: g.cover, installed: g.installed !== false, lastPlayed: g.lastPlayed || 0, favorite: !!g.favorite })),
    game: gid => ctx.games().find(g => g.id === gid) || null,
    running: () => ctx.games().filter(g => RUN.has(g.id)),
    launch: gid => { const g = LIB.find(x => x.id === gid); if (g) launchGame(g); },
    // the song Windows is playing, and its controls: 'play', 'next', 'prev'
    nowPlaying: () => api('/api/nowplaying').then(s => s?.title ? s : null).catch(() => null),
    media: action => api('/api/overlay', { action: { play: 'media-play', next: 'media-next', prev: 'media-prev' }[action] }).catch(() => {}),
    volume: () => api('/api/volume').catch(() => null),
    setVolume: delta => api('/api/volume', { delta }).catch(() => null),
    // the person and the app
    profile: () => ({ name: PROFILE.name, avatar: PROFILE.avatar, timezone: PROFILE.timezone }),
    timezone: () => PROFILE.timezone,
    // talking to them
    toast: (text, ms) => toast(String(text), ms),
    ask: (label, done, max = 60) => openSearch(null, text => done(text.trim()), { id: 'addon', label, max }),  // the on-screen keyboard
    sound: (pitch = 760, level = .06) => tick(pitch, level),
    openSettings: () => { closeSys?.(); openPanel(); },
    // its own saved things: settings (shown in its Settings page) and a small store for anything else
    settings: (aid = id) => addonState()[aid]?.settings || {},
    saveSettings(aid, patch) { if (typeof aid === 'object') { patch = aid; aid = id; } const st = addonState(); st[aid] = { ...(st[aid] || {}), settings: { ...(st[aid]?.settings || {}), ...patch } }; addonSave(st); addonRefresh(aid); },
    store: {
      get: (key, fallback = null) => { try { const v = localStorage.getItem(`fe-addon-${id}-${key}`); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
      set: (key, value) => { try { localStorage.setItem(`fe-addon-${id}-${key}`, JSON.stringify(value)); } catch {} },
      remove: key => { try { localStorage.removeItem(`fe-addon-${id}-${key}`); } catch {} },
    },
    // rows of its own in Quick Access: rows() returns [{ icon, label, sub, value, run }], asked each time it's drawn
    quickAccess(rows) { ADDONS.qa[id] = rows; return () => delete ADDONS.qa[id]; },
    refresh: () => { if (typeof SP !== 'undefined' && SP.open) renderSys(); },
    icon: name => icon(name),
  };
  ctx._cleanup = () => {
    own.off.forEach(f => f()); own.timers.forEach(t => { clearInterval(t); clearTimeout(t); });
    own.els.forEach(e => e.remove()); own.styles.forEach(s => s.remove()); delete ADDONS.qa[id];
    own.off = []; own.timers = []; own.els = []; own.styles = [];
  };
  return ctx;
}

// What an add-on script sees globally: UFE.addon registers it. The rest is kept so older add-ons still work.
const UFE = {
  version: 2,
  addon(def) { ADDONS.defs[def.id] = def; if (addonState()[def.id]?.installed) addonMount(def.id); },
  slot: name => document.querySelector(`[data-addon-slot="${name}"]`),
  settings: aid => addonState()[aid]?.settings || {},
  saveSettings: (aid, patch) => addonApi(aid).saveSettings(aid, patch),
  timezone: () => PROFILE.timezone,
  ask: (label, done, max = 60) => openSearch(null, text => done(text.trim()), { id: 'addon', label, max }),
  toast: (text, ms) => toast(text, ms),
};

function addonMount(id) {
  const def = ADDONS.defs[id];
  if (!def || ADDONS.loaded[id]) return;
  const ctx = ADDONS.ctx[id] = addonApi(id);
  try { ADDONS.loaded[id] = true; def.mount?.call(def, ctx); } catch (e) { console.error(e); }
}
function addonUnmount(id) {
  const def = ADDONS.defs[id];
  if (!ADDONS.loaded[id]) return;
  try { def?.unmount?.call(def, ADDONS.ctx[id]); } catch (e) { console.error(e); }
  ADDONS.ctx[id]?._cleanup();
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
// Quick Access rows from add-ons, each turned into the app's own row shape
function addonQaRows() {
  return Object.entries(ADDONS.qa).flatMap(([id, fn]) => {
    try { return (fn() || []).map(r => ({ ic: r.icon || 'settings', label: String(r.label || ''), sub: r.sub ? String(r.sub) : '', value: r.value != null ? String(r.value) : '', run: r.run ? () => { try { r.run(); } catch (e) { console.error(e); } } : null })); }
    catch (e) { console.error(e); return []; }
  });
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
      ...(on && ADDONS.defs[a.id]?.options ? ADDONS.defs[a.id].options(ADDONS.ctx[a.id] || UFE) : []),
    ];
  });
}
// every installed add-on starts with the page
fetch('addons/catalog.json').then(r => r.json()).then(list => {
  ADDONS.catalog = list;
  const st = addonState();
  list.filter(a => st[a.id]?.installed).forEach(addonLoad);
}).catch(() => {});
