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
    // opts: { title, icon } for the row they fold under (the add-on's own title if not given)
    quickAccess(rows, opts = {}) { ADDONS.qa[id] = rows; ADDONS.qaOpts = { ...(ADDONS.qaOpts || {}), [id]: opts }; return () => delete ADDONS.qa[id]; },
    refresh: () => { if (typeof SP !== 'undefined' && SP.open) renderSys(); },
    icon: name => icon(name),
    // a card of its own over the game, in the corner: { icon, text, sub, progress 0-100 }, or null to take it away.
    // Shown only while a game runs; send it again at least every two minutes, or it's taken away (the add-on stopped).
    hud: item => { own.hud = !!item; return api('/api/addon-hud', { id, item: item || null }).catch(() => {}); },
    // the app's own server, for an add-on that has a part there (like Bambu Lab's printer connection)
    request: (path, body) => api(path, body),
  };
  ctx._cleanup = () => {
    own.off.forEach(f => f()); own.timers.forEach(t => { clearInterval(t); clearTimeout(t); });
    own.els.forEach(e => e.remove()); own.styles.forEach(s => s.remove()); delete ADDONS.qa[id];
    if (own.hud) api('/api/addon-hud', { id, item: null }).catch(() => {});
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
  s.dataset.addonScript = entry.id;
  document.head.appendChild(s);  // the script registers itself with UFE.addon
}
// A changed add-on (its file is newer) is taken down and its script loaded again, so edits show at once
function addonReload(entry) {
  const on = ADDONS.loaded[entry.id];
  addonUnmount(entry.id);
  delete ADDONS.defs[entry.id];
  document.querySelectorAll(`script[data-addon-script="${entry.id}"]`).forEach(x => x.remove());
  if (on || addonState()[entry.id]?.installed) addonLoad(entry);
}
function addonSet(entry, installed) {
  const st = addonState();
  st[entry.id] = { ...(st[entry.id] || {}), installed };
  addonSave(st);
  if (installed) addonLoad(entry); else addonUnmount(entry.id);
  toast(installed ? `${entry.title} installed` : `${entry.title} removed`, 2500);
  renderPanel();
}
// Quick Access rows from add-ons, each add-on's under its own title, turned into the app's own row shape
const addonTitle = id => ADDONS.qaOpts?.[id]?.title || ADDONS.catalog.find(a => a.id === id)?.title || id;
function addonQaGroups() {
  return Object.entries(ADDONS.qa).map(([id, fn]) => {
    let rows = [];
    try { rows = (fn() || []).map(r => ({ ic: r.icon || 'settings', label: String(r.label || ''), sub: r.sub ? String(r.sub) : '', value: r.value != null ? String(r.value) : '', run: r.run ? () => { try { r.run(); } catch (e) { console.error(e); } } : null })); }
    catch (e) { console.error(e); }
    return { title: addonTitle(id), rows };
  });
}
function addonQaIcons() { return Object.fromEntries(Object.keys(ADDONS.qa).map(id => [addonTitle(id), ADDONS.qaOpts?.[id]?.icon || 'settings'])); }
// Settings › Add-ons
function addonRows() {
  const st = addonState();
  const folder = ADDONS.folder ? [{ kind: 'head', label: 'Your own' }, { kind: 'row', ic: icon('folder'), label: 'Add-ons folder',
    sub: 'Put an add-on in its own folder here (addon.json and its script). It shows up at once, and edits reload by themselves',
    act: () => api('/api/addons/open', {}).catch(e => toast(e.message)) }] : [];
  if (!ADDONS.catalog.length) return [{ kind: 'note', label: 'No add-ons yet.' }, ...folder];
  return [...ADDONS.catalog.flatMap(a => {
    const on = !!st[a.id]?.installed;
    return [
      { kind: 'head', label: a.title },
      // installed: A opens or closes its settings (and Remove, at the end of them); not installed: A installs it
      { kind: 'row', ic: `<img class="paddon" src="${esc(a.icon)}" alt="">`, label: a.title, sub: `${a.description} · by ${a.author}${a.own ? ' · from your add-ons folder' : ''}`,
        value: on ? (ADDONS.open === a.id ? '▴' : '▾') : 'Install',
        act: () => { if (!on) return addonSet(a, true); ADDONS.open = ADDONS.open === a.id ? '' : a.id; renderPanel(); } },
      ...(on && ADDONS.open === a.id ? [
        ...(ADDONS.defs[a.id]?.options ? ADDONS.defs[a.id].options(ADDONS.ctx[a.id] || UFE) : []),
        { kind: 'row', ic: icon('close'), label: `Remove ${a.title}`, warn: true, sub: 'Takes it off; install it again any time', act: () => { ADDONS.open = ''; addonSet(a, false); } },
      ] : []),
    ];
  }), ...folder];
}
// every installed add-on starts with the page: the built-in catalogue, then your own from the data folder, which is
// looked at again every few seconds so a new or edited add-on works without restarting
let BUILTIN = [];
async function addonScan(first) {
  let own = [];
  try { own = (await api('/api/addons')).addons; ADDONS.folder = true; } catch {}
  const before = new Map(ADDONS.catalog.map(a => [a.id, a]));
  ADDONS.catalog = [...BUILTIN.filter(b => !own.some(o => o.id === b.id)), ...own];
  const st = addonState();
  for (const a of ADDONS.catalog) {
    const old = before.get(a.id);
    if (first || !old) { if (st[a.id]?.installed) addonLoad(a); }
    else if (a.stamp && old.stamp !== a.stamp) { addonReload(a); if (st[a.id]?.installed) toast(`${a.title} reloaded`, 1600); }
  }
  for (const [id] of before) if (!ADDONS.catalog.some(a => a.id === id)) addonUnmount(id);  // its folder was deleted
  if (!first && typeof P !== 'undefined' && P.open && ADDONS.catalog.length !== before.size) renderPanel();
}
fetch('addons/catalog.json').then(r => r.json()).catch(() => []).then(list => { BUILTIN = list; return addonScan(true); })
  .then(() => setInterval(() => { if (document.visibilityState !== 'hidden') addonScan(false); }, 3000));
