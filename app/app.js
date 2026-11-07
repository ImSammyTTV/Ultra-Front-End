// Home screen: one row of covers, round shortcut buttons, source tabs.
const ON_MAC = /Macintosh|Mac OS X/.test(navigator.userAgent), ON_ANDROID = /Android/.test(navigator.userAgent),
  HERE = ON_MAC ? 'this Mac' : ON_ANDROID ? 'this device' : 'this PC';  // the page's word for the computer
// Focus zones (up/down): 0 = game row, 1 = buttons, 2 = source tabs.
const $ = q => document.querySelector(q);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const raf2 = f => requestAnimationFrame(() => requestAnimationFrame(f));

const ICONS = {
  speaker: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/><path d="M19 6a8.5 8.5 0 0 1 0 12"/>',
  headset: '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
  wifi: '<path d="M2.5 9a14 14 0 0 1 19 0"/><path d="M5.5 12.5a9.5 9.5 0 0 1 13 0"/><path d="M8.7 16a5 5 0 0 1 6.6 0"/><circle cx="12" cy="19.3" r="1"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  bellOff: '<path d="M6 16V11a6 6 0 0 1 9.5-4.9"/><path d="M18 11v5l1.5 2H8"/><path d="M10 20a2 2 0 0 0 4 0"/><path d="M4 4l16 16"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  exit: '<path d="M14 4h5v16h-5"/><path d="M4 12h10"/><path d="M10 8l4 4-4 4"/>',
  power: '<path d="M12 3v9"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
  download: '<path d="M12 4v11"/><path d="M7 10.5l5 5 5-5"/><path d="M5 20h14"/>',
  more: '<circle cx="5.5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="18.5" cy="12" r="1.3" fill="currentColor"/>',
  friends: '<circle cx="9" cy="8.5" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M15.5 5.3a3.5 3.5 0 0 1 0 6.4"/><path d="M18 14.6a6.5 6.5 0 0 1 3.5 5.4"/>',
  volume: '<path d="M4 9.5v5h4l5 4v-13l-5 4z"/><path d="M16.5 9a4 4 0 0 1 0 6"/><path d="M19 6.5a8 8 0 0 1 0 11"/>',
  mute: '<path d="M4 9.5v5h4l5 4v-13l-5 4z"/><path d="M17 9.5l5 5"/><path d="M22 9.5l-5 5"/>',
  music: '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
  news: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 15h5"/>',
  library: '<path d="M4 4v16M8 4v16"/><rect x="11" y="4" width="4" height="16" rx="1"/><path d="M17.5 5.5l3 14"/>',
  pad: '<rect x="2" y="7" width="20" height="11" rx="5.5"/><path d="M7 10.5v4M5 12.5h4"/><circle cx="15.5" cy="11.5" r=".9" fill="currentColor"/><circle cx="18" cy="13.8" r=".9" fill="currentColor"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h.01M18 14h.01M9.5 14h5"/>',
  album: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9.5" r="1.6"/><path d="M3 17l5-4.5 4 3.5 3-2.5 6 5"/>',
  controllers: '<path d="M6.5 8h11a4.5 4.5 0 0 1 4.3 5.8l-1 3.4a2.2 2.2 0 0 1-3.8.8L15 16H9l-2 2a2.2 2.2 0 0 1-3.8-.8l-1-3.4A4.5 4.5 0 0 1 6.5 8z"/><path d="M8 11v3M6.5 12.5h3"/><circle cx="16" cy="12" r=".8" fill="currentColor"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  heart: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  flame: '<path d="M12 22a7 7 0 0 0 7-7c0-4-3-6-4-9-1 2-2 3-3 3 0-2-1-4-3-6 0 4-4 6-4 12a7 7 0 0 0 7 7z"/>',
  crown: '<path d="M3 8l4 4 5-7 5 7 4-4-2 11H5z"/>',
  ghost: '<path d="M5 21V10a7 7 0 0 1 14 0v11l-3-2-2 2-2-2-2 2-2-2z"/><circle cx="9.5" cy="10" r=".9" fill="currentColor"/><circle cx="14.5" cy="10" r=".9" fill="currentColor"/>',
  planet: '<circle cx="12" cy="12" r="5"/><path d="M3.5 16c2.5 2 15.5-4.5 17-9"/>',
  rocket: '<path d="M12 2c4 3 5 8 4 13H8C7 10 8 5 12 2z"/><path d="M8 15l-3 4h4M16 15l3 4h-4"/><circle cx="12" cy="9" r="1.5"/>',
  cat: '<path d="M5 4l3 4h8l3-4v10a7 7 0 0 1-14 0z"/><circle cx="9.5" cy="12" r=".9" fill="currentColor"/><circle cx="14.5" cy="12" r=".9" fill="currentColor"/>',
  leaf: '<path d="M5 19C5 9 12 4 20 4c0 8-5 15-15 15z"/><path d="M5 19l8-8"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="M3 16l5-4 4 3 3-2 6 5"/>',
  wide: '<rect x="2" y="7" width="20" height="10" rx="2"/><path d="M2 14l5-3 4 2.5 4-3 7 4"/>',
  reset: '<path d="M4 4v6h6"/><path d="M5 15a8 8 0 1 0 2-9l-3 4"/>',
  eyeoff: '<path d="M3 3l18 18"/><path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 9 6 9 6a17 17 0 0 1-3 3.6M6.6 7.6C4.2 9.2 3 12 3 12s4 6 9 6a9 9 0 0 0 4.4-1.2"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  eye: '<path d="M3 12s4-6 9-6 9 6 9 6-4 6-9 6-9-6-9-6z"/><circle cx="12" cy="12" r="3"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
const icon = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${ICONS[n]}</svg>`;

// Games come from the local helper (server.py). Opened as a plain file, the placeholder library.js is used instead.
const API = location.protocol.startsWith('http');
let LIB = [];
let TABS = [{ name: 'All Games', has: () => true }];
let NEWS_DOT = false;  // a new version's notes not seen yet: a dot on the News button
// Steam's key page, step by step: the first time, Steam shows a Register form asking for a domain name
const STEAM_KEY_STEPS = ['1. Choose “Open Steam’s API key page” below and sign in to Steam there.',
  '2. The first time, Steam shows “Register Steam Web API Key” and asks for a Domain Name: type localhost (any name works, it isn’t used).',
  '3. Tick “I agree to the Steam Web API Terms of Use” and choose Register.',
  '4. Copy the Key it shows, come back here, select the box below and choose Paste on the keyboard (or press Ctrl+V), then Connect.',
  'Steam only gives keys to accounts that have bought something on Steam.'].join(String.fromCharCode(10));
const BUTTONS = [
  { name: 'Library', icon: 'library', run: () => openLibraryPage('pc') },
  { name: 'Emulators', icon: 'pad', run: () => openLibraryPage('emu') },
  { name: 'Album', icon: 'album', run: () => openAlbum() },
  { name: 'Search', icon: 'search', run: () => openSearch() },
  { name: 'News', icon: 'news', run: () => openNewsPage() },
  { name: 'Settings', icon: 'settings', run: () => openPanel() },
];

// Safari's engine (the Mac app) draws some glass differently; styles.css adjusts for it under .webkit
if (/AppleWebKit/.test(navigator.userAgent) && !/Chrome|Edg\//.test(navigator.userAgent)) document.documentElement.classList.add('webkit');

const S = { dir: 1, tab: 0, tabName: 'All Games', zone: 0, btn: 0, sel: {}, list: [], sound: true, busy: false, pad: false };
try { Object.assign(S, JSON.parse(localStorage.getItem('fe-home') || '{}'), { tab: 0, zone: 0, busy: false, pad: false }); } catch {}
const save = () => { try { localStorage.setItem('fe-home', JSON.stringify({ tabName: TABS[S.tab].name, sel: S.sel, sound: S.sound, uiVolume: S.uiVolume, uiScale: S.uiScale, optKey: S.optKey, tabIcons: S.tabIcons, trailerVolume: S.trailerVolume, trailerMuted: S.trailerMuted })); } catch {} };
// Settings › General › UI scale: styles.css sizes every screen by --scale, except the backdrop
const SCALE = { min: .75, max: 1.25, step: .05 };  // past 125% the home row and its title run off a 16:9 screen
const uiScale = () => S.uiScale ?? 1;
const applyScale = () => document.documentElement.style.setProperty('--scale', uiScale());
applyScale();
// Selection is remembered per tab, by game id, so it survives rescans.
const idx = () => Math.max(0, S.list.findIndex(g => g.id === S.sel[TABS[S.tab].name]));
const game = () => S.list[idx()];
const select = i => { if (S.list[i]) S.sel[TABS[S.tab].name] = S.list[i].id; };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hue = s => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
const colorOf = g => g.color || `hsl(${hue(g.title)},45%,42%)`;

async function api(path, body) {
  let r;
  try { r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Frontend': '1' }, body: JSON.stringify(body) }); }
  catch { throw new Error('The frontend helper isn’t running. Close Ultra Front End and open it again.'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Something went wrong (${r.status})`);
  return j;
}
// ---------- profile: name, icon, time zone ----------
const AVATARS = [
  ['pad', '#38bdf8', '#1d4ed8'], ['star', '#fbbf24', '#ea580c'], ['bolt', '#a3e635', '#15803d'], ['heart', '#fb7185', '#be123c'],
  ['moon', '#a5b4fc', '#4338ca'], ['flame', '#fb923c', '#b91c1c'], ['crown', '#fde047', '#a16207'], ['ghost', '#e2e8f0', '#64748b'],
  ['planet', '#5eead4', '#0f766e'], ['rocket', '#f0abfc', '#7e22ce'], ['cat', '#fcd34d', '#c2410c'], ['leaf', '#86efac', '#166534'],
];
const TIMEZONES = ['America/Los_Angeles', 'America/Denver', 'America/Chicago', 'America/New_York', 'America/Halifax', 'America/Sao_Paulo',
  'Europe/London', 'Europe/Dublin', 'Europe/Lisbon', 'Europe/Paris', 'Europe/Berlin', 'Europe/Madrid', 'Europe/Rome', 'Europe/Athens',
  'Europe/Istanbul', 'Europe/Moscow', 'Africa/Johannesburg', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Bangkok', 'Asia/Singapore', 'Asia/Shanghai',
  'Asia/Tokyo', 'Asia/Seoul', 'Australia/Perth', 'Australia/Brisbane', 'Australia/Sydney', 'Pacific/Auckland'];
let PROFILE = { name: '', avatar: '', timezone: 'auto', picture: '', setupDone: true };
const NAME_MAX = 32;  // the helper keeps this much of a name
const localZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
const zoneName = z => z === 'auto' ? `Automatic (${localZone().split('/').pop().replace(/_/g, ' ')})` : z.split('/').pop().replace(/_/g, ' ');
const timeIn = z => { try { return new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, ...(z && z !== 'auto' && { timeZone: z }) }); } catch { return timeIn('auto'); } };
// The profile's time zone as a date option; one this browser doesn't know (an old or hand-edited config) means this PC's
const zoneOpt = (z = PROFILE.timezone) => { if (!z || z === 'auto') return {}; try { Intl.DateTimeFormat('en-US', { timeZone: z }); return { timeZone: z }; } catch { return {}; } };
const dateIn = z => new Date().toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long', ...zoneOpt(z) });
function avatarHTML(p = PROFILE) {
  if (p.avatar === 'picture' && p.picture) return `<img src="${esc(p.picture)}" alt="">`;
  const a = AVATARS.find(x => x[0] === p.avatar);
  if (a) return `<span class="av-ico" style="background:linear-gradient(135deg,${a[1]},${a[2]})">${icon(a[0])}</span>`;
  return esc((p.name || 'P').trim().charAt(0).toUpperCase());
}
function renderProfile() {
  $('.user .avatar').innerHTML = avatarHTML();
  $('.user .uname').textContent = PROFILE.name || 'Player';
  clock();
}
async function saveProfile(patch) {
  try { PROFILE = await api('/api/profile', patch); } catch (e) { toast(e.message); throw e; }  // callers only move on (or say "saved") once it's saved
  renderProfile();
}

// Everything that runs on Windows (Steam, Epic, folders, ports) is "PC"; emulated games use their console's name.
// By maker, as the helper lists them (SYSTEM_GROUPS in server.py)
const PLATFORM_ORDER = ['PC', 'PS5', 'PS4', 'PS3', 'PS2', 'PS1', 'PSP', 'PS Vita', 'Switch 2', 'Switch', 'Wii U', 'Wii', 'GameCube', 'N64', '64DD', 'SNES',
  'NES', 'FDS', '3DS', 'DS', 'GBA', 'GBC', 'Game Boy', 'Virtual Boy', 'Pokemon Mini', 'Game & Watch', 'Xbox 360', 'Xbox',
  'Dreamcast', 'Saturn', 'Sega CD', '32X', 'Genesis', 'Master System', 'Game Gear', 'SG-1000', 'NAOMI', 'NAOMI 2', 'Atomiswave', 'Model 3',
  'PC Engine', 'PC Engine CD', 'PC-FX', 'Neo Geo', 'Neo Geo CD', 'Neo Geo Pocket', 'Atari Jaguar', 'Atari Lynx', 'Atari 7800', 'Atari 5200', 'Atari 2600',
  'Atari ST', 'Atari 8-bit', 'WonderSwan', 'Arcade', '3DO', 'CD-i', 'ColecoVision', 'Intellivision', 'Vectrex', 'Odyssey 2', 'N-Gage',
  'DOS', 'ScummVM', 'C64', 'VIC-20', 'Amiga', 'ZX Spectrum', 'Amstrad CPC', 'MSX', 'Apple II', 'Flash'];
const platformOf = g => g.source === 'Emulators' ? (g.system || g.group) : g.source === 'Android' ? 'Android' : 'PC';
// Platform logos (Simple Icons, Wikimedia Commons) for the tab bar; consoles without a free logo of their own use their maker's.
const SGDB_LOGO = 'steamgriddb.png';  // white-on-transparent version of SteamGridDB's logo
const PLATFORM_LOGO = { PC: 'windows11', PS5: 'playstation5', PS4: 'playstation4', PS3: 'playstation3', PS2: 'playstation2', PS1: 'playstation',
  PSP: 'playstationportable', 'PS Vita': 'playstationvita', Switch: 'nintendoswitch', 'Switch 2': 'nintendoswitch', 'Wii U': 'wiiu', Wii: 'wii', GameCube: 'nintendogamecube',
  '3DS': 'nintendo3ds', N64: 'nintendo64', SNES: 'snes', NES: 'nes', DS: 'nintendods', GBA: 'gameboyadvance', GBC: 'gameboycolor', 'Game Boy': 'gameboy',
  'Xbox 360': 'xbox', Xbox: 'xbox', Dreamcast: 'sega', Saturn: 'sega', Genesis: 'sega',
  '64DD': 'nintendo64dd', FDS: 'fds', 'Pokemon Mini': 'nintendo', 'Game & Watch': 'gameandwatch', 'Virtual Boy': 'virtualboy', '32X': 'sega32x',
  'Master System': 'mastersystem', 'Sega CD': 'sega', 'Game Gear': 'gamegear', 'SG-1000': 'sg1000', NAOMI: 'sega', 'NAOMI 2': 'sega', 'Model 3': 'sega',
  'PC Engine': 'pcengine', 'PC Engine CD': 'nec', 'PC-FX': 'pcfx', 'Neo Geo Pocket': 'neogeopocket', 'Atari Jaguar': 'atarijaguar', 'Atari Lynx': 'atarilynx',
  'Atari 7800': 'atari7800', 'Atari 5200': 'atari5200', 'Atari 2600': 'atari2600', 'Atari ST': 'atarist', 'Atari 8-bit': 'atari', WonderSwan: 'wonderswan',
  Atomiswave: 'atomiswave', '3DO': 'threedo', 'CD-i': 'cdi', Intellivision: 'intellivision', 'N-Gage': 'ngage', C64: 'commodore', 'VIC-20': 'commodore',
  Amiga: 'amiga', 'ZX Spectrum': 'zxspectrum', MSX: 'msx', 'Apple II': 'apple2' };
// Logos that spell the system's name (SNES, PS4, Wii...) stand in for the tab's text. Value: the logo's width ÷ height
// (each file's viewBox is trimmed to the artwork, see assets/platforms), so every wordmark gets the same height.
const WORDMARK = { snes: 4.07, nes: 2.71, nintendo64: 6.91, nintendods: 3.09, nintendo3ds: 4.29, gameboyadvance: 11.19, gameboycolor: 2.45,
  gameboy: 5.71, wii: 2.09, wiiu: 3.36, playstation2: 5.8, playstation3: 4.67, playstation4: 4.68, playstation5: 4.66, playstationportable: 5.8,
  playstationvita: 6, nintendo64dd: 3.27, virtualboy: 3.88, sega32x: 3.63, mastersystem: 5.84, pcfx: 2.24, neogeopocket: 4.58, atarijaguar: 2.78,
  atarilynx: 8.39, threedo: 3.46, cdi: 6.52, intellivision: 6.09, sg1000: 6.65, pcengine: 2.03, fds: 3.77, atari2600: 3.01,
  atari7800: 4.44, atari5200: 3.16, atarist: 5.82, ngage: 8.22, msx: 2.87, zxspectrum: 3.44, apple2: 2.77, amiga: 3.14 };
const isWordmark = name => S.tabIcons !== false && PLATFORM_LOGO[name] in WORDMARK;
const ICON_ALL = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6"/></svg>';
function tabIcon(name) {
  if (S.tabIcons === false) return '';
  if (name === 'All Games') return `<span class="tsvg">${ICON_ALL}</span>`;
  if (name === 'Favourites') return `<span class="tsvg">${icon('star')}</span>`;
  const logo = PLATFORM_LOGO[name];
  if (logo in WORDMARK) return `<span class="ticon wm ${logo}" style="--logo:url(assets/platforms/${logo}.svg);--r:${WORDMARK[logo]}"></span>`;
  return logo ? `<span class="ticon ${logo}" style="--logo:url(assets/platforms/${logo}.svg)"></span>` : `<span class="tsvg">${icon('pad')}</span>`;
}
async function loadLibrary() {
  if (API) {
    try { const r = await api('/api/library'); LIB = r.games; libStamp = r.scanned; } catch (e) { toast(e.message); }
  } else {
    LIB = (window.LIBRARY || []).map(g => ({ ...g, group: g.source === 'Ports' ? 'PC Ports' : g.source, installed: true, lastPlayed: Date.now() / 1000 - g.lastPlayed * 86400 }));
  }
  // Tabs are platforms, in console-family order; only platforms with games get a tab.
  // Hidden games stay out of every tab; they're listed under Settings > Hidden games.
  const rank = n => (PLATFORM_ORDER.indexOf(n) + 1) || 99;
  const platforms = [...new Set(LIB.filter(g => !g.hidden).map(platformOf))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  TABS = [{ name: 'All Games', has: g => !g.hidden },
    ...(LIB.some(g => !g.hidden && g.favorite) ? [{ name: 'Favourites', has: g => !g.hidden && g.favorite }] : []),
    ...platforms.map(n => ({ name: n, has: g => !g.hidden && platformOf(g) === n }))];
  const t = TABS.findIndex(x => x.name === S.tabName);
  S.tab = Math.max(0, t);
  if (t < 0) S.tabName = TABS[0].name;  // a tab that went away isn't jumped back to when it returns
  renderTabs(); drawButtons();
  decodeCoversIdle();
}
// The round buttons, always in this order: Library, Emulators, Album, Search, News, Settings
function drawButtons() {
  $('#buttons').innerHTML = BUTTONS.map((b, i) => `<div class="btn${S.zone === 1 && i === S.btn ? ' sel' : ''}" data-i="${i}"><div class="ring">${icon(b.icon)}${b.name === 'News' && NEWS_DOT ? '<i class="btn-dot"></i>' : ''}</div><span>${b.name}</span></div>`).join('');
}
// Every cover decoded in idle time, a few at a time, so a fast scroll through games not seen yet still shows each
// one's art (the browser keeps the bitmaps in its own cache; this only makes sure they're fetched once).
function decodeCoversIdle() {
  if (!S.artBg) return;
  const todo = LIB.filter(g => g.cover && !g.hidden && !BG_READY.has(g.cover)).map(g => g.cover);
  const step = () => { todo.splice(0, 6).forEach(preloadArt); if (todo.length) setTimeout(step, 150); };
  setTimeout(step, 1500);
}
function renderTabs() {
  $('#tabs').innerHTML = TABS.map((t, i) => `<div class="tab${i === S.tab ? ' sel' : ''}" data-i="${i}" title="${esc(t.name)}">${tabIcon(t.name)}${
    isWordmark(t.name) ? '' : `<span>${esc(t.name)}</span>`}</div>`).join('');
  tabsInView(false);
}
// More tabs than the screen is wide (a big library on a 4:3 or portrait screen): the bar scrolls to keep the selected one in the middle
function tabsInView(smooth = true) {
  const bar = $('#tabs'), sel = bar.children[S.tab];
  bar.classList.toggle('overflow', bar.scrollWidth > bar.clientWidth + 1);
  if (sel) bar.scrollTo({ left: sel.offsetLeft - (bar.clientWidth - sel.offsetWidth) / 2, behavior: smooth ? 'smooth' : 'auto' });
}

// ---------- sound ----------
let ac;
function tick(f, dur = .05, vol = .03, type = 'sine') {
  const level = S.uiVolume ?? 60;  // Settings > UI sounds volume: 100 is ten times the old fixed level
  if (!S.sound || !level) return;
  vol = Math.min(.7, vol * level / 10);
  try {
    ac = ac || new AudioContext();
    if (ac.state === 'suspended') ac.resume();
    const o = ac.createOscillator(), g = ac.createGain(), t = ac.currentTime;
    o.type = type; o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g).connect(ac.destination); o.start(t); o.stop(t + dur);
  } catch {}
}

// ---------- wallpaper ----------
function rng(seed) { return () => { seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
// The scene's viewBox has the shape of the 112vw-wide layer, so nothing is stretched: 2700 wide on 21:9, wider on 32:9.
// Below about 1.4:1 it stays 1600 wide and the screen shows its middle (SLICE).
let VW = 2700, SLICE = false;
const VH = 1000, SHORE = 600;
// Midpoint-displacement ridge line: returns [[x,y],...]
function ridge(seed, base, amp, rough) {
  const r = rng(seed), n = 256, ys = new Array(n + 1).fill(base);
  ys[0] = base - r() * amp; ys[n] = base - r() * amp;
  for (let step = n, a = amp; step > 1; step /= 2, a *= rough)
    for (let i = step / 2; i < n; i += step) ys[i] = (ys[i - step / 2] + ys[i + step / 2]) / 2 - (r() - .45) * a;
  return ys.map((y, i) => [i / n * VW, y]);
}
const poly = (pts, fill, extra = '') => `<polygon points="${pts.map(p => p.map(v => v.toFixed(1)).join(',')).join(' ')}" fill="${fill}" ${extra}/>`;
const svgUrl = body => `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${VW} ${VH}" preserveAspectRatio="${SLICE ? 'xMidYMax slice' : 'none'}">${body}</svg>`)}")`;
function pine(x, base, h, fill) {
  let s = '';
  for (let k = 0; k < 4; k++) { const y = base - h * (k / 4), w = h * .32 * (1 - k / 5); s += poly([[x - w, y], [x, y - h * .42], [x + w, y]], fill); }
  return s + `<rect x="${x - h * .02}" y="${base - 4}" width="${h * .04}" height="${h * .08}" fill="${fill}"/>`;
}
function buildWallpaper() {
  const fit = 2700 * innerWidth / innerHeight / (3440 / 1440);
  VW = Math.round(Math.max(1600, fit)); SLICE = fit < 1600;
  const k = VW / 2700;  // places and counts are shares of the 21:9 scene; heights and widths stay in viewBox units
  // Mountains sit high so they show above the cover row, like the mockup.
  // Both ridges dip in the middle so the planet sits in open sky above the title.
  const dip = (pts, d) => pts.map(([x, y]) => [x, y + d * Math.sin(Math.PI * x / VW) ** 2]);
  const haze = dip(ridge(31, 230, 200, .5), 150), far = dip(ridge(11, 320, 180, .52), 110);
  // castle on the far right ridge
  const cx = 2180 * k, cy = far[Math.round(cx / VW * 256)][1];
  let castle = '';
  [[-60, 70, 14], [-30, 120, 18], [0, 180, 22], [34, 110, 16], [64, 80, 12], [96, 60, 10]].forEach(([dx, h, w]) => {
    castle += `<rect x="${cx + dx - w / 2}" y="${cy - h}" width="${w}" height="${h + 20}" fill="#122140"/>` + poly([[cx + dx - w / 2 - 3, cy - h], [cx + dx, cy - h - w * 2.2], [cx + dx + w / 2 + 3, cy - h]], '#122140');
  });
  $('#far').style.backgroundImage = svgUrl(
    `<defs><linearGradient id="h" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a4474"/><stop offset=".5" stop-color="#172a4d"/></linearGradient></defs>` +
    poly([[0, VH], ...haze, [VW, VH]], 'url(#h)') + poly([[0, VH], ...far, [VW, VH]], '#13223f') + castle);

  // mid hills: high at the edges, low in the middle so the lake opens up
  const mid = ridge(23, 500, 150, .55).map(([x, y]) => [x, y + 110 * Math.sin(Math.PI * x / VW)]);
  let lights = '';
  const r = rng(5);
  for (let c = 0; c < 4; c++) {
    const cx2 = (1450 + c * 210 + r() * 60) * k;
    for (let i = 0; i < 9; i++) lights += `<circle cx="${cx2 + (r() - .5) * 120}" cy="${SHORE - 4 - r() * 22}" r="${1.4 + r() * 1.6}" fill="#ffd27a" opacity="${.45 + r() * .55}"/>`;
  }
  $('#mid').style.backgroundImage = svgUrl(poly([[0, VH], ...mid.map(([x, y]) => [x, Math.min(y, SHORE)]), [VW, VH]], '#0d182e') + lights);

  // lake: gradient + faint mirrored ridge
  const mirror = far.map(([x, y]) => [x, SHORE + (SHORE - y) * .55]);
  $('#lake').style.backgroundImage = svgUrl(
    `<defs><linearGradient id="w" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b2d52"/><stop offset="1" stop-color="#060c18"/></linearGradient></defs>` +
    `<rect x="0" y="${SHORE}" width="${VW}" height="${VH - SHORE}" fill="url(#w)"/>` +
    poly([[0, SHORE], ...mirror, [VW, SHORE]], '#0f1b33', 'opacity=".55"'));

  // near: rocky ground + pines at both edges
  const rr = rng(9);
  let near = poly([[0, VH], [0, 760], [180 * k, 780], [420 * k, 820], [620 * k, 900], [760 * k, 1000]], '#050a14')
    + poly([[VW, VH], [VW, 780], [2500 * k, 800], [2300 * k, 860], [2120 * k, 1000]], '#050a14');
  for (let i = 0; i < Math.round(18 * k); i++) near += pine(rr() * 520 * k, 790 + rr() * 60, 140 + rr() * 200, '#050a14');
  for (let i = 0; i < Math.round(16 * k); i++) near += pine(2180 * k + rr() * 520 * k, 800 + rr() * 60, 140 + rr() * 200, '#050a14');
  // a few clumps of small trees on the far shore
  for (let c = 0; c < 6; c++) {
    const x0 = (650 + rr() * 1500) * k, n = 2 + Math.floor(rr() * 5);
    for (let i = 0; i < n; i++) near += pine(x0 + (rr() - .5) * 90, SHORE + 8 + rr() * 6, 16 + rr() * 30, '#0a1426');
  }
  $('#near').style.backgroundImage = svgUrl(near);
}

// Stars and water shimmer on canvases (animated).
const sky = $('#sky'), water = $('#water'), sctx = sky.getContext('2d'), wctx = water.getContext('2d');
let stars = [], ripples = [], meteor = null, nextMeteor = performance.now() + 8000;
// The world is drawn 30 times a second (plenty for twinkling and shimmer), and not at all while a page or menu covers it
// or game art fills the screen. Everything that animates stops while another window (a game) has the focus, and picks
// up again on focus or any input.
const COVERS = ['details-open', 'viewer-open', 'reader-open', 'panel-open', 'news-open', 'album-open', 'search-open', 'ach-open', 'lib-open', 'quick-open', 'hub-open'];
const covered = () => COVERS.some(c => document.body.classList.contains(c));
const W = { raf: 0, last: -1e9 };
let awake = true;
function wake() {
  if (awake) return;
  awake = true;
  if (!W.raf) W.raf = requestAnimationFrame(drawWorld);
  if (F.el && !F.raf) { F.last = 0; F.raf = requestAnimationFrame(floatFrame); }
}
addEventListener('blur', () => { awake = false; });
addEventListener('focus', wake);
['keydown', 'pointerdown', 'pointermove'].forEach(e => addEventListener(e, wake, { passive: true }));
function sizeCanvases() {
  W.last = -1e9;
  const d = devicePixelRatio || 1;
  for (const c of [sky, water]) { c.width = innerWidth * d; c.height = innerHeight * d; c.getContext('2d').setTransform(d, 0, 0, d, 0, 0); }
  const r = rng(3);
  stars = Array.from({ length: Math.round(innerWidth * innerHeight / 9000) }, () => ({ x: r() * innerWidth, y: r() * innerHeight * .4, s: r() * 1.3 + .2, p: r() * 6.3, f: .6 + r() * 1.6 }));
  // as many ripples across the lake, and as long, relative to the screen as on 21:9 at 1440 (140 of 10-70px)
  const k = innerHeight / 1440;
  ripples = Array.from({ length: Math.round(140 * innerWidth / innerHeight * 1440 / 3440) }, () => ({ x: r() * innerWidth, y: innerHeight * (.61 + r() * .28), w: (10 + r() * 60) * k, p: r() * 6.3, f: .5 + r() * 1.2 }));
}
function drawWorld(t) {
  W.raf = awake ? requestAnimationFrame(drawWorld) : 0;
  if (t - W.last < 28 || S.artBg || covered()) return;
  W.last = t;
  const s = t / 1000;
  sctx.clearRect(0, 0, innerWidth, innerHeight * .41 + 2);  // stars and meteors stay in the top 40%
  for (const st of stars) {
    sctx.globalAlpha = .25 + .75 * (.5 + .5 * Math.sin(s * st.f + st.p)) * (1 - st.y / (innerHeight * .62));
    sctx.fillStyle = '#dbe8ff'; sctx.fillRect(st.x, st.y, st.s, st.s);
  }
  if (!meteor && t > nextMeteor) meteor = { x: innerWidth * (.2 + Math.random() * .6), y: innerHeight * .05, t0: t };
  if (meteor) {
    const k = (t - meteor.t0) / 900;
    if (k > 1) { meteor = null; nextMeteor = t + 9000 + Math.random() * 14000; }
    else {
      const x = meteor.x + k * innerWidth * .12, y = meteor.y + k * innerHeight * .12, L = 120 * innerHeight / 1440;  // trail follows the screen height
      const g = sctx.createLinearGradient(x, y, x - L, y - L);
      g.addColorStop(0, 'rgba(220,240,255,.9)'); g.addColorStop(1, 'rgba(220,240,255,0)');
      sctx.globalAlpha = 1 - k; sctx.strokeStyle = g; sctx.lineWidth = Math.max(1, 1.5 * innerHeight / 1440);
      sctx.beginPath(); sctx.moveTo(x, y); sctx.lineTo(x - L, y - L); sctx.stroke();
    }
  }
  sctx.globalAlpha = 1;
  wctx.clearRect(0, innerHeight * .61 - 2, innerWidth, innerHeight * .28 + 4);  // ripples sit between 61% and 89%
  wctx.strokeStyle = '#9cc4ff'; wctx.lineWidth = 1;
  for (const rp of ripples) {
    wctx.globalAlpha = .12 * (.5 + .5 * Math.sin(s * rp.f + rp.p));
    const dx = Math.sin(s * .3 + rp.p) * 6;
    wctx.beginPath(); wctx.moveTo(rp.x + dx, rp.y); wctx.lineTo(rp.x + dx + rp.w, rp.y); wctx.stroke();
  }
  wctx.globalAlpha = 1;
}
function parallax() {
  const p = S.list.length > 1 ? idx() / (S.list.length - 1) - .5 : 0;
  [['#planet', 3], ['#far', 4], ['#mid', 7], ['#lake', 7], ['#near', 11]].forEach(([q, range]) => $(q).style.transform = `translateX(${-p * range}vw)`);
  const g = game();
  $('#tint').style.background = g ? `radial-gradient(ellipse 80% 70% at 50% 40%, ${colorOf(g)}, transparent 75%)` : 'none';
}

// ---------- rendering ----------
const strip = $('#strip');
// Most recently played first, then installed before not-installed, then A-Z. A game added in the last three days and not
// played since counts as played when it arrived, so new games show at the front.
const NEW_FOR = 3 * 86400;
const recency = g => Math.max(g.lastPlayed || 0, g.added && Date.now() / 1000 - g.added < NEW_FOR ? g.added : 0);
const byRecent = (a, b) => recency(b) - recency(a) || (b.installed !== false) - (a.installed !== false) || a.title.localeCompare(b.title);
// ---------- games that are already running ----------
let RUN = new Set();
async function watchRunning() {
  let r;
  try { r = await api('/api/running'); } catch { return; }
  const next = new Set(r.games), same = next.size === RUN.size && [...next].every(x => RUN.has(x));
  if (same) return;
  RUN = next;
  showRunning();
  if (LIB.length) buildRow(false);
  if (D.open) renderActions();
  if (SP.open) renderSys();
}
function showRunning() {
  const first = LIB.find(g => RUN.has(g.id));
  $('#running').textContent = first ? `Running: ${first.title}${RUN.size > 1 ? ` +${RUN.size - 1}` : ''}` : '';
}
async function resumeGame(g) {
  try { await api('/api/running/resume', { id: g.id }); } catch (e) { toast(e.message); }
}
// Close game ends the game without saving, so like Restart and Shut down it asks for a second A
let closeAsk = null, closeAskT;
function askClose(g) {
  if (closeAsk === g.id) { closeAsk = null; return closeRunning(g); }
  closeAsk = g.id; clearTimeout(closeAskT);
  closeAskT = setTimeout(() => { closeAsk = null; if (D.open) renderActions(); if (Q.open) quickRelabel(); }, 4000);
  if (D.open) renderActions();
  if (Q.open) quickRelabel();
  toast('Press A again to close it. Unsaved progress is lost.', 4000);
}
async function closeRunning(g) {
  try { await api('/api/running/close', { id: g.id }); RUN.delete(g.id); showRunning(); toast(`${g.title} closed`); watchRunning(); if (LIB.length) buildRow(false); if (D.open) renderActions(); }
  catch (e) { toast(e.message); }
}
// Animated covers (SteamGridDB) all play, all the time: on the home row, and on the Library or search page while it's open
// (watchAnims; a closed page is hidden, not gone, so its covers would keep playing unseen). The helper serves light copies
// of the animations (server.light_anim): the originals can be 50 MB each. g.cover stays the still first frame, shown where
// only a still will do. On the home row the animation is a layer above the cover, outside .art, so the reflection mirrors
// the still: a mirrored animation had to be redrawn every frame, lagged behind and glitched.
const ANIM_ROOTS = new Map();  // a row or grid -> whether its page is open
function watchAnims(root, live) {
  if (!root) return;
  ANIM_ROOTS.set(root, live);
  animPlan(root);
}
function animPlan(root) {
  const live = ANIM_ROOTS.get(root);
  root.querySelectorAll('img[data-anim]').forEach(im => {
    const want = live ? im.dataset.anim : im.dataset.still || '';
    if (!im.dataset.anim || (im.getAttribute('src') || '') === want) return;  // (unchanged: a playing one isn't restarted)
    if (want) im.src = want; else im.removeAttribute('src');
  });
}
function tileHTML(g, i, animate) {
  // The title card underneath shows whenever a cover is missing or fails to load.
  return `<div class="tile${animate ? ' in' : ''}${g.installed === false ? ' cloud' : ''}" data-i="${i}" style="animation-delay:${Math.min(Math.abs(i - idx()), 12) * 45}ms;--c:${colorOf(g)}">
    <div class="art"><div class="ph"><span>${esc(g.title)}</span></div>
    ${g.cover ? `<img src="${esc(g.cover)}" alt="" draggable="false" loading="lazy" onerror="coverRetry(this)">` : ''}</div>
    ${g.coverAnim ? `<img class="anim-cover" data-anim="${esc(g.coverAnim)}" alt="" draggable="false" onerror="this.remove()">` : ''}
    ${g.favorite ? `<i class="fav">${icon('star')}</i>` : ''}${RUN.has(g.id) ? '<i class="runtag">Running</i>' : ''}<div class="frame"></div></div>`;
}
let rowKey = '';
function buildRow(animate) {
  S.list = LIB.filter(TABS[S.tab].has).sort(byRecent);
  select(idx());
  // A refresh that changed nothing (back from a game, a rescan) keeps the tiles, so no cover reloads or decodes again
  const key = S.tab + '\n' + S.list.map(g => [g.id, g.title, g.cover, g.installed, g.color, g.favorite, RUN.has(g.id)].join('\t')).join('\n');
  if (animate || key !== rowKey) {
    strip.innerHTML = S.list.map((g, i) => tileHTML(g, i, animate)).join('')
      || `<div class="empty"><b>No games ${API ? 'yet' : 'here yet'}</b>${API ? '<span>Open Settings to add your libraries and accounts.</span>' : ''}</div>`;
    STRIP.size = '';
  }
  rowKey = key;
  placeStrip(false);
  update();
}
// The row's entrance animation plays once. If a tile kept its "in" class, the selected tile's "animation: none" switching
// off as you moved on restarted it, so the tile you just left vanished and rose back in.
strip.addEventListener('animationend', e => { if (e.animationName === 'tileIn') e.target.classList.remove('in'); });
// Tile size and gap, read once per window size: reading them on every move forced a layout right after the class changes
const STRIP = { size: '', w: 0, gap: 0 };
function placeStrip(smooth = true) {
  const t = strip.querySelector('.tile');
  if (!t) return;
  if (STRIP.size !== innerWidth + 'x' + innerHeight || !STRIP.w) {
    STRIP.w = t.offsetWidth; STRIP.gap = parseFloat(getComputedStyle(strip).columnGap) || 0; STRIP.size = innerWidth + 'x' + innerHeight;
  }
  const { w, gap } = STRIP;
  const x = innerWidth / 2 - (idx() * (w + gap) + w / 2);
  if (!smooth) { strip.style.transition = 'none'; strip.style.transform = `translateX(${x}px)`; void strip.offsetWidth; strip.style.transition = ''; }
  else strip.style.transform = `translateX(${x}px)`;
}
let lastTitle = null;
function setTitle(text) {
  if (text === lastTitle) return;
  lastTitle = text;
  const box = $('#title');
  box.querySelectorAll('span').forEach(o => { o.classList.add('leave'); setTimeout(() => o.remove(), 450); });
  const n = document.createElement('span');
  n.className = 'enter'; n.textContent = text;
  box.appendChild(n);
  raf2(() => n.classList.remove('enter'));
}
function update() {
  document.body.className = document.body.className.replace(/zone-\d/g, '').trim() + ` zone-${S.zone}`;
  [...strip.children].forEach((e, i) => {
    e.classList.toggle('sel', i === idx());
    const nearby = Math.abs(i - idx()) <= 10;
    e.classList.toggle('nearby', nearby);
    const image = nearby && e.querySelector('img'), pri = i === idx() ? 'high' : 'auto';
    if (image && image.loading !== 'eager') { image.loading = 'eager'; image.decoding = 'async'; }
    if (image && image.fetchPriority !== pri) image.fetchPriority = pri;
  });
  placeStrip();
  watchAnims(strip, true);
  [...$('#buttons').children].forEach((e, i) => e.classList.toggle('sel', S.zone === 1 && i === S.btn));
  [...$('#tabs').children].forEach((e, i) => e.classList.toggle('sel', i === S.tab));
  const g = game();
  setTitle(S.zone === 1 ? BUTTONS[S.btn].name : g ? g.title : LIB.length ? TABS[S.tab].name : 'Welcome');
  parallax();
  if (g && g.id !== lastSel) {  // Big Picture-style: the new cover pops and catches the light, the background follows
    lastSel = g.id;
    const t = strip.children[idx()];
    if (t) { t.classList.remove('pop', 'in'); void t.offsetWidth; t.classList.add('pop'); floatTo(t, S.dir); }
    scheduleBackground(g);
    schedulePrefetch(g);
  } else if (g && F.el !== strip.children[idx()]) floatTo(strip.children[idx()], 0);  // row was rebuilt (tab switch)
}

// ---------- floaty selected cover ----------
// Floaty tiles applied to the selected cover: it rises, sways and bobs,
// leans the way you moved, and a sheen drifts over it. Every value is a damped spring (same stiffness and damping as
// the dashboard), so nothing snaps and it settles with a small overshoot. A mouse over it steers it like the dashboard.
const FLOAT = { stiff: 150, damp: 13, lean: 3, drift: 6, lift: 9, bob: 3, bobS: 3 };
const F = { el: null, s: null, raf: 0, last: 0, pointer: null, mv: { x: 0, y: 0 } };
const spr = (v = 0) => ({ v, vel: 0, to: v });
const calmMotion = matchMedia('(prefers-reduced-motion: reduce)');
function stepSpring(sp, dt, k = FLOAT.stiff, d = FLOAT.damp) {
  const a = k * (sp.to - sp.v) - d * sp.vel; sp.vel += a * dt; sp.v += sp.vel * dt;
  if (!Number.isFinite(sp.v) || !Number.isFinite(sp.vel)) { sp.v = sp.to; sp.vel = 0; }  // never let a bad value stick
}
const FLOAT_VARS = ['--fx', '--fy', '--rx', '--ry', '--sc', '--px', '--py', '--mx', '--my', '--glare'];
function clearFloat(el) { FLOAT_VARS.forEach(v => el.style.removeProperty(v)); el.removeAttribute('data-float'); }
function floatTo(el, dir) {
  if (!el || calmMotion.matches) return;
  if (F.el !== el) {
    if (F.el) clearFloat(F.el);
    // starts at the unselected size so it grows into place on the spring
    F.el = el; F.s = { x: spr(), y: spr(), rx: spr(), ry: spr(), sc: spr(1 / 1.1), px: spr(), py: spr(), mx: spr(50), my: spr(50), glare: spr() };
    el.setAttribute('data-float', '');
  }
  dir = Number(dir) || 0;   // no direction yet at startup
  F.s.ry.vel += dir * 75;   // a push the way you moved: it leans, then springs back
  F.s.x.vel += dir * 220;
  if (!F.raf) F.raf = requestAnimationFrame(floatFrame);
}
function floatFrame(now) {
  F.raf = 0;
  if (!F.el || !F.el.isConnected) { F.el = null; return; }
  if (!awake) return;  // wake() starts it again
  if (covered()) { F.last = now; F.raf = requestAnimationFrame(floatFrame); return; }
  const dt = Math.min(0.05, (now - (F.last || now)) / 1000), t = now / 1000, k = innerHeight / 1440, s = F.s;
  F.last = now;
  const active = S.zone === 0;
  // A slow, wandering "pointer" so the held cover sways; a real mouse over it takes over.
  let px = Math.sin(t * .55) * .5, py = Math.sin(t * .41 + 1) * .4;
  // Steering, strongest first: a mouse right over the tile, the right stick, then mouse motion anywhere
  // (Steam's desktop mode turns the right stick into mouse movement). Let go and it eases back.
  const gp = [...(navigator.getGamepads?.() || [])].find(Boolean);
  const sx = gp?.axes[2] || 0, sy = gp?.axes[3] || 0;
  F.mv.x *= Math.exp(-dt * 2.5); F.mv.y *= Math.exp(-dt * 2.5);
  if (F.pointer && now - F.pointer.t < 2500) {
    const r = F.el.getBoundingClientRect();
    px = clamp((F.pointer.x - r.left) / r.width, 0, 1) * 2 - 1;
    py = clamp((F.pointer.y - r.top) / r.height, 0, 1) * 2 - 1;
  } else if (Math.hypot(sx, sy) > 0.15) {
    px = clamp(sx, -1, 1); py = clamp(sy, -1, 1);
  } else if (Math.hypot(F.mv.x, F.mv.y) > 0.03) {
    px = F.mv.x; py = F.mv.y;
  }
  if (!active) px = py = 0;
  const bob = active ? Math.sin(t * 2 * Math.PI / FLOAT.bobS) * FLOAT.bob * k : 0;
  s.px.to = px; s.py.to = py;
  s.x.to = px * FLOAT.drift * k;
  s.y.to = (active ? -FLOAT.lift * k : 0) + py * FLOAT.drift * k * .6 + bob;
  s.rx.to = -py * FLOAT.lean; s.ry.to = px * FLOAT.lean;
  s.sc.to = active ? 1 : 1.04 / 1.1;
  s.glare.to = active ? 1 : 0;
  s.mx.to = 50 + px * 40; s.my.to = 50 + py * 40;
  for (const [key, sp] of Object.entries(s)) key === 'mx' || key === 'my' ? stepSpring(sp, dt, 90, 16) : stepSpring(sp, dt);  // the sheen trails a little
  const st = F.el.style;
  st.setProperty('--fx', s.x.v.toFixed(2) + 'px'); st.setProperty('--fy', s.y.v.toFixed(2) + 'px');
  st.setProperty('--rx', s.rx.v.toFixed(2) + 'deg'); st.setProperty('--ry', s.ry.v.toFixed(2) + 'deg');
  st.setProperty('--sc', s.sc.v.toFixed(4)); st.setProperty('--px', s.px.v.toFixed(3)); st.setProperty('--py', s.py.v.toFixed(3));
  st.setProperty('--mx', s.mx.v.toFixed(1) + '%'); st.setProperty('--my', s.my.v.toFixed(1) + '%');
  st.setProperty('--glare', clamp(s.glare.v, 0, 1).toFixed(3));
  F.raf = requestAnimationFrame(floatFrame);
}
strip.addEventListener('pointermove', e => { if (e.pointerType !== 'touch') F.pointer = { x: e.clientX, y: e.clientY, t: performance.now() }; }, { passive: true });
// Mouse motion anywhere acts like a stick: it tips the tile in the direction moved, then eases back.
addEventListener('pointermove', e => {
  if (e.pointerType === 'touch' || e.target.closest?.('#strip')) return;
  F.mv.x = clamp(F.mv.x + (e.movementX || 0) / 90, -1, 1);
  F.mv.y = clamp(F.mv.y + (e.movementY || 0) / 90, -1, 1);
}, { passive: true });

// ---------- game art background ----------
// With "Home background: Game art", the selected game's wide art fills the screen and follows as you move. The art
// already decoded (the games either side are fetched ahead) swaps at once, so every game you pass shows; a game whose
// hero isn't known yet shows its cover (blurred) straight away and gets the hero when the helper has looked it up.
let lastSel = null, bgTimer = null, bgShown = null;
const HERO_CACHE = {}, HERO_DONE = {};  // id -> promise of the hero URL, and the URL once known ('' = none)
// An animated background comes as its still first frame (hero) plus the animation (heroAnim, kept in HERO_ANIM): the row
// preloads and shows the still, and the animation starts once the selection rests on the game (see animateBackground).
const HERO_ANIM = {};
const heroOf = g => HERO_CACHE[g.id] ??= (API ? api('/api/hero?id=' + encodeURIComponent(g.id)).then(r => { if (r.heroAnim) HERO_ANIM[g.id] = r.heroAnim; else delete HERO_ANIM[g.id]; return r.hero; }).catch(() => '') : Promise.resolve(''))
  .then(h => (HERO_DONE[g.id] = h || ''));
let animTimer = 0;
function animateBackground(g) {
  clearTimeout(animTimer);
  if (!g || !HERO_ANIM[g.id]) return;
  animTimer = setTimeout(() => {
    if (game()?.id !== g.id || !S.artBg) return;
    const url = HERO_ANIM[g.id], img = new Image();  // loaded before it fades in (never kept with the preloads: too big)
    img.src = url;
    img.decode().catch(() => {}).then(() => { if (game()?.id === g.id && S.artBg && img.naturalWidth) showBackground(g, url, true); });
  }, 500);
}
function applyBackgroundMode() {
  document.body.classList.toggle('art-bg', !!S.artBg);
  bgShown = null;
  if (S.artBg && game()) scheduleBackground(game(), 0); prefetchBackgrounds(); decodeCoversIdle();
}
// Images fetched and decoded ahead of time, so moving swaps at once.
const BG_READY = new Map(), BG_DONE = new Set();
function preloadArt(url) {
  if (!url) return Promise.resolve();
  if (!BG_READY.has(url)) {
    const img = new Image(); img.src = url;
    BG_READY.set(url, img.decode().then(() => BG_DONE.add(url)).catch(() => {}));
    if (BG_READY.size > 400) { const old = BG_READY.keys().next().value; BG_READY.delete(old); BG_DONE.delete(old); }
  }
  return BG_READY.get(url);
}
function prefetchBackgrounds() {
  if (!S.artBg) return;
  const i = idx();
  for (let d = 1; d <= 12; d++) for (const n of [S.list[i + d], S.list[i - d]]) {
    if (!n) continue;
    preloadArt(n.cover);  // covers are small: a dozen each side
    if (d <= 6) heroOf(n).then(h => preloadArt(h || n.cover));  // the wide heroes, six each side
  }
}
// One new layer crossfades over the one before it; never more than two alive, so a fast scroll can't pile them up.
function showBackground(g, url, hero) {
  if (url !== HERO_ANIM[g?.id]) animateBackground(g);  // a still on screen: its animation follows once the selection rests
  if (!url || bgShown === url) return;
  bgShown = url;
  const box = $('#gamebg'), layer = document.createElement('div');
  layer.className = 'gb' + (hero ? '' : ' soft');  // a portrait cover is blurred so it doesn't look stretched
  layer.style.backgroundImage = `url("${url}")`;
  const old = [...box.children];
  old.slice(0, -1).forEach(o => o.remove());
  box.appendChild(layer);
  setTimeout(() => { if (layer.isConnected && layer !== box.lastChild) layer.remove(); old.forEach(o => o.remove()); }, 600);
}
function scheduleBackground(g, delay = 120) {
  if (!S.artBg) return;
  clearTimeout(bgTimer);
  preloadArt(g.cover); prefetchBackgrounds();  // start fetching now; a slow hero lookup must not hold the neighbours up
  const hero = HERO_DONE[g.id];
  const best = hero === undefined ? null : hero || g.cover;
  if (best && BG_DONE.has(best)) { showBackground(g, best, !!hero); return; }  // ready: at once
  if (g.cover && BG_DONE.has(g.cover)) showBackground(g, g.cover, false);  // the cover now, the hero when it comes
  bgTimer = setTimeout(async () => {
    const h = await heroOf(g);
    if (game()?.id !== g.id) return;
    const url = h || g.cover;
    if (!url) return;
    if (!BG_DONE.has(g.cover) && g.cover && url !== g.cover) { preloadArt(g.cover).then(() => { if (game()?.id === g.id && bgShown !== url) showBackground(g, g.cover, false); }); }
    await preloadArt(url);
    if (game()?.id !== g.id) return;
    showBackground(g, url, !!h);
    prefetchBackgrounds();
  }, delay);
}

// ---------- actions ----------
function move(dx, dy) {
  if (S.busy) return;
  if (dy) {
    const z = clamp(S.zone + dy, 0, 2);
    if (z === S.zone) return;
    S.zone = z; tick(420, .06); update(); return;
  }
  if (S.zone === 0) {
    const n = clamp(idx() + dx, 0, S.list.length - 1);
    if (n === idx() || !S.list.length) return;
    select(n); tick(760, .035, .022);
  } else if (S.zone === 1) {
    const n = clamp(S.btn + dx, 0, BUTTONS.length - 1);
    if (n === S.btn) return;
    S.btn = n; tick(640, .04);
  } else return setTab(S.tab + dx);
  save(); update();
}
// ---------- startup intro: once each time the frontend opens, never on a page refresh ----------
// The intro (opening) and the outro (closing), each on or off in Settings › General. The outro follows the old shared
// switch until it's set on its own.
function introOn() { try { return localStorage.getItem('fe-intro') !== 'off'; } catch { return true; } }
function outroEnabled() { try { return (localStorage.getItem('fe-outro') ?? localStorage.getItem('fe-intro')) !== 'off'; } catch { return true; } }
function runIntro() {
  const el = $('#intro');
  let seen = false;
  try { seen = !!sessionStorage.getItem('fe-intro-seen'); sessionStorage.setItem('fe-intro-seen', '1'); } catch {}
  if (seen || !API || !introOn()) return el.remove();
  INTRO.open = true;
  el.addEventListener('pointerdown', () => endIntro(true), { once: true });  // a tap or click skips it, like any button
  api('/api/introsound', { play: true }).catch(() => {});
  if (!introWave()) el.classList.add('flat');  // no WebGL: a still image of the wave simply fades in
  INTRO.timer = setTimeout(endIntro, 3700);
}
// Drawn live, after the look of the Kling test: a flat line of light swells into a wave of hairline contours that
// pinch together at drifting nodes around a soft icy core. Being drawn, it stays sharp at any resolution.
function introWave(c = $('#introwave'), clock = s => s, alive = () => !!$('#intro')) {  // clock: the wave's time from seconds shown (the outro runs it backwards)
  const dpr = devicePixelRatio || 1;
  c.width = Math.round(innerWidth * dpr); c.height = Math.round(innerHeight * dpr);  // device pixels, so the hairlines stay sharp when Windows scales the display
  const gl = c.getContext('webgl', { antialias: false, alpha: false });
  if (!gl) return false;
  const shader = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const prog = gl.createProgram();
  gl.attachShader(prog, shader(gl.VERTEX_SHADER, 'attribute vec2 p; varying vec2 v; void main() { v = p * .5 + .5; gl_Position = vec4(p, 0., 1.); }'));
  gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, `precision highp float; varying vec2 v; uniform float t, aspect, px, k;
    float grain(vec2 q) { return fract(sin(dot(q, vec2(12.9898, 78.233))) * 43758.5453); }
    void main() {
      float x = (v.x - .5) * aspect, y = v.y - .5, xk = x * k;  // xk: screens narrower than 16:9 still show as many crests
      float swell = smoothstep(.42, 1.75, t), A = .17 * swell * swell * (3. - 2. * swell) * (1. + .1 * smoothstep(3.2, 3.8, t));
      float line = 0., a = 0.;
      for (int i = 0; i < 36; i++) {
        float w = -1. + 2. * float(i) / 35.;            // each contour is the same wave at a different height
        a = sin(xk * 4.3 - t * 1.05) + .4 * sin(xk * 2.3 + t * .55 + 1.2);
        float b = .3 * sin(xk * 2.1 + t * .62 + w * 1.15);
        float d = abs(y - A * (w * a + b));
        line += (.35 + .65 * abs(w)) * px * 1.5 / (d + px * 1.5) * exp(-d * 90.);
      }
      float core = A * (.26 * a + .3 * sin(xk * 1.5 + t * .4));
      float d = abs(y - core);
      float body = abs(A * a) + .004, wide = exp(-d * d / (.5 * body * body + .0005)), tight = exp(-d * d / .00004);
      float flow = .6 + .4 * sin(xk * 2.3 - t * 1.4);      // brightness runs along the wave
      float band = exp(-pow((x - (t - 1.6) * 1.05) * 2.4, 2.));
      vec3 c = vec3(.4, .64, .95) * line * .34 + vec3(.28, .52, .9) * wide * .62 * flow + vec3(.86, .95, 1.) * tight * flow * .75;
      c *= 1. + 1.1 * band;
      float open = (t - .36) * aspect * .62;               // opens outward from the centre
      c *= smoothstep(open, open - .7 * min(1., aspect * 9. / 16.), abs(x)) * smoothstep(.36, 1., t);
      c = 1. - exp(-c * 1.5);
      c += (grain(gl_FragCoord.xy + t) - .5) / 255.;       // stops banding in the soft glow
      gl_FragColor = vec4(c, 1.);
    }`));
  gl.bindAttribLocation(prog, 0, 'p');
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false;
  gl.useProgram(prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.viewport(0, 0, c.width, c.height);
  gl.uniform1f(gl.getUniformLocation(prog, 'aspect'), c.width / c.height);
  gl.uniform1f(gl.getUniformLocation(prog, 'px'), 1 / c.height);
  gl.uniform1f(gl.getUniformLocation(prog, 'k'), Math.max(1, 16 / 9 / (c.width / c.height)));
  const uT = gl.getUniformLocation(prog, 't'), t0 = performance.now();
  const frame = now => {
    if (!alive()) return;
    gl.uniform1f(uT, clock((now - t0) / 1000));
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  return true;
}
function endIntro(skipped) {
  if (!INTRO.open) return;
  INTRO.open = false; clearTimeout(INTRO.timer);
  if (skipped === true) api('/api/introsound', { play: false }).catch(() => {});
  $('#intro').classList.add('out');
  setTimeout(() => $('#intro')?.remove(), 700);
}
let tabsPeekT;  // the platform row only shows while it's being used
function setTab(n) {
  n = clamp(n, 0, TABS.length - 1);
  if (n === S.tab || S.busy) return;
  S.tab = n; S.tabName = TABS[n].name; tick(560, .07); save();
  peekTabs();
  [...strip.children].forEach(t => t.classList.add('out'));
  setTimeout(() => buildRow(true), 180);
  [...$('#tabs').children].forEach((e, i) => e.classList.toggle('sel', i === S.tab));
  tabsInView();
}
function back() { if (S.zone !== 0) { S.zone = 0; tick(420, .06); update(); } else openSys(); }
// B on the home screen: a small menu to leave the frontend
// Quick Access's last row: left and right pick one, A does it. Restart and Shut down ask for a second A.
const POWER = [{ id: 'sleep', ic: 'moon', label: 'Sleep', done: 'Going to sleep' }, { id: 'restart', ic: 'reset', label: 'Restart', confirm: true },
  { id: 'shutdown', ic: 'power', label: 'Shut down', confirm: true }, { id: 'exit', ic: 'exit', label: 'Exit' }];
const powerChoices = () => API && !ON_ANDROID ? POWER : POWER.filter(p => p.id === 'exit');  // Android apps can't sleep or restart the device
function powerPick(p) {
  if (p.id === 'exit') return quitFrontend();
  if (p.confirm && SP.confirm !== p.id) {
    SP.confirm = p.id; renderSys();
    clearTimeout(SP.confirmT); SP.confirmT = setTimeout(() => { SP.confirm = null; if (SP.open) renderSys(); }, 4000);
    return;
  }
  closeSys(); powerAction(p.id, p.done || `${p.label} in a few seconds`);
}
async function powerAction(action, message) {
  try { await api('/api/system', { action }); toast(message, 4000); } catch (e) { toast(e.message); }
}
// Beside the choices: the time, the song playing, friends online and the controller's battery. Anything missing is left out.
const infoRow = (label, value, sub) => `<div class="si"><small>${esc(label)}</small><div>${esc(value)}</div>${sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
// The side menu with no game cover beside it
function sysMenu(title, items) {
  $('#quick .sys-info').innerHTML = ''; $('#quick .sys-time').innerHTML = '';
  openQuick({ title, cover: 'icon.png', group: '' });
  Q.items = items;
  $('#quick .q-meta').textContent = '';
  $('#quick').classList.add('sys');  // no game here: no cover, just the choices
  $('#quick .q-list').innerHTML = Q.items.map((it, j) => `<div class="q-item${it.warn ? ' warn' : ''}" data-i="${j}" style="animation-delay:${60 + j * 35}ms">${it.ic}<span>${esc(it.label)}</span></div>`).join('');
  quickFocus();
}
function quitFrontend() {
  playOutro(() => {
    if (window.pywebview?.api?.quit) window.pywebview.api.quit();
    else if (window.AndroidApp) window.AndroidApp.quit();
    else window.close();
  });
}
// The closing animation: the screen goes dark and the intro's wave plays backwards, folding into a line of light that
// closes to the middle, with the closing sound; then the window goes. Off in Settings › General › Outro.
let outroOn = false;
function playOutro(done = () => {}) {
  if (outroOn) return;
  if (!API || !outroEnabled()) return done();
  outroOn = true;
  const el = document.createElement('div');
  el.id = 'outro'; el.innerHTML = '<canvas></canvas>';
  document.body.appendChild(el);
  api('/api/introsound', { play: true, outro: true }).catch(() => {});
  const SHOWN = 1.5, FROM = 2.9;  // the wave from fully open back to nothing, in a second and a half
  const drawn = introWave(el.querySelector('canvas'), s => Math.max(0, FROM * (1 - s / SHOWN)), () => el.isConnected);
  if (!drawn) el.classList.add('flat');  // no WebGL: the still wave fades
  raf2(() => el.classList.add('on'));
  setTimeout(done, SHOWN * 1000 + 250);
}
window.playOutro = playOutro;  // the tray's Exit asks for it too
let toastT;
function toast(msg, ms = 2200) { const t = $('#toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), ms); }
async function activate() {
  if (S.busy) return;
  if (S.zone === 2) { S.zone = 0; return update(); }
  if (S.zone === 1) {
    const b = BUTTONS[S.btn];
    tick(880, .08);
    if (b.run) b.run();  // the highlight stays on the button, so B comes back to it
    else toast(`${b.name}: coming soon`);
    return;
  }
  const g = game();
  if (!g) return openPanel('libraries');
  openDetails(g);
}
// Unpacking happens after the launch call has answered, so a failure is only known by asking until it's finished.
async function watchUnpack(g) {
  for (;;) {
    await new Promise(res => setTimeout(res, 1500));
    let r;
    try { r = await api('/api/unpack?id=' + encodeURIComponent(g.id)); } catch { return; }
    if (r.error) return toast(`${g.title} couldn't start: ${r.error}`, Math.max(5000, r.error.length * 70));
    if (!r.unpacking) return void (g.lastPlayed = Date.now() / 1000);  // played once it's unpacked and started
  }
}
// The launch screen covers everything while it's up: B takes it down (and tells the helper to stop holding it on top)
let LAUNCH = null;
function cancelLaunch() {
  const l = LAUNCH;
  if (!l) return;
  if (API) api('/api/launching/cancel', { id: l.id }).catch(() => {});
  tick(420, .06); l.done();
}
// The program a console's games start in, as the emulator pages name it
async function emulatorName(g) {
  const d = P.data || await api('/api/settings').catch(() => null), p = d?.platforms?.find(x => x.name === g.system);
  if (!p?.emulator) return 'The emulator';
  return p.recommended && p.emulator.toLowerCase().includes(p.recommended.toLowerCase().split(' ')[0]) ? p.recommended : p.emulator;
}
// A console with no emulator yet: its page in Settings › Systems, where one is installed or chosen
async function openEmulatorFor(g) {
  await openPanel('systems');
  if (P.data?.platforms?.some(x => x.name === g.system)) { P.system = g.system; P.side = false; setView('system'); }
}
async function launchGame(g) {
  if (S.busy || !g) return;
  if (RUN.has(g.id)) return resumeGame(g);  // never a second copy
  // The game's own logo alone in the middle, over its art dimmed behind; its name in large type until (or unless) a
  // logo is found. Everything already looked up for the details screen is reused, so this is usually instant.
  const L = $('#launch'), bg = L.querySelector('.lbg'), logo = L.querySelector('.llogo'), title = L.querySelector('.lt');
  bg.style.cssText = g.cover ? `background-image:url("${g.cover}")` : `background:${colorOf(g)}`;
  L.classList.remove('has-logo', 'wide');
  logo.removeAttribute('src');
  title.textContent = g.title;
  L.querySelector('.ls').textContent = g.installed === false ? 'Opening install' : 'Launching';
  L.querySelector('.ln').textContent = API ? '' : "Preview: games don't launch yet";
  heroOf(g).then(h => { if (h && L.classList.contains('on')) { bg.style.cssText = `background-image:url("${h}")`; L.classList.add('wide'); } });
  detailsFor(g)?.info.then(d => {
    if (!d?.logo || !L.classList.contains('on')) return;
    logo.onload = () => L.classList.add('has-logo');
    logo.src = d.logo;
  }).catch(() => {});
  S.busy = true; tick(440, .25, .05, 'triangle'); setTimeout(() => tick(880, .3, .04, 'triangle'), 120);
  L.classList.add('on');
  let over = false;
  const done = () => { if (over) return; over = true; L.classList.remove('on'); S.busy = false; if (LAUNCH?.id === g.id) LAUNCH = null; };
  LAUNCH = { id: g.id, done };
  if (API) {
    try {
      const r = await api('/api/launch', { id: g.id });
      if (r.unpacking) {  // a zipped game the emulator can't open: the helper unpacks it once, then starts it
        L.querySelector('.ls').textContent = 'Unpacking';
        watchUnpack(g);
      } else g.lastPlayed = Date.now() / 1000;
      if (D.open && D.game?.id === g.id) renderStats();
    }
    catch (e) {
      done(); toast(e.message, Math.max(3500, e.message.length * 55));
      if (g.source === 'Emulators' && /Settings › Systems/.test(e.message)) openEmulatorFor(g);
      return;
    }
    // Stays up until the game fills the screen, covering any emulator or launcher windows on the way
    const start = performance.now();
    for (;;) {
      await new Promise(res => setTimeout(res, 300));
      if (over) return;  // B took it down
      let r;
      try { r = await api('/api/launching?id=' + encodeURIComponent(g.id)); } catch { break; }
      if (r.exited) {  // gone at once, with no window: usually a missing BIOS or an emulator never set up
        const name = g.source === 'Emulators' ? await emulatorName(g) : g.title;
        toast(`${name} closed straight away. ${g.source === 'Emulators' ? 'It may need a BIOS or first-time setup: open it once from Settings › Systems.' : 'Try starting it again.'}`, 8000);
      }
      if (!r.waiting || performance.now() - start > 180000) break;  // a first-time unpack can take a while
    }
    return done();
  }
  setTimeout(done, 3600);
}
// Refresh after returning from a game (new playtime, newly installed games).
let lastLoad = Date.now();
addEventListener('focus', async () => {
  if (!API || Date.now() - lastLoad < 20000 || P.open) return;
  lastLoad = Date.now();
  await loadLibrary(); buildRow(false);
  if (D.open) { D.game = LIB.find(x => x.id === D.game.id) || D.game; renderStats(); }
});

// Games dropped into the ROMs folder appear by themselves: the helper watches the folders and rescans, and this
// ping (which also keeps the helper alive) notices the new scan time. Waits while a menu is open, then catches up.
let libStamp = 0;
let pageStamp = 0;
let sysStamp = 0;
async function watchLibrary() {
  let r;
  try { r = await api('/api/ping'); } catch { return; }
  // New page files: refresh by itself, but only on the plain home screen so nothing is interrupted
  if (r.page && pageStamp && r.page !== pageStamp) {
    if (!S.busy && S.zone === 0 && !document.body.className.match(/-open/)) return location.reload();
  } else pageStamp = r.page || pageStamp;  // a newer page waits for the home screen instead of being forgotten
  if (r.scanned && r.scanned !== sysStamp && P.open && QUEUE_VIEWS.includes(P.view) && !P.working) {  // a system added by itself shows up on an open Systems page
    sysStamp = r.scanned;
    try { P.data = await api('/api/settings'); renderPanel(); } catch {}
  }
  if (!r.scanned || r.scanned === libStamp || P.open || Q.open) return;
  const before = new Set(LIB.map(g => g.id));
  await loadLibrary(); buildRow(false);
  if (D.open) { D.game = LIB.find(x => x.id === D.game.id) || D.game; renderStats(); }
  const added = LIB.filter(g => !before.has(g.id) && !g.hidden);
  if (added.length) toast(added.length === 1 ? `Added ${added[0].title}` : `Added ${added.length} games`, 3000);
}

// ---------- game details ----------
// Opens on A / Enter: hero art, playtime, Play, trailers/screenshots and the game's news.
// Left column has two rows (buttons, media); right column is the news. The ⋯ button opens a small vertical menu.
const D = { open: false, game: null, data: null, col: 0, row: 0, a: 0, m: 0, n: 0, menu: false, mi: 0 };
const fmtTime = m => m >= 60 ? `${(m / 60).toFixed(m >= 6000 ? 0 : 1)} h` : m ? `${m} min` : 'Not yet';
// Today, Yesterday... count calendar days in the profile's time zone, not 24-hour periods
function fmtDate(ts) {
  if (!ts) return 'Never';
  const d = new Date(ts * 1000), z = zoneOpt(), ymd = t => new Date(t).toLocaleDateString('en-CA', z);  // YYYY-MM-DD
  const days = Math.round((Date.parse(ymd(Date.now())) - Date.parse(ymd(d))) / 864e5);
  if (days < 1) return 'Today';
  if (days < 2) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', ...z, ...(ymd(d).slice(0, 4) !== ymd(Date.now()).slice(0, 4) && { year: 'numeric' }) });
}
const ICON_PLAY = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>';
const ICON_FILM = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M10 9.2v5.6l4.8-2.8z" fill="currentColor"/></svg>';
const ICON_MORE = '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5.5" cy="12" r="1.9"/><circle cx="12" cy="12" r="1.9"/><circle cx="18.5" cy="12" r="1.9"/></svg>';
function detailActions() {
  const g = D.game;
  return [
    { label: RUN.has(g.id) ? 'Resume' : g.installed === false ? 'Install' : 'Play', html: ICON_PLAY, primary: true, run: () => launchGame(g) },
    ...(RUN.has(g.id) ? [{ label: closeAsk === g.id ? 'Press A again' : 'Close game', html: icon('close'), run: () => askClose(g) }] : []),
    ...(D.data?.trailers?.length ? [{ label: 'Watch trailer', html: ICON_FILM, run: () => openViewer(0) }] : []),
    { label: '', html: ICON_MORE, more: true, run: () => { D.menu = true; D.mi = 0; renderActions(); } },
  ];  // no Back button: B (or Esc) goes back
}
function moreItems() {
  const g = D.game;
  return [
    { label: g.favorite ? 'Remove from Favourites' : 'Add to Favourites', run: () => setFavorite(g, !g.favorite) },
    { label: 'Collections', run: () => openCollections(g) },
    { label: 'Rename', run: () => renameGame(g) },  // also here, not only in the game menu (Y / hold), so it's found
    ...(g.renamed ? [{ label: 'Restore original name', run: () => setGameName(g, '') }] : []),
    ...(g.source === 'Emulators' ? [] : [{ label: 'Change app location', run: () => changeAppLocation(g) }]),  // a ROM's program is its console's emulator
    ...(g.appPath ? [{ label: 'Restore default app location', run: () => changeAppLocation(g, true) }] : []),
    { label: 'Change cover', run: () => openGame(g, 'cover') },
    { label: 'Change logo', run: () => openGame(g, 'logo') },
    ...(g.customLogo ? [{ label: 'Reset logo', run: () => resetArt(g, 'logo') }] : []),
    { label: 'Change background', run: () => openGame(g, 'hero') },
    ...(g.custom ? [{ label: 'Reset cover', run: () => resetArt(g, 'cover') }] : []),
    ...(g.customHero ? [{ label: 'Reset background', run: () => resetArt(g, 'hero') }] : []),
    { label: g.hidden ? 'Unhide this game' : 'Hide this game', run: () => setHidden(g, !g.hidden) },
  ];
}
// ---------- favourites and collections ----------
async function afterLibraryChange() {
  await loadLibrary(); renderTabs(); buildRow(false);
  if (D.open) D.game = LIB.find(x => x.id === D.game.id) || D.game;  // the ⋯ and Y menus read it
}
// A name of your own for a game, typed on the on-screen keyboard (or a real one), starting from the name it has now
function renameGame(g) {
  openSearch(null, text => setGameName(g, text.trim()), { id: 'rename', label: `New name for ${g.title}`, max: 120 });
  $('#srq').value = g.title; searchRun();
}
async function setGameName(g, title) {
  if (title === g.title) return;
  try { await api('/api/game/rename', { id: g.id, title }); } catch (e) { return toast(e.message); }
  delete DCACHE[g.id];  // a new name can find other details
  await afterLibraryChange();
  if (D.open) renderDetails();  // its title, now
  toast(title ? `Renamed to ${title}` : 'Original name restored');
}
async function setFavorite(g, favorite) {
  try { await api('/api/game/favorite', { id: g.id, favorite }); } catch (e) { return toast(e.message); }
  await afterLibraryChange();
  toast(favorite ? `${g.title} added to Favourites` : `${g.title} removed from Favourites`);
}
const allCollections = () => [...new Set(LIB.flatMap(g => g.collections || []))].sort((a, b) => a.localeCompare(b));
function openCollections(g) {
  const mine = g.collections || [];
  sysMenu('Collections', [
    ...allCollections().map(n => ({ label: n + (mine.includes(n) ? '  ✓' : ''), ic: icon('library'), run: () => setCollection(g, n, !mine.includes(n)) })),
    { label: 'New collection', ic: icon('star'), run: () => openSearch(null, name => setCollection(g, name, true)) },
    { label: 'Close', ic: icon('close'), run: () => {} },
  ]);
}
async function setCollection(g, name, member) {
  try { await api('/api/game/collection', { id: g.id, name, member }); } catch (e) { return toast(e.message); }
  await afterLibraryChange();
  toast(member ? `${g.title} added to ${name}` : `${g.title} removed from ${name}`);
}
async function setHidden(g, hidden) {
  if (!API) return toast('Start the frontend with Start Frontend.bat to hide games');
  const i = idx();
  try { await api('/api/game/hide', { id: g.id, hidden }); } catch (e) { return toast(e.message); }
  if (D.open) closeDetails();
  if (P.open) closePanel();
  await loadLibrary();
  buildRow(false);
  if (game()?.id !== g.id || hidden) { select(clamp(i, 0, S.list.length - 1)); update(); }  // stay near where the game was
  toast(hidden ? `${g.title} hidden. Bring it back from Settings › Hidden games.` : `${g.title} is back in your library`, 3000);
}
// Trailers first, then screenshots.
function mediaItems() {
  const d = D.data || {};
  const shots = d.screenshots || [];
  return [...(d.trailers || []).map(t => ({ kind: 'video', youtube: t.youtube, thumb: t.thumb, src: t.hls || t.mp4, alt: t.mp4, label: t.name || 'Trailer' })),
    ...shots.map(s => ({ kind: 'image', thumb: s.thumb, src: s.full, label: '' }))];
}
function renderActions() {
  $('#details .d-actions').innerHTML = detailActions().map((b, i) => `<div class="d-btn${b.primary ? ' primary' : ''}${b.more ? ' more' : ''}" data-i="${i}">${b.html || ''}${b.label ? `<span>${esc(b.label)}</span>` : ''}${
    b.more && D.menu ? `<div class="d-menu">${moreItems().map((m, j) => `<div class="d-mi" data-j="${j}">${esc(m.label)}</div>`).join('')}</div>` : ''}</div>`).join('');
  // The column scrolls, so it clips the menu: below the buttons when it fits, else on the side with more room, scrolling
  // when even that is too short (many art rows on a 16:9 screen)
  const menu = $('#details .d-menu');
  if (menu) {
    const col = $('#details .d-left').getBoundingClientRect(), b = menu.parentElement.getBoundingClientRect(), z = uiScale();
    const need = menu.getBoundingClientRect().height + innerHeight * .012 * z, edge = innerHeight * .015;
    const below = Math.min(col.bottom, innerHeight) - edge - b.bottom, above = b.top - Math.max(col.top, 0) - edge;
    if (need > below) {
      if (above > below) menu.classList.add('up');
      if (need > Math.max(above, below)) Object.assign(menu.style, { maxHeight: (Math.max(above, below) - innerHeight * .012 * z) / z + 'px', overflowY: 'auto' });
    }
  }
  detailsFocus();
}
function heroLayer(url, blur) {
  const box = $('#details .d-hero'), layer = document.createElement('div');
  layer.className = 'xf' + (blur ? ' blur' : '');
  layer.style.cssText = `position:absolute;inset:0;opacity:0;transition:opacity .9s ease;background:url("${url}") center 30%/cover no-repeat`;
  const old = [...box.children];
  box.appendChild(layer);
  raf2(() => layer.style.opacity = 1);
  setTimeout(() => old.forEach(o => o.remove()), 950);
}
// Details are fetched once per game and kept for 10 minutes; news comes separately so the screen fills in at once.
const DCACHE = {};
function detailsFor(g) {
  if (!API || !g) return null;
  const c = DCACHE[g.id];
  if (c && Date.now() - c.t < 600000) return c;
  const q = encodeURIComponent(g.id);
  const entry = { t: Date.now() };
  entry.info = api('/api/game?id=' + q).then(d => {
    if (!d?.description) entry.t = Date.now() - 540000;  // nothing found yet: asked again after a minute, not ten
    return d;
  }).catch(e => { delete DCACHE[g.id]; throw e; });
  return DCACHE[g.id] = Object.assign(entry, {
    news: g.source === 'Emulators' ? Promise.resolve([]) : api('/api/game/news?id=' + q).then(r => r.news).catch(() => []) });  // emulated games show achievements instead
}
let prefetchTimer;
function schedulePrefetch(g) { clearTimeout(prefetchTimer); prefetchTimer = setTimeout(() => detailsFor(g), 450); }  // while browsing the row
async function openDetails(g, from = null) {  // from: the Library or Search page it was opened on, which B goes back to
  if (!g) return;
  Object.assign(D, { open: true, game: g, data: null, col: 0, row: 0, a: 0, m: 0, n: 0, menu: false, mi: 0, from });
  document.body.classList.add('details-open');
  tick(520, .09);
  $('#details .d-hero').innerHTML = '';
  if (g.cover) heroLayer(g.cover, true);  // blurred cover until the real hero art arrives
  renderDetails();
  const c = detailsFor(g);
  if (!c) return;
  c.info.then(d => {
    if (D.game !== g) return;
    D.data = { ...d, news: D.data?.news ?? d.news };
    if (d.hero) { const im = new Image(); im.onload = () => D.game === g && heroLayer(d.hero, !!d.heroSoft); im.src = d.hero; }
    renderDetails();
    if (d.achPending) api('/api/game/achievements?id=' + encodeURIComponent(g.id)).then(r => {
      d.achPending = false; d.achievements = r.achievements;
      if (D.game === g) { D.data.achievements = r.achievements; D.data.achPending = false; renderStats(); renderNews(); }
    }).catch(() => {});
  }).catch(e => toast(e.message));
  c.news.then(news => {
    if (D.game !== g) return;
    D.data = { ...(D.data || {}), news };
    renderNews();
  });
}
function closeDetails() { D.open = false; document.body.classList.remove('details-open'); tick(420, .06); }
function renderDetails() {
  const g = D.game, d = D.data, root = $('#details');
  const logo = root.querySelector('.d-logo');
  logo.innerHTML = `<h1>${esc(g.title)}</h1>`;
  if (d?.logo && !g.renamed) {  // swap the text title for the game's logo once it has loaded (a name of your own stays as text)
    const im = new Image(); im.alt = g.title;
    im.onload = () => { if (D.game === g) { logo.innerHTML = ''; logo.appendChild(im); } };
    im.src = d.logo;
  }
  root.querySelector('.d-meta').textContent = [g.system || g.group, ...(d?.genres || []), d?.developer].filter(Boolean).join('   ·   ');
  root.querySelector('.d-desc').textContent = d?.description || '';
  root.querySelector('.d-shots').innerHTML = mediaItems().map((m, i) => `<div class="d-media${m.kind === 'video' ? ' video' : ''}" data-i="${i}"><img src="${esc(m.thumb)}" alt="" loading="lazy">${m.kind === 'video' ? `<span class="pb">${ICON_PLAY}</span>` : ''}</div>`).join('');
  renderNews();
  renderStats();
  renderActions();
}
// Emulated games have no news: that column is their RetroAchievements list.
const isEmu = () => D.game?.source === 'Emulators';
const achList = () => isEmu() && D.data?.achievements?.items?.length ? D.data.achievements.items : null;
function renderNews() {
  const d = D.data, news = $('#details .d-news'), ach = achList();
  const hideSection = isEmu() ? !ach && d?.raConnected !== false : !d?.news?.length;  // with RetroAchievements not connected, it says how
  $('#details .d-right').classList.toggle('no-content', hideSection);
  if (hideSection) {
    news.innerHTML = '';
    $('#details .d-newshead').textContent = '';
    if (D.col === 1) D.col = 0;
    detailsFocus();
    return;
  }
  $('#details .d-newshead').textContent = !isEmu() ? 'News' : ach ? `Achievements · ${d.achievements.done} of ${d.achievements.total}` : 'Achievements';
  news.innerHTML = !API ? '<div class="d-empty">News appears when the frontend is started with Start Frontend.bat.</div>'
    : isEmu() && !ach ? `<div class="d-empty">${!d || d.achPending ? 'Loading achievements…'
        : d.raConnected === false ? 'Connect RetroAchievements in Settings › Accounts to see achievements for this game.'
        : 'No RetroAchievements set found for this game.'}</div>`
    : ach ? ach.map((a, i) => `<div class="d-item d-ach${a.earned ? ' got' : ''}" data-i="${i}" style="animation-delay:${Math.min(i, 12) * 50}ms">
        <img src="${esc(a.badge)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'), { className: 'ap-noicon' }))"><div class="nb"><div class="nt">${esc(a.title)}</div><div class="ns">${esc(a.desc)}</div>
        <div class="nd">${a.points} points${a.earned ? ` · Unlocked ${esc(fmtDate(Date.parse(a.earned.replace(' ', 'T') + 'Z') / 1000))}${a.hardcore ? ' · Hardcore' : ''}` : ''}</div></div></div>`).join('')
    : !Array.isArray(d?.news) ? '<div class="d-empty">Loading news…</div>'
    : d.news.length ? d.news.map((n, i) => `<div class="d-item" data-i="${i}" style="animation-delay:${i * 70}ms">
        ${newsImage(n, i) ? `<div class="ni" style="background-image:url(&quot;${esc(newsImage(n, i))}&quot;)"></div>` : ''}
        <div class="nb"><div class="nd">${esc(fmtDate(n.date))}${n.source ? ' · ' + esc(n.source) : ''}</div><div class="nt">${esc(n.title)}</div><div class="ns">${esc(n.summary)}</div></div></div>`).join('')
    : '<div class="d-empty">No news found for this game.</div>';
  detailsFocus();
}
function renderStats() {
  const g = D.game, d = D.data;
  const stats = [['Playtime', fmtTime(g.minutes || 0)], ['Last played', fmtDate(g.lastPlayed)]];
  if (d?.achievements?.total > 0) stats.push(['Achievements', `${d.achievements.done} / ${d.achievements.total}`]);
  if (d?.released) stats.push(['Released', d.released]);
  if (D.players?.id === g.id && D.players.n != null) stats.push(['Playing now', D.players.n.toLocaleString('en-US')]);
  else if (API && D.players?.id !== g.id) {
    D.players = { id: g.id, n: null };  // Steam's live count, filled in when it arrives
    api('/api/game/players?id=' + encodeURIComponent(g.id)).then(r => { if (D.open && D.game.id === g.id && r.players != null) { D.players.n = r.players; renderStats(); } }).catch(() => {});
  }
  $('#details .d-stats').innerHTML = stats.map(([k, v]) => `<div class="d-stat${k === 'Achievements' && hasAchList() ? ' ach' : ''}"><b>${esc(v)}</b><span>${k}</span></div>`).join('');
  detailsFocus();
}
function detailsFocus() {
  const left = D.col === 0 && !D.menu;
  document.querySelectorAll('#details .d-btn').forEach((e, i) => e.classList.toggle('sel', left && D.row === 0 && i === D.a));
  $('#details .d-stat.ach')?.classList.toggle('sel', left && D.row === -1);
  document.querySelectorAll('#details .d-btn.more').forEach(e => e.classList.toggle('open', D.menu));
  document.querySelectorAll('#details .d-mi').forEach((e, i) => e.classList.toggle('sel', D.menu && i === D.mi));
  const mi = $('#details .d-mi.sel'), menu = mi?.parentElement;  // a menu too tall for the column scrolls inside itself
  if (mi && menu.scrollHeight > menu.clientHeight) menu.scrollTop = clamp(menu.scrollTop, mi.offsetTop + mi.offsetHeight - menu.clientHeight + 8, mi.offsetTop - 8);
  document.querySelectorAll('#details .d-media').forEach((e, i) => e.classList.toggle('sel', left && D.row === 1 && i === D.m));
  document.querySelectorAll('#details .d-item').forEach((e, i) => e.classList.toggle('sel', D.col === 1 && i === D.n));
  $('#details .d-media.sel')?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
  if (left && D.row < 1) {  // a column taller than the screen goes back to the top, unless that would leave Play below it
    const col = $('#details .d-left'), el = $(D.row === 0 ? '#details .d-btn.sel' : '#details .d-stat.ach');
    const c = col.getBoundingClientRect(), k = c.height / col.offsetHeight || 1;  // screen pixels per pixel of the (zoomed) column
    if (el && el.getBoundingClientRect().bottom - c.top + col.scrollTop * k > col.clientHeight * k) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    else col.scrollTo({ top: 0, behavior: 'smooth' });
  }
  $('#details .d-item.sel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
const newsCount = () => D.data?.news?.length || achList()?.length || 0;
function detailsMove(dx, dy) {
  const state = () => [D.col, D.row, D.a, D.m, D.n, D.menu, D.mi].join();
  const before = state(), nA = detailActions().length, nM = mediaItems().length, nN = newsCount();
  if (D.menu) {  // vertical ⋯ menu: up/down choose, sideways closes it
    if (dy) D.mi = clamp(D.mi + dy, 0, moreItems().length - 1);
    else { D.menu = false; renderActions(); }
  } else if (D.col === 1) {
    if (dx < 0) D.col = 0;
    else if (dy) D.n = clamp(D.n + dy, 0, nN - 1);
  } else if (D.row === -1) {  // the Achievements card above the buttons
    if (dy > 0) D.row = 0;
    else if (dx > 0 && nN) D.col = 1;
  } else if (D.row === 0) {
    if (dx) { const n = D.a + dx; if (n >= nA) { if (nN) D.col = 1; } else D.a = clamp(n, 0, nA - 1); }
    else if (dy > 0 && nM) D.row = 1;
    else if (dy < 0 && hasAchList()) D.row = -1;
  } else {
    if (dx) { const n = D.m + dx; if (n >= nM) { if (nN) D.col = 1; } else D.m = clamp(n, 0, nM - 1); }
    else if (dy < 0) D.row = 0;
  }
  if (before !== state()) { tick(D.col ? 700 : 640, .04); detailsFocus(); }
}
function detailsBack() {
  if (D.menu) { D.menu = false; tick(420, .05); return renderActions(); }
  closeDetails();
  backTo(D.from);
}
// The page details were opened from, as it was: its category, order and game, or the search and its result
function backTo(from) {
  const l = from?.lib || (from?.page === 'lib' && from);
  if (l) {
    openLibraryPage(l.mode);
    if (!LP.open) return;
    LP.cat = Math.max(0, LP.cats.findIndex(c => c.name === l.cat)); LP.sort = l.sort; LP.zone = 'grid';
    LP.i = Math.max(0, lpItems().findIndex(g => g.id === l.id));
    renderLibraryPage();
  }
  if (from?.page === 'search') {
    openSearch(from.scope);
    $('#srq').value = from.q; searchRun();
    const r = SR.results.findIndex(g => g.id === from.id);
    if (r >= 0) { SR.zone = 'res'; SR.r = r; searchFocus(); }
  }
}
const lpState = () => ({ page: 'lib', mode: LP.mode, cat: LP.cats[LP.cat]?.name, sort: LP.sort, id: lpItems()[LP.i]?.id });
// Posts without a picture borrow one of the game's screenshots.
function newsImage(n, i) {
  const shots = D.data?.screenshots || [];
  return n.image || (shots.length ? shots[i % shots.length].thumb : D.data?.hero || '');
}
function detailsActivate() {
  tick(880, .08);
  if (D.menu) { const it = moreItems()[D.mi]; D.menu = false; renderActions(); return it?.run(); }
  if (D.col === 1) {
    if (achList()) return openAchievements(achList()[D.n]);  // an emulated game's column is its achievements
    const n = D.data?.news?.[D.n]; return n && openReader(n, newsImage(n, D.n));
  }
  if (D.row === 1) return openViewer(D.m);
  if (D.row === -1) return openAchievements();
  detailActions()[D.a]?.run();
}

// ---------- achievements page ----------
// Opened from the Achievements card on the details screen: progress, then every achievement (Steam or
// RetroAchievements) with its icon, description and unlock date. LB/RB switch All / Unlocked / Locked.
const AP = { open: false, view: 'all', i: 0 };
const hasAchList = () => !!D.data?.achievements?.items?.length;
const achDate = a => a.earned && a.earned !== 'unlocked' ? fmtDate(Date.parse(a.earned.replace(' ', 'T') + 'Z') / 1000) : '';
function achShown() {
  const items = D.data?.achievements?.items || [];
  const got = items.filter(a => a.earned).sort((a, b) => (b.earned > a.earned) - (b.earned < a.earned)), locked = items.filter(a => !a.earned);
  return AP.view === 'got' ? got : AP.view === 'locked' ? locked : [...got, ...locked];  // newest unlocks first
}
function openAchievements(item) {  // item: the one to highlight
  if (!hasAchList()) return;
  AP.open = true; AP.view = 'all'; AP.i = 0;
  if (item) AP.i = Math.max(0, achShown().indexOf(item));
  document.body.classList.add('ach-open'); tick(600, .07); renderAchievements();
}
function closeAchievements() { AP.open = false; document.body.classList.remove('ach-open'); tick(420, .06); }
function achTab(dir) {
  const views = ['all', 'got', 'locked'], n = clamp(views.indexOf(AP.view) + dir, 0, 2);
  if (views[n] !== AP.view) { AP.view = views[n]; AP.i = 0; tick(760, .04); renderAchievements(); }
}
function renderAchievements() {
  const a = D.data.achievements, g = D.game, pct = a.total ? Math.round(a.done / a.total * 100) : 0;
  const points = a.items.reduce((s, x) => s + (x.points || 0), 0), gotPoints = a.items.filter(x => x.earned).reduce((s, x) => s + (x.points || 0), 0);
  $('#achpage .ap-head').innerHTML = `<div class="ap-title"><h1>${esc(g.title)}</h1><div class="np-sub">${esc(a.source || '')} achievements${points ? ` · ${gotPoints} of ${points} points` : ''}</div></div>
    <div class="ap-prog"><div class="ap-count"><b>${a.done}</b> of ${a.total} · ${pct}%</div><div class="ap-bar"><i style="width:${pct}%"></i></div></div>`;
  const n = { all: a.items.length, got: a.done, locked: a.items.length - a.done };
  $('#achpage .al-tabs').innerHTML = [['all', 'All'], ['got', 'Unlocked'], ['locked', 'Locked']].map(([k, label]) =>
    `<div class="al-tab${AP.view === k ? ' sel' : ''}" data-k="${k}">${label}<span>${n[k]}</span></div>`).join('');
  const shown = achShown();
  $('#achpage .ap-grid').innerHTML = shown.length ? shown.map((x, i) => `<div class="ap-card${x.earned ? ' got' : ''}" data-i="${i}" style="animation-delay:${Math.min(i, 16) * 25}ms">
      <img src="${esc(x.badge)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'), { className: 'ap-noicon' }))"><div class="nb"><div class="nt">${esc(x.title)}</div>${x.desc ? `<div class="ns">${esc(x.desc)}</div>` : ''}
      <div class="nd">${[x.earned ? `Unlocked${achDate(x) ? ' ' + esc(achDate(x)) : ''}` : 'Locked', x.hardcore ? 'Hardcore' : '', x.points ? `${x.points} points` : '',
        x.rarity != null ? `${x.rarity < 10 ? x.rarity.toFixed(1) : Math.round(x.rarity)}% of players` : ''].filter(Boolean).join(' · ')}</div></div></div>`).join('')
    : `<div class="d-empty">${AP.view === 'got' ? 'Nothing unlocked yet.' : 'All unlocked!'}</div>`;
  achFocus();
}
function achFocus() {
  document.querySelectorAll('#achpage .ap-card').forEach(e => e.classList.toggle('sel', +e.dataset.i === AP.i));
  $('#achpage .ap-card.sel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
function achMove(dx, dy) {
  const cards = [...document.querySelectorAll('#achpage .ap-card')];
  const cols = cards.filter(e => e.offsetTop === cards[0]?.offsetTop).length || 1;
  const n = clamp(AP.i + dx + dy * cols, 0, cards.length - 1);
  if (n !== AP.i) { AP.i = n; tick(700, .03); achFocus(); }
}
$('#achpage').addEventListener('click', e => {
  const t = e.target.closest('.al-tab'), c = e.target.closest('.ap-card');
  if (t) { AP.view = t.dataset.k; AP.i = 0; renderAchievements(); }
  else if (c) { AP.i = +c.dataset.i; achFocus(); }
});
$('#details .d-stats').addEventListener('click', e => { if (e.target.closest('.d-stat.ach')) { D.col = 0; D.row = -1; detailsFocus(); openAchievements(); } });

// ---------- trailer & screenshot viewer ----------
// Left/right flips through trailers and screenshots; A plays/pauses a trailer.
const V = { open: false, i: 0, items: [] };
function openViewer(i, items = mediaItems()) {  // the details screen's media, or any list (the album)
  V.items = items;
  if (!V.items.length) return;
  V.open = true;
  document.body.classList.add('viewer-open');
  $('#viewer .v-strip').innerHTML = V.items.map((m, j) => `<div class="v-thumb${m.kind === 'video' ? ' video' : ''}" data-i="${j}"><img src="${esc(m.thumb)}" alt="" loading="lazy"></div>`).join('');
  showMedia(i);
}
let youtubeReady;
function loadYouTubePlayer() {
  if (window.YT?.Player) return Promise.resolve();
  if (!youtubeReady) youtubeReady = new Promise((resolve, reject) => {
    window.onYouTubeIframeAPIReady = resolve;
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api'; script.onerror = reject;
    document.head.appendChild(script);
  });
  return youtubeReady;
}
function showMedia(i) {
  V.i = (i + V.items.length) % V.items.length;
  const m = V.items[V.i], stage = $('#viewer .v-stage');
  stopVideo();
  if (m.youtube) {
    stage.innerHTML = '<div id="youtube-trailer"></div>';
    loadYouTubePlayer().then(() => {
      if (!V.open || V.items[V.i] !== m) return;
      V.youtube = new YT.Player('youtube-trailer', { host: 'https://www.youtube-nocookie.com', videoId: m.youtube,
        playerVars: { playsinline: 1, rel: 0, origin: location.origin },
        events: {
          onReady: event => { event.target.setVolume(Math.round((S.trailerVolume ?? 0.2) * 100)); if (S.trailerMuted) event.target.mute(); event.target.playVideo(); },
          onError: () => toast('This trailer is unavailable or its publisher has disabled embedded playback.', 6000),
        } });
    }).catch(() => toast('Could not load the trailer player. Check your connection.'));
  } else if (m.kind === 'video') {
    stage.innerHTML = '<video controls autoplay playsinline></video>';
    const v = stage.querySelector('video');
    v.volume = typeof S.trailerVolume === 'number' && Number.isFinite(S.trailerVolume) ? Math.max(0, Math.min(1, S.trailerVolume)) : 0.2;
    v.muted = S.trailerMuted === true;
    v.addEventListener('volumechange', () => { S.trailerVolume = v.volume; S.trailerMuted = v.muted; save(); });
    // Steam streams trailers (HLS); if this browser can't, fall back to the MP4 copy older trailers have.
    v.onerror = () => { if (m.alt && !v.src.includes(m.alt)) v.src = m.alt; else toast('This trailer can’t be played here'); };
    v.src = m.src;
  } else {  // fill the stage; small pictures (DS/GBA screenshots) scale up with crisp pixels
    stage.innerHTML = `<img src="${esc(m.src)}" alt="">`;
    const im = stage.querySelector('img');
    im.onload = () => im.classList.toggle('px', im.naturalWidth < 800);
  }
  $('#viewer .v-label').innerHTML = `<span class="v-badge${m.kind === 'video' ? ' video' : ''}">${esc(m.badge || (m.kind === 'video' ? 'Trailer' : 'Screenshot'))}</span>${m.label ? `<span class="v-name">${esc(m.label)}</span>` : ''}${m.capture ? `<button class="v-more" aria-label="Delete this">${icon('more')}</button>` : ''}`;
  document.querySelectorAll('#viewer .v-thumb').forEach((e, j) => e.classList.toggle('sel', j === V.i));
  $('#viewer .v-thumb.sel')?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
  tick(660, .05);
}
function stopVideo() {
  if (V.youtube) { try { S.trailerVolume = V.youtube.getVolume() / 100; S.trailerMuted = V.youtube.isMuted(); save(); V.youtube.destroy(); } catch {} V.youtube = null; }
  const v = $('#viewer video');
  if (v) { v.onerror = null; v.pause(); v.removeAttribute('src'); v.load(); }
}
function closeViewer() { stopVideo(); $('#viewer .v-stage').innerHTML = ''; V.open = false; document.body.classList.remove('viewer-open'); tick(420, .06); }
function viewerToggle() { if (V.youtube?.getPlayerState) { V.youtube.getPlayerState() === 1 ? V.youtube.pauseVideo() : V.youtube.playVideo(); return; } const v = $('#viewer video'); if (v) v.paused ? v.play() : v.pause(); }
$('#viewer').addEventListener('click', e => {
  const th = e.target.closest('.v-thumb');
  if (e.target.closest('.v-more')) return viewerMore();
  if (th) showMedia(+th.dataset.i);
  else if (e.target.closest('.v-arrow.l')) showMedia(V.i - 1);
  else if (e.target.closest('.v-arrow.r')) showMedia(V.i + 1);
  else if (e.target === $('#viewer') || e.target.classList.contains('v-stage')) closeViewer();
});
async function refreshDetails() {
  if (!D.open || !API) return;
  const g = LIB.find(x => x.id === D.game.id) || D.game;
  delete DCACHE[g.id];
  try {
    const d = await detailsFor(g).info;
    D.game = g; D.data = { ...d, news: D.data?.news ?? d.news };
    if (d.hero) heroLayer(d.hero, !!d.heroSoft);  // a screenshot standing in for art is softened
    else if (g.cover) heroLayer(g.cover, true);  // a background reset to none: the blurred cover, as when details open
    else $('#details .d-hero').innerHTML = '';
    renderDetails();
  } catch (e) { toast(e.message); }
}

// ---------- news reader ----------
// Shows a whole post inside the frontend. The helper sends plain text and image blocks, never Steam's markup.
const R = { open: false };
function openReader(n, image) {
  const body = (n.body || []).filter((b, i) => !(i < 4 && b.t === 'img' && b.src === n.image));
  $('#reader .r-article').innerHTML = `${image ? `<img class="r-hero" src="${esc(image)}" alt="">` : ''}
    <div class="r-meta">${esc(fmtDate(n.date))}${n.source ? ' · ' + esc(n.source) : ''}</div>
    <h1 class="r-title">${esc(n.title)}</h1>
    ${n.state === 'update' ? `<button class="r-update" type="button">Update to ${esc(n.version)} <span>A</span></button>` : ''}
    <div class="r-body">${body.map(b => b.t === 'img' ? `<img src="${esc(b.src)}" alt="" loading="lazy">`
      : b.t === 'h' ? `<h2>${esc(b.text)}</h2>` : b.t === 'li' ? `<li>${esc(b.text)}</li>` : `<p>${esc(b.text)}</p>`).join('') || `<p>${esc(n.summary)}</p>`}</div>`;
  $('#reader .r-scroll').scrollTop = 0;
  readerZoom(0);
  R.open = true; R.update = n.state === 'update';  // a newer release: A installs it
  document.body.classList.add('reader-open');
  tick(600, .07);
}
// Zoom a post in or out for reading from the sofa: RB in, LB out (the bumpers come through from every controller,
// a Steam Controller's too), Ctrl + the mouse wheel, or the right stick; 100% to 250%. Each post opens at 100%
function readerZoom(by = 0) {
  R.zoom = by === 0 ? 1 : clamp(Math.round(((R.zoom || 1) + by) * 100) / 100, 1, 2.5);
  $('#reader').style.setProperty('--rz', R.zoom);
  $('#reader .r-zoom').lastChild.textContent = R.zoom === 1 ? ' Zoom' : ` ${Math.round(R.zoom * 100)}%`;
}
$('#reader').addEventListener('wheel', e => { if (e.ctrlKey) { e.preventDefault(); readerZoom(e.deltaY < 0 ? .1 : -.1); } }, { passive: false });
$('#reader .r-zoom').addEventListener('click', () => readerZoom(0));
function readerUpdate() { closeReader(); updateNow('install'); }
$('#reader').addEventListener('click', e => { if (e.target.closest('.r-update')) readerUpdate(); });
function closeReader() { R.open = false; document.body.classList.remove('reader-open'); tick(420, .06); }
// Scrolling with a controller glides at a steady speed for as long as the direction is held (the presses repeat while
// it's held: each one keeps the glide going), then eases to a stop. A single press moves a short way.
function readerScroll(steps) {
  const el = $('#reader .r-scroll');
  R.dir = Math.sign(steps); R.held = performance.now(); R.speed = Math.max(R.speed || 0, Math.abs(steps) > 1 ? 3 : 1);
  if (R.glide) return;
  let v = 0, last = performance.now();
  const step = now => {
    const dt = Math.min(50, now - last); last = now;
    const holding = now - R.held < 420;  // the first repeat comes about 0.4 s after the press
    const want = holding ? R.dir * innerHeight * 1.1 * R.speed : 0;  // screen heights per second
    v += (want - v) * Math.min(1, dt / (holding ? 120 : 110));
    const before = el.scrollTop;
    el.scrollTop += v * dt / 1000;
    if (!R.open || (!holding && Math.abs(v) < 20) || (el.scrollTop === before && Math.abs(v) > 20 && now - R.held > 60)) { R.glide = 0; R.speed = 0; return; }
    R.glide = requestAnimationFrame(step);
  };
  R.glide = requestAnimationFrame(step);
}
$('#details').addEventListener('click', e => {
  const mi = e.target.closest('.d-mi'), b = e.target.closest('.d-btn'), md = e.target.closest('.d-media'), n = e.target.closest('.d-item');
  if (mi) { D.mi = +mi.dataset.j; return detailsActivate(); }
  if (b) { D.menu = false; D.col = 0; D.row = 0; D.a = +b.dataset.i; detailsFocus(); return detailsActivate(); }
  if (md) { D.menu = false; D.col = 0; D.row = 1; D.m = +md.dataset.i; detailsFocus(); return detailsActivate(); }
  if (n) { D.menu = false; D.col = 1; D.n = +n.dataset.i; detailsFocus(); return detailsActivate(); }
  if (D.menu) { D.menu = false; renderActions(); }
});

// ---------- news page: the latest news across your Steam games, and What's new in Ultra Front End (LB / RB) ----------
const NP = { open: false, items: [], i: 0, tab: 'games', games: null, updates: null, upErr: '', version: '' };
const NEWS_TABS = [['games', 'Game news'], ['new', 'What’s new']];
const RELEASE_STATE = { installed: 'Installed', update: 'Update ready' };
let newsReq = null, whatsReq = null;
// After an update the News button has a dot, and News opens on What's new, until its notes have been seen
async function openNewsPage(tab) {
  if (!API) return toast('Start the frontend with Start Frontend.bat to see news');
  NP.open = true; NP.i = 0; NP.tab = tab || (NEWS_DOT ? 'new' : 'games');
  document.body.classList.add('news-open');
  tick(600, .07);
  renderNewsPage(); loadNewsTab();
}
async function loadNewsTab() {
  const tab = NP.tab;
  if (tab === 'new') {
    try {
      whatsReq ??= api('/api/whatsnew').finally(() => setTimeout(() => whatsReq = null, 600000));
      const r = await whatsReq;
      NP.updates = r.items; NP.upErr = r.error || ''; NP.version = r.version || '';
      if (!r.items?.length) whatsReq = null;  // nothing to show (offline, say): asked again next time
      // the dot goes once the notes are actually on screen, not when they couldn't load
      if (NEWS_DOT && r.items?.length && NP.open && NP.tab === 'new') { NEWS_DOT = false; drawButtons(); api('/api/whatsnew', {}).catch(() => {}); }
    } catch (e) { NP.upErr = e.message; NP.updates ??= []; whatsReq = null; }
  } else {
    try {
      newsReq ??= api('/api/news').finally(() => setTimeout(() => newsReq = null, 600000));
      NP.games = (await newsReq).news;
    } catch (e) { NP.games ??= []; toast(e.message); }
  }
  if (NP.open && NP.tab === tab) renderNewsPage();
}
function renderNewsPage() {
  const games = NP.tab === 'games', list = games ? NP.games : NP.updates, grid = $('#newspage .np-grid');
  NP.items = list || [];
  NP.i = clamp(NP.i, 0, Math.max(0, NP.items.length - 1));
  $('#newspage .np-sub').textContent = games ? 'The latest from your Steam games' : `Updates to Ultra Front End${NP.version ? ` · you have version ${NP.version}` : ''}`;
  $('#newspage .al-tabs').innerHTML = NEWS_TABS.map(([k, label]) => `<div class="al-tab${NP.tab === k ? ' sel' : ''}" data-k="${k}">${label}</div>`).join('');
  if (!list) grid.innerHTML = `<div class="d-empty">${games ? 'Loading news from your games…' : 'Loading what’s new…'}</div>`;
  else if (games) grid.innerHTML = list.length ? list.map((n, i) => `<div class="np-card" data-i="${i}" style="animation-delay:${Math.min(i, 16) * 40}ms">
      <div class="ni" style="background-image:url(&quot;${esc(n.image || n.cover)}&quot;)"></div>
      <div class="nb"><div class="ng">${esc(n.game)}</div><div class="nt">${esc(n.title)}</div><div class="ns">${esc(n.summary)}</div><div class="nd">${esc(fmtDate(n.date))}${n.source ? ' · ' + esc(n.source) : ''}</div></div></div>`).join('')
    : `<div class="d-empty">No news yet. Connect Steam or add Steam games to see their news here.${LIB.some(g => g.appid) ? '' : '<br>Press A to connect Steam.'}</div>`;
  else grid.innerHTML = list.length ? list.map(relPicture).map((n, i) => `<div class="np-card np-rel${n.image ? ' own' : ''}" data-i="${i}" style="animation-delay:${Math.min(i, 16) * 40}ms">
      <div class="ni"${n.image ? ` style="background-image:linear-gradient(180deg, rgba(4, 8, 20, 0) 40%, rgba(4, 8, 20, .7)), url(&quot;${esc(n.image)}&quot;)"` : ''}>${n.image ? '' : `<span class="np-ver">${esc(n.version)}</span>`}${n.state ? `<span class="np-state ${n.state}">${RELEASE_STATE[n.state]}</span>` : ''}</div>
      <div class="nb"><div class="ng">Ultra Front End</div><div class="nt">${esc(n.title)}</div><div class="ns">${esc(n.summary)}</div><div class="nd">${esc(fmtDate(n.date))}</div></div></div>`).join('')
    : `<div class="d-empty">${esc(NP.upErr || 'Nothing here yet.')}</div>`;
  newsFocus();
}
// A release's own picture: the helper names it (image), or it's the first picture in its notes (an older helper)
function relPicture(n) { return n.image ? n : { ...n, image: (n.body || []).find(b => b.t === 'img')?.src || '' }; }
function newsTab(dir) {
  const k = dir > 0 ? 'new' : 'games';
  if (k === NP.tab) return;
  NP.tab = k; NP.i = 0; tick(760, .04);
  renderNewsPage(); loadNewsTab();
}
// From the pages that need a Steam account: Settings › Accounts, on Connect Steam unless it's connected already
async function connectSteam() {
  if (NP.open) closeNewsPage();
  if (HUB.open) closeHub();
  await openPanel('accounts');
  P.side = false;
  if (P.data && !P.data.accounts?.steam) setView('steam'); else renderPanel();
}
function closeNewsPage() { NP.open = false; document.body.classList.remove('news-open'); tick(420, .06); }
function newsFocus() {
  document.querySelectorAll('#newspage .np-card').forEach((e, i) => e.classList.toggle('sel', i === NP.i));
  glideTo($('#newspage .np-grid'), $('#newspage .np-card.sel'));
}
const newsCols = () => { const els = [...document.querySelectorAll('#newspage .np-card')]; return els.filter(e => e.offsetTop === els[0]?.offsetTop).length || 1; };
function newsMove(dx, dy) {
  const n = clamp(NP.i + dx + dy * newsCols(), 0, NP.items.length - 1);
  if (n !== NP.i) { NP.i = n; tick(700, .04); newsFocus(); }
}
function newsOpen() {
  const n = NP.items[NP.i];
  if (n && NP.tab === 'new') { const r = relPicture(n); return openReader({ ...r, source: 'Ultra Front End' }, r.image || 'assets/intro-wave.jpg'); }  // its own picture, else the wave
  if (n) openReader(n, n.image || n.cover); else if (NP.tab === 'games' && NP.games && !NP.items.length && !LIB.some(g => g.appid) && API) connectSteam();
}
$('#newspage').addEventListener('click', e => {
  const t = e.target.closest('.al-tab'), c = e.target.closest('.np-card');
  if (t) return newsTab(t.dataset.k === 'new' ? 1 : -1);
  if (c) { NP.i = +c.dataset.i; newsFocus(); newsOpen(); } else if (e.target.closest('.d-empty')) newsOpen();
});

// ---------- search ----------
// Type on a keyboard, or with the controller on the on-screen keys (A types, Y deletes). Matching games appear as
// covers; choosing one jumps to it in the row and opens its details.
const SR = { open: false, zone: 'kb', row: 1, col: 0, r: 0, results: [], scope: null, prompt: null, entry: null, shift: false };  // scope: 'pc' / 'emu' from the Library / Emulators page
const KB_ROWS = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM', ['Space', 'Delete', 'Clear']];
// Typing into a Settings field (SR.entry) adds Shift, the symbols names and keys use, and Paste
const KB_TEXT = [...KB_ROWS.slice(0, 3), ['Shift', ...'ZXCVBNM'], [..."-_.@/:'"], ['Space', 'Delete', 'Clear', 'Paste', 'Done']];
const kbRows = () => SR.entry ? KB_TEXT : KB_ROWS;
const kbRow = r => { const row = kbRows()[r]; return typeof row === 'string' ? [...row] : SR.prompt && !SR.entry ? [...row, 'Done'] : row; };
const kbCase = k => SR.shift ? k : k.toLowerCase();
const normT = t => t.toLowerCase().normalize('NFKD').replace(/[^a-z0-9 ]/g, '');
// With a prompt the same keys name something instead of searching: Done hands the text to the prompt.
// With an entry (a Settings or setup text field) they type it exactly as shown, starting from what the field holds.
function openSearch(scope = null, prompt = null, entry = null) {
  SR.open = true; SR.zone = 'kb'; SR.row = 1; SR.col = 0; SR.r = 0; SR.scope = scope; SR.prompt = prompt; SR.entry = entry; SR.shift = false; SR.typed = false;
  $('#srq').placeholder = entry ? entry.label : prompt ? 'Name your collection' : scope === 'pc' ? 'Search your PC games' : scope === 'emu' ? 'Search your ROMs' : 'Search your games';
  document.body.classList.add('search-open'); $('#search').classList.toggle('entry', !!entry);
  kbDraw();
  $('#srq').value = entry ? val(entry.id) : ''; searchRun(); tick(600, .07);
}
function kbDraw() {
  $('#search .sr-kb').innerHTML = kbRows().map((_, r) => `<div class="sr-krow">${kbRow(r).map((k, c) =>
    `<div class="sr-key${k.length > 1 ? ' wide' : ''}${k === 'Shift' && SR.shift ? ' on' : ''}" data-r="${r}" data-c="${c}">${k === 'Delete' ? '⌫ Delete' : k === 'Shift' ? '⇧ Shift'
      : k.length > 1 ? k : SR.entry ? kbCase(k) : SR.prompt ? k.toLowerCase() : k}</div>`).join('')}</div>`).join('');  // a name types in lower case until Done capitalises it
}
function closeSearch() {
  const entry = SR.entry;
  SR.open = false; SR.prompt = null; SR.entry = null; document.body.classList.remove('search-open'); tick(420, .06);
  watchAnims($('#search .sr-results'), false);  // hidden, not gone: its animated covers would keep playing
  if (entry) renderPanel();  // back on the field's row
}
// A text field in Settings or the setup guide, chosen with a controller or the mouse: Done writes the text into it, B leaves it as it was
function fieldKeyboard(it) {
  openSearch(null, text => { const f = $(`#panel input[data-id="${it.id}"]`); if (f) f.value = text; }, it);
  renderPanel();  // the highlight moves to this row, and its field loses the focus so real keys type on the keyboard
}
async function kbPaste() {
  let t;
  // through the helper: the window would ask permission first, in a prompt a controller can't answer
  try { t = API ? (await api('/api/clipboard', {})).text : await navigator.clipboard.readText(); } catch { return toast('Couldn’t read the clipboard'); }
  if (!SR.open) return;
  if (!t) return toast('Nothing to paste');
  $('#srq').value += t; tick(760, .04); searchRun();
}
// A real keyboard types straight in (the box only shows the text, so the D-pad never moves a text cursor); typing
// moves the highlight to the results so Enter opens the best match.
function searchKey(ch) {
  $('#srq').value += ch.toLowerCase(); tick(760, .03); searchRun(); afterKey();
}
// After a real key the highlight is never left on an on-screen key, where Enter would type it: it goes to Done when
// naming something, else to the best match; with no match Enter does nothing until the arrows move the highlight
const kbToDone = () => { SR.zone = 'kb'; SR.row = kbRows().length - 1; SR.col = kbRow(SR.row).indexOf('Done'); };
const afterKey = () => { SR.typed = true; if (SR.prompt) kbToDone(); else if (SR.results.length) { SR.zone = 'res'; SR.r = 0; } searchFocus(); };
function entryKey(ch) { $('#srq').value += ch; tick(760, .03); kbToDone(); searchRun(); }
function searchRun() {
  const q = $('#srq'), max = SR.entry ? SR.entry.max : SR.prompt && 40;  // the longest name the helper keeps
  if (max && q.value.length > max) { q.value = q.value.slice(0, max); toast(`${max} characters at most`, 1600); }
  if (SR.prompt) {
    SR.results = [];
    $('#search .sr-results').innerHTML = SR.entry ? `<div class="d-empty"><b>${esc(SR.entry.label)}</b><br>Type it here, then choose Done.</div>`
      : '<div class="d-empty">Type a name, then choose Done.</div>';
    if (SR.entry) q.scrollLeft = q.scrollWidth;  // a long key shows its end, where the typing is
    return searchFocus();
  }
  const words = normT(q.value).split(' ').filter(Boolean);
  const initials = t => normT(t).split(' ').filter(Boolean).map(w => /^\d+$/.test(w) ? w : w[0]).join('');  // "gta" finds Grand Theft Auto
  const hay = g => normT(`${g.title} ${platformOf(g)}`) + ' ' + initials(g.title);
  const inScope = g => !SR.scope || (SR.scope === 'emu') === (g.source === 'Emulators');
  SR.results = !words.length ? [] : LIB.filter(g => !g.hidden && inScope(g) && words.every(w => hay(g).includes(w)))
    .sort((a, b) => (normT(b.title).startsWith(words[0]) - normT(a.title).startsWith(words[0])) || byRecent(a, b)).slice(0, 40);
  SR.r = Math.min(SR.r, Math.max(0, SR.results.length - 1));
  if (!SR.results.length && SR.zone === 'res') SR.zone = 'kb';
  $('#search .sr-results').innerHTML = SR.results.length ? SR.results.map((g, i) => `<div class="sr-hit" data-i="${i}">
      <div class="sr-cover">${coverHTML(g)}</div>
      <div class="sr-name">${esc(g.title)}</div><div class="sr-plat">${esc(platformOf(g))}</div></div>`).join('')
    : `<div class="d-empty">${words.length ? 'No games match that.' : 'Start typing to find a game.'}</div>`;
  searchFocus();
}
function searchFocus() {
  document.querySelectorAll('#search .sr-key').forEach(e => e.classList.toggle('sel', SR.zone === 'kb' && +e.dataset.r === SR.row && +e.dataset.c === SR.col));
  document.querySelectorAll('#search .sr-hit').forEach(e => e.classList.toggle('sel', SR.zone === 'res' && +e.dataset.i === SR.r));
  $('#search .sr-hit.sel')?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  watchAnims($('#search .sr-results'), SR.open);
}
function searchType(k) {
  const q = $('#srq');
  if (k === 'Done' && SR.entry) { SR.prompt(q.value); return closeSearch(); }  // exactly as typed; nothing at all clears the field
  if (k === 'Shift') { SR.shift = !SR.shift; tick(640, .04); kbDraw(); return searchFocus(); }
  if (k === 'Paste') return kbPaste();
  if (k === 'Done') {
    const name = q.value.trim().split(' ').filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join(' '), done = SR.prompt;
    if (!name) return toast('Type a name first');
    closeSearch();
    return done(name);
  }
  q.value = k === 'Delete' ? q.value.slice(0, -1) : k === 'Clear' ? '' : q.value + (k === 'Space' ? ' ' : SR.entry ? kbCase(k) : k.toLowerCase());
  tick(k === 'Delete' || k === 'Clear' ? 520 : 760, .04); searchRun();
}
function searchMove(dx, dy) {
  if (SR.zone === 'kb') {
    if (dy > 0 && SR.row === kbRows().length - 1) { if (SR.results.length) SR.zone = 'res'; }  // the results row is below the keys
    else if (dy) { SR.row = clamp(SR.row + dy, 0, kbRows().length - 1); SR.col = Math.min(SR.col, kbRow(SR.row).length - 1); }
    else SR.col = clamp(SR.col + dx, 0, kbRow(SR.row).length - 1);
  } else if (dy < 0) SR.zone = 'kb';
  else if (dx) SR.r = clamp(SR.r + dx, 0, SR.results.length - 1);
  SR.typed = false;
  tick(700, .03); searchFocus();
}
// Enter after typing with no match: nothing (the highlighted key wasn't chosen)
function searchEnter() { if (!(SR.typed && lastSrc === 'key' && SR.zone === 'kb' && !SR.prompt)) searchOk(); }
function searchOk() {
  if (SR.zone === 'kb') return searchType(kbRow(SR.row)[SR.col]);
  const g = SR.results[SR.r];
  if (!g) return;
  const from = { page: 'search', scope: SR.scope, q: $('#srq').value, id: g.id, lib: LP.open ? lpState() : null };
  closeSearch();
  if (LP.open) closeLibraryPage();
  showInRow(g);
  openDetails(g, from);
}
// A game opened from a page is selected in the row behind the details screen; the tab changes only if it isn't there
function showInRow(g) {
  if (!TABS[S.tab].has(g)) { S.tab = 0; S.tabName = 'All Games'; save(); renderTabs(); }
  S.sel[TABS[S.tab].name] = g.id;
  S.zone = 0; buildRow(false);
}
$('#search').addEventListener('click', e => {
  const k = e.target.closest('.sr-key'), h = e.target.closest('.sr-hit');
  if (k) { SR.zone = 'kb'; SR.row = +k.dataset.r; SR.col = +k.dataset.c; searchOk(); }
  else if (h) { SR.zone = 'res'; SR.r = +h.dataset.i; searchOk(); }
});

// ---------- library / emulators pages ----------
// A full grid of your PC games (Library) or ROMs (Emulators). LB/RB pick a category (installed, a store or console,
// a genre), Y changes the order, A opens the game's details.
const LP = { open: false, mode: 'pc', cat: 0, sort: 0, i: 0, cats: [], zone: 'grid', h: 0 };  // zone 'head': the Search / Sort buttons
const LP_SORTS = [['A–Z', (a, b) => a.title.localeCompare(b.title)], ['Recently played', byRecent],
  ['Most played', (a, b) => (b.minutes || 0) - (a.minutes || 0) || a.title.localeCompare(b.title)]];
const lpBase = () => LIB.filter(g => !g.hidden && (LP.mode === 'emu' ? g.source === 'Emulators' : g.source !== 'Emulators'));
function lpCategories() {
  const base = lpBase(), cats = [{ name: 'All', has: () => true }];
  const count = f => base.filter(f).length;
  if (count(g => g.favorite)) cats.push({ name: 'Favourites', has: g => g.favorite });
  [...new Set(base.flatMap(g => g.collections || []))].sort((a, b) => a.localeCompare(b)).forEach(n => cats.push({ name: n, has: g => (g.collections || []).includes(n) }));
  if (LP.mode === 'pc') {
    if (count(g => g.installed !== false) && count(g => g.installed === false)) cats.push({ name: 'Installed', has: g => g.installed !== false });
    [...new Set(base.map(g => g.source))].sort((a, b) => count(g => g.source === b) - count(g => g.source === a))
      .forEach(src => cats.push({ name: src, has: g => g.source === src }));
  } else {
    const rank = n => (PLATFORM_ORDER.indexOf(n) + 1) || 99;
    [...new Set(base.map(platformOf))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b)).forEach(sys => cats.push({ name: sys, has: g => platformOf(g) === sys }));
  }
  const genres = {};
  base.forEach(g => (g.genres || []).forEach(x => genres[x] = (genres[x] || 0) + 1));
  Object.entries(genres).filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).forEach(([x]) => cats.push({ name: x, has: g => (g.genres || []).includes(x), genre: true }));
  return cats;
}
const lpItems = () => lpBase().filter(LP.cats[LP.cat]?.has || (() => true)).sort(LP_SORTS[LP.sort][1]);
function openLibraryPage(mode) {
  if (!LIB.length) return toast('No games yet. Open Settings to add your libraries and accounts.');
  Object.assign(LP, { open: true, mode, cat: 0, i: 0, zone: 'grid', h: 0 });
  LP.cats = lpCategories();
  if (mode === 'emu' && LP.cats.length < 2 && !lpBase().length) { LP.open = false; return toast('No emulated games yet. Put your games in the console folders inside your ROMs folder (Settings › Systems shows them), and they appear here by themselves', 6000); }
  document.body.classList.add('lib-open'); tick(600, .07); renderLibraryPage();
}
function closeLibraryPage() {
  LP.open = false; document.body.classList.remove('lib-open'); tick(420, .06);
  watchAnims($('#libpage .lp-grid'), false);  // hidden, not gone: its animated covers would keep playing
}
function lpCat(dir) {
  const n = clamp(LP.cat + dir, 0, LP.cats.length - 1);
  if (n !== LP.cat) { LP.cat = n; LP.i = 0; tick(760, .04); renderLibraryPage(); $('#libpage .lp-grid').scrollTop = 0; }
}
function lpSort() { LP.sort = (LP.sort + 1) % LP_SORTS.length; LP.i = 0; tick(680, .04); renderLibraryPage(); toast(`Sorted: ${LP_SORTS[LP.sort][0]}`, 1400); }
function renderLibraryPage() {
  const items = lpItems(), cat = LP.cats[LP.cat];
  $('#libpage .lp-head').innerHTML = `<div><h1>${LP.mode === 'emu' ? 'Emulators' : 'Library'}</h1>
      <div class="np-sub">${items.length} game${items.length === 1 ? '' : 's'}${cat && cat.name !== 'All' ? ` · ${esc(cat.name)}` : ''} · LB and RB change category</div></div>
    <div class="lp-btns"><div class="lp-btn lp-find">${icon('search')}Search</div><div class="lp-btn lp-sort"><b>Y</b> Sort: ${LP_SORTS[LP.sort][0]}</div></div>`;
  $('#libpage .lp-cats').innerHTML = LP.cats.map((c, i) => `${c.genre && !LP.cats[i - 1]?.genre ? '<span class="lp-sep"></span>' : ''}<div class="al-tab${i === LP.cat ? ' sel' : ''}" data-c="${i}">${
      c.genre ? '' : LP.mode === 'emu' && i ? tabIcon(c.name) : ''}${LP.mode === 'emu' && i && !c.genre && isWordmark(c.name) ? '' : `<span class="lp-name">${esc(c.name)}</span>`}<span>${lpBase().filter(c.has).length}</span></div>`).join('');
  $('#libpage .lp-cats .al-tab.sel')?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
  $('#libpage .lp-grid').innerHTML = items.length ? items.map((g, i) => `<div class="sr-hit lp-hit" data-i="${i}" style="animation-delay:${Math.min(i, 20) * 18}ms">
      <div class="sr-cover">${coverHTML(g)}</div>
      <div class="sr-name">${esc(g.title)}</div><div class="sr-plat">${esc(LP.mode === 'emu' ? platformOf(g) : g.source)}${g.minutes ? ' · ' + fmtTime(g.minutes) : ''}</div></div>`).join('')
    : `<div class="d-empty">${LP.mode === 'pc' && !lpBase().length && LIB.some(g => g.source === 'Emulators') ? 'No PC games yet. Your emulated games are on the Emulators page.' : 'No games here.'}</div>`;
  lpFocus();
}
// A cover over the game's name, which shows when there's no art or it fails to load (as on the home row)
const coverHTML = g => `<span>${esc(g.title)}</span>${g.cover ? `<img src="${esc(g.cover)}"${g.coverAnim ? ` data-anim="${esc(g.coverAnim)}" data-still="${esc(g.cover)}"` : ''} alt="" loading="lazy" onerror="${g.coverAnim ? 'coverFailed(this)' : 'this.remove()'}">` : ''}`;
// An animated cover that won't load: back to its still for good (only a still that fails takes the image away)
function coverFailed(im) {
  if (im.dataset.anim && im.getAttribute('src') === im.dataset.anim) { delete im.dataset.anim; im.src = im.dataset.still; }
  else coverRetry(im);
}
// A cover that didn't load (the helper busy or restarting) tries again twice before its tile shows the name card
function coverRetry(im) {
  const n = +(im.dataset.retry || 0);
  if (n >= 2) return im.remove();
  im.dataset.retry = n + 1;
  const src = im.getAttribute('src') || '';
  setTimeout(() => { if (im.isConnected) im.src = src.replace(/([?&])r=\d+&?/, '$1').replace(/[?&]$/, '') + (src.includes('?') ? '&' : '?') + 'r=' + (n + 1); }, 1500 * (n + 1));
}
// Keeps the selected item in view by gliding the list towards it: each move (and the repeats while a direction is held)
// only moves the target, so stepping row after row reads as one smooth scroll, not a jump and a stop per step
function glideTo(box, el, pad = 0.12) {
  if (!box || !el) return;
  const b = box.getBoundingClientRect(), r = el.getBoundingClientRect(), room = b.height * pad, max = box.scrollHeight - box.clientHeight;
  const now = box._glide ? box._target : box.scrollTop;
  let t = now;
  if (r.top - room < b.top) t = now - (b.top + room - r.top);
  else if (r.bottom + room > b.bottom) t = now + (r.bottom + room - b.bottom);
  box._target = clamp(t, 0, max);
  if (box._glide && performance.now() - box._glideAt < 250) return;  // one already running (a stalled one is restarted)
  cancelAnimationFrame(box._glide);
  const step = () => {
    const d = box._target - box.scrollTop, before = box.scrollTop;
    if (Math.abs(d) < 1) { box.scrollTop = box._target; box._glide = 0; return; }
    box._glideAt = performance.now();
    box.scrollTop += Math.sign(d) * Math.max(1, Math.abs(d) * .14);
    if (box.scrollTop === before) { box._glide = 0; return; }
    box._glide = requestAnimationFrame(step);
  };
  box._glideAt = performance.now();
  box._glide = requestAnimationFrame(step);
}
function lpFocus() {
  document.querySelectorAll('#libpage .lp-btn').forEach((e, j) => e.classList.toggle('sel', LP.zone === 'head' && j === LP.h));
  $('#libpage .lp-cats').classList.toggle('focus', LP.zone === 'cats');
  document.querySelectorAll('#libpage .lp-hit').forEach(e => e.classList.toggle('sel', LP.zone === 'grid' && +e.dataset.i === LP.i));
  glideTo($('#libpage .lp-grid'), $('#libpage .lp-hit.sel'));
  watchAnims($('#libpage .lp-grid'), LP.open);
}
function lpMove(dx, dy) {
  const hits = [...document.querySelectorAll('#libpage .lp-hit')];
  const cols = hits.filter(e => e.offsetTop === hits[0]?.offsetTop).length || 1;
  if (LP.zone === 'head') {  // Search / Sort buttons above the grid
    if (dx) LP.h = clamp(LP.h + dx, 0, 1); else if (dy > 0) LP.zone = 'cats';
    tick(700, .03); return lpFocus();
  }
  if (LP.zone === 'cats') {  // the category row: left and right change category straight away
    if (dx) return lpCat(dx);
    LP.zone = dy < 0 ? 'head' : hits.length ? 'grid' : 'cats';
    tick(700, .03); return lpFocus();
  }
  if (dy < 0 && LP.i < cols) { LP.zone = 'cats'; tick(700, .03); return lpFocus(); }
  const n = clamp(LP.i + dx + dy * cols, 0, hits.length - 1);
  if (n !== LP.i) { LP.i = n; tick(700, .03); lpFocus(); }
}
function lpOpen() {
  if (LP.zone === 'head') return LP.h === 0 ? openSearch(LP.mode) : lpSort();
  if (LP.zone === 'cats') { LP.zone = 'grid'; tick(700, .03); return lpFocus(); }
  const g = lpItems()[LP.i];
  if (!g) return;
  const from = lpState();
  closeLibraryPage();
  showInRow(g);
  openDetails(g, from);
}
$('#libpage').addEventListener('click', e => {
  const c = e.target.closest('.al-tab'), h = e.target.closest('.lp-hit');
  if (c) { LP.cat = +c.dataset.c; LP.i = 0; renderLibraryPage(); }
  else if (h) { LP.zone = 'grid'; LP.i = +h.dataset.i; lpOpen(); }
  else if (e.target.closest('.lp-sort')) lpSort();
  else if (e.target.closest('.lp-find')) openSearch(LP.mode);
});

// ---------- album: Still screenshots and recordings taken while playing ----------
// The helper ties every Still capture made during a game to that game. Two views (Screenshots, Gameplay), each
// grouped by game, newest first. LB/RB switch views; A opens the full-screen viewer.
const AL = { open: false, all: [], view: 'screenshot', i: 0, still: true };
const albumItems = () => AL.all.filter(c => c.kind === AL.view);
const fmtClock = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
const fmtWhen = t => `${fmtDate(t)} · ${new Date(t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true, ...zoneOpt() })}`;
async function openAlbum() {
  if (!API) return toast('Start the frontend with Start Frontend.bat to see your album');
  AL.open = true; AL.i = 0;
  document.body.classList.add('album-open');
  tick(600, .07);
  try { const r = await api('/api/album'); AL.all = r.captures; AL.still = r.still; } catch (e) { return toast(e.message); }
  if (AL.open) renderAlbum();
}
function closeAlbum() { AL.open = false; document.body.classList.remove('album-open'); tick(420, .06); }
function albumTab(dir) {
  const next = dir > 0 ? 'video' : 'screenshot';
  if (next !== AL.view) { AL.view = next; AL.i = 0; tick(760, .04); renderAlbum(); }
}
function renderAlbum() {
  const count = k => AL.all.filter(c => c.kind === k).length;
  $('#albumpage .al-tabs').innerHTML = [['screenshot', 'Screenshots'], ['video', 'Gameplay']].map(([k, label]) =>
    `<div class="al-tab${AL.view === k ? ' sel' : ''}" data-k="${k}">${label}<span>${count(k)}</span></div>`).join('');
  const items = albumItems();
  let html = '', game = null;
  items.forEach((c, i) => {
    if (c.game !== game) { game = c.game; html += `<div class="al-game">${esc(c.title)}<span>${items.filter(x => x.game === game).length}</span></div>`; }
    html += `<div class="al-card${c.kind === 'video' ? ' video' : ''}" data-i="${i}" style="animation-delay:${Math.min(i, 16) * 30}ms">
      <div class="al-img" style="background-image:url(&quot;/api/album/thumb?id=${encodeURIComponent(c.id)}&quot;)"></div>
      <div class="al-meta">${esc(fmtWhen(c.created))}${c.kind === 'video' && c.duration ? ` · ${fmtClock(c.duration)}` : ''}</div>
      <button class="al-more" aria-label="More: open or delete">${icon('more')}</button></div>`;
  });
  const how = 'In a game, use the overlay, or hold View and press RB for a screenshot and View + LB to start or stop recording.';
  $('#albumpage .al-grid').innerHTML = html || `<div class="d-empty">${AL.still ? (AL.view === 'video' ? 'No gameplay recordings yet.' : 'No screenshots yet.') : 'Take a screenshot or record a video from the in-game menu while you play, and it shows up here.'}</div>`;
  $('#albumpage .np-sub').textContent = how + (items.length ? ' To delete one, press Y or its ⋯ button.' : '');
  albumFocus();
}
function albumFocus() {
  document.querySelectorAll('#albumpage .al-card').forEach(e => e.classList.toggle('sel', +e.dataset.i === AL.i));
  const card = $('#albumpage .al-card.sel'), grid = $('#albumpage .al-grid');
  if (card && card.offsetTop < grid.offsetTop + grid.clientHeight / 2 && card === grid.querySelector('.al-card')) grid.scrollTop = 0;  // keep the first heading
  else card?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
// ⋯ on a card (or Y): open it or delete it. Deleting asks once more, and moves the file to the Recycle Bin.
function albumMore(i = AL.i) {
  const c = albumItems()[i];
  if (!c) return;
  AL.i = i; albumFocus();
  const what = c.kind === 'video' ? 'video' : 'screenshot';
  sysMenu(c.kind === 'video' ? 'Gameplay video' : 'Screenshot', [
    { label: c.kind === 'video' ? 'Play' : 'View', ic: c.kind === 'video' ? ICON_PLAY : icon('image'), run: albumOpen },
    { label: `Delete this ${what}`, ic: icon('close'), warn: true, run: () => setTimeout(() => albumDelete(c), 0) },
  ]);
}
function albumDelete(c = albumItems()[AL.i], after) {
  if (!c) return;
  const what = c.kind === 'video' ? 'video' : 'screenshot';
  sysMenu(`Delete this ${what}?`, [{ label: 'Cancel', ic: icon('back'), run: () => {} }, { label: 'Move to Recycle Bin', ic: icon('close'), warn: true, run: async () => {
    try { await api('/api/album/delete', { id: c.id }); } catch (e) { return toast(/404/.test(e.message) ? 'This needs the latest frontend update.' : e.message); }
    AL.all = AL.all.filter(x => x.id !== c.id);
    AL.i = clamp(AL.i, 0, Math.max(0, albumItems().length - 1));
    if (AL.open) renderAlbum();
    after?.();
    toast(`Moved to the Recycle Bin`);
  } }]);
}
// The viewer showing your own captures: ⋯ (or Y) deletes the one on screen, and moves on to the next
function viewerMore() {
  const m = V.items[V.i];
  if (!m?.capture) return;
  const c = AL.all.find(x => x.id === m.capture);
  if (!c) return;
  albumDelete(c, () => {
    V.items = V.items.filter(x => x.capture !== c.id);
    if (!V.items.length) return closeViewer();
    openViewer(Math.min(V.i, V.items.length - 1), V.items);
  });
}
// Cards sit in sections (one per game), so up/down goes to the nearest card above or below by position. Rows are told
// apart by half a card's height: the selected card is lifted a little, which isn't a row of its own.
function albumMove(dx, dy) {
  const cards = [...document.querySelectorAll('#albumpage .al-card')];
  const cur = cards.find(e => +e.dataset.i === AL.i);
  if (!cur) return;
  let n = AL.i;
  if (dx) n = clamp(AL.i + dx, 0, cards.length - 1);
  else {
    const r = cur.getBoundingClientRect(), cx = r.left + r.width / 2, half = r.height / 2;
    const rows = cards.map(e => e.getBoundingClientRect()).map((b, j) => ({ j, top: b.top, cx: b.left + b.width / 2 }))
      .filter(b => dy > 0 ? b.top > r.top + half : b.top < r.top - half);
    if (rows.length) {
      const rowTop = dy > 0 ? Math.min(...rows.map(b => b.top)) : Math.max(...rows.map(b => b.top));
      n = rows.filter(b => Math.abs(b.top - rowTop) < half).sort((a, b) => Math.abs(a.cx - cx) - Math.abs(b.cx - cx))[0].j;
    }
  }
  if (n !== AL.i) { AL.i = n; tick(700, .04); albumFocus(); }
}
function albumOpen() {
  const items = albumItems();
  if (!items[AL.i]) return;
  openViewer(AL.i, items.map(c => ({ kind: c.kind === 'video' ? 'video' : 'image', badge: c.kind === 'video' ? 'Gameplay' : 'Screenshot',
    thumb: `/api/album/thumb?id=${encodeURIComponent(c.id)}`, src: `/api/album/file?id=${encodeURIComponent(c.id)}`,
    label: `${c.title} · ${fmtWhen(c.created)}`, capture: c.id })));
}
$('#albumpage').addEventListener('click', e => {
  const t = e.target.closest('.al-tab'), c = e.target.closest('.al-card');
  if (c && e.target.closest('.al-more')) return albumMore(+c.dataset.i);
  if (t) { AL.view = t.dataset.k; AL.i = 0; renderAlbum(); }
  else if (c) { AL.i = +c.dataset.i; albumFocus(); albumOpen(); }
});

// ---------- quick menu (Y / O / right-click) ----------
// A blurred overlay with the game's cover and a vertical list of big options.
const Q = { open: false, game: null, i: 0, items: [] };
function quickItems(g) {
  const svg = n => n === 'play' ? ICON_PLAY : icon(n);
  return [  // no Play: A on the cover (or the details page) starts a game, so Y then A never starts one by mistake
    ...(RUN.has(g.id) ? [{ label: closeAsk === g.id ? 'Press A again to close' : 'Close game', ic: svg('close'), warn: true, stay: closeAsk !== g.id, run: () => askClose(g) }] : []),
    ...(D.open ? [] : [{ label: 'Game details', ic: svg('info'), run: () => openDetails(g) }]),
    { label: g.favorite ? 'Remove from Favourites' : 'Add to Favourites', ic: svg('star'), run: () => setFavorite(g, !g.favorite) },
    { label: 'Collections', ic: svg('library'), run: () => openCollections(g) },
    { label: 'Artwork', ic: svg('image'), run: () => openArtMenu(g) },
    { label: 'Rename', ic: svg('keyboard'), run: () => renameGame(g) },
    ...(g.renamed ? [{ label: 'Restore original name', ic: svg('reset'), run: () => setGameName(g, '') }] : []),
    ...(g.source !== 'Emulators' || g.appPath ? [{ label: 'App location', ic: svg('folder'), run: () => openLocationMenu(g) }] : []),
    { label: g.hidden ? 'Unhide game' : 'Hide game', ic: svg(g.hidden ? 'eye' : 'eyeoff'), run: () => setHidden(g, !g.hidden) },
  ];
}
function openArtMenu(g) {
  const svg = icon;
  sysMenu('Artwork', [
    { label: 'Change cover', ic: svg('image'), run: () => openGame(g, 'cover') },
    { label: 'Change logo', ic: svg('image'), run: () => openGame(g, 'logo') },
    { label: 'Change background', ic: svg('wide'), run: () => openGame(g, 'hero') },
    ...(g.custom ? [{ label: 'Reset cover', ic: svg('reset'), run: () => resetArt(g, 'cover') }] : []),
    ...(g.customLogo ? [{ label: 'Reset logo', ic: svg('reset'), run: () => resetArt(g, 'logo') }] : []),
    ...(g.customHero ? [{ label: 'Reset background', ic: svg('reset'), run: () => resetArt(g, 'hero') }] : []),
    { label: `Full-screen game art: ${S.artBg ? 'On' : 'Off'}`, ic: svg('wide'), run: toggleArtBg },
  ]);
}
function openLocationMenu(g) {
  sysMenu('App location', [  // emulated games start in their console's emulator (Settings › Systems); an old override can still go
    ...(g.source === 'Emulators' ? [] : [{ label: 'Change app location', ic: icon('folder'), run: () => changeAppLocation(g) }]),
    ...(g.appPath ? [{ label: 'Restore default location', ic: icon('reset'), run: () => changeAppLocation(g, true) }] : []),
  ]);
}
// Home background: the selected game's art full screen, or the night scenery (also in Settings › Artwork & info).
async function toggleArtBg() {
  try { const r = await api('/api/options', { artBackground: !S.artBg }); S.artBg = r.options.artBackground; }
  catch (e) { return toast(e.message); }
  applyBackgroundMode(); toast(S.artBg ? 'Full-screen game art on' : 'Night scenery on');
}
function openQuick(g) {
  if (!g) return;
  Object.assign(Q, { open: true, game: g, i: 0, items: quickItems(g) });
  const cover = $('#quick .q-cover');
  cover.style.setProperty('--c', colorOf(g));
  cover.style.backgroundImage = g.cover ? `url("${g.coverAnim || g.cover}")` : 'none';
  cover.innerHTML = g.cover ? '' : `<div class="ph">${esc(g.title)}</div>`;
  $('#quick .q-meta').textContent = [g.system || g.group, g.installed === false ? 'Not installed' : '', g.minutes ? fmtTime(g.minutes) + ' played' : ''].filter(Boolean).join(' · ');
  $('#quick .q-title').textContent = g.title;
  $('#quick .q-list').innerHTML = Q.items.map((it, j) => `<div class="q-item${it.warn ? ' warn' : ''}" data-i="${j}" style="animation-delay:${60 + j * 35}ms">${it.ic}<span>${esc(it.label)}</span></div>`).join('');
  $('#quick').classList.add('sys');  // every menu here is the same side panel
  $('#quick .sys-info').innerHTML = ''; $('#quick .sys-time').innerHTML = '';
  quickFocus();
  document.body.classList.add('quick-open');
  tick(600, .07);
}
function closeQuick() { Q.open = false; document.body.classList.remove('quick-open'); tick(420, .06); }
function quickFocus() {
  document.querySelectorAll('#quick .q-item').forEach((e, j) => e.classList.toggle('sel', j === Q.i));
  $('#quick .q-item.sel')?.scrollIntoView({ block: 'nearest' });
}
function quickMove(dy) { const n = clamp(Q.i + dy, 0, Q.items.length - 1); if (n !== Q.i) { Q.i = n; tick(640, .04); quickFocus(); } }
function quickActivate() { const it = Q.items[Q.i]; tick(880, .08); if (it?.stay) return it.run(); closeQuick(); it?.run(); }  // stay: the menu stays open
// The game's menu again with fresh labels (Close game asking for a second press), in place
function quickRelabel() {
  if (!Q.open || !Q.game?.id) return;
  Q.items = quickItems(Q.game);
  document.querySelectorAll('#quick .q-item span').forEach((s, j) => { if (Q.items[j]) s.textContent = Q.items[j].label; });
}
$('#quick').addEventListener('click', e => {
  const it = e.target.closest('.q-item');
  if (it) { Q.i = +it.dataset.i; return quickActivate(); }
  if (!e.target.closest('.q-inner')) closeQuick();
});

// ---------- Downloads and Friends pages ----------
const HUB = { open: false, kind: '', i: 0, items: [], error: '', timer: 0, loading: false };
const gb = n => (n / 1073741824).toFixed(n > 10737418240 ? 0 : 1) + ' GB';
function statsItems() {
  return LIB.filter(g => !g.hidden && g.minutes).sort((a, b) => b.minutes - a.minutes).slice(0, 40)
    .map(g => ({ id: g.id, title: g.title, cover: g.cover, done: 0, total: 0, status: `${fmtTime(g.minutes)} · ${platformOf(g)}${g.lastPlayed ? ' · ' + fmtDate(g.lastPlayed) : ''}` }));
}
async function openHub(kind) {
  clearTimeout(HUB.timer);  // a Friends or Downloads refresh still pending would otherwise run as 'stats'
  if (kind === 'stats') {
    Object.assign(HUB, { open: true, kind, i: 0, items: statsItems(), error: '', loading: false });
    document.body.classList.add('hub-open'); tick(600, .07);
    return renderHub();
  }
  if (!API) return toast('Start the frontend with Start Frontend.bat first');
  Object.assign(HUB, { open: true, kind, i: 0, items: [], error: '', loading: true });
  document.body.classList.add('hub-open'); tick(600, .07); renderHub(); refreshHub();
}
function closeHub() { HUB.open = false; clearTimeout(HUB.timer); document.body.classList.remove('hub-open'); tick(420, .06); }
async function refreshHub() {
  const kind = HUB.kind;
  let r, error = '';
  try { r = await api('/api/' + kind); } catch (e) { error = /404/.test(e.message) ? 'This needs the latest frontend update.' : e.message; }
  if (!HUB.open || kind !== HUB.kind) return;  // closed, or another hub opened meanwhile: this answer (and its next refresh) is over
  if (r) { HUB.items = r.items; HUB.error = r.error || ''; } else HUB.error = error;
  HUB.loading = false;
  HUB.i = clamp(HUB.i, 0, Math.max(0, HUB.items.length - 1));
  renderHub();
  clearTimeout(HUB.timer);
  HUB.timer = setTimeout(refreshHub, kind === 'downloads' ? 3000 : 60000);
}
function hubRow(it, i) {
  if (HUB.kind === 'friends') return `<div class="hub-row${it.online ? '' : ' off'}" data-i="${i}"><img class="hub-face" src="${esc(it.avatar)}" alt="">
    <div class="hub-text"><div class="hub-name">${esc(it.name)}</div><div class="hub-sub${it.game ? ' playing' : ''}"><span class="hub-dot"></span>${esc(it.status)}</div></div></div>`;
  const pct = it.total ? Math.round(it.done / it.total * 100) : 0;
  return `<div class="hub-row" data-i="${i}"><div class="hub-art">${it.cover ? `<img src="${esc(it.cover)}" alt="">` : icon('download')}</div>
    <div class="hub-text"><div class="hub-name">${esc(it.title)}</div><div class="hub-sub">${esc(it.status)}${it.total ? ` · ${gb(it.done)} of ${gb(it.total)}` : ''}</div>
    ${it.total ? `<div class="hub-bar"><i style="width:${pct}%"></i></div>` : ''}</div></div>`;
}
function renderHub() {
  const friends = HUB.kind === 'friends', stats = HUB.kind === 'stats', on = HUB.items.filter(f => f.online).length;
  const played = LIB.filter(g => !g.hidden && g.minutes), total = played.reduce((n, g) => n + g.minutes, 0);
  $('#hubpage h1').textContent = friends ? 'Friends' : stats ? 'Play Stats' : 'Downloads';
  $('#hubpage .np-sub').textContent = stats ? `${Math.round(total / 60).toLocaleString('en-US')} hours across ${played.length} games`
    : friends ? (HUB.items.length ? `${on} online of ${HUB.items.length}` : 'Your Steam friends') : HUB.items.length ? 'Press A to pause, resume or reorder them in Steam' : 'Steam downloads and games being unpacked';
  $('#hubpage .hub-grid').innerHTML = HUB.items.map(hubRow).join('')
    || `<div class="d-empty">${esc(HUB.loading ? 'Loading…' : HUB.error || (friends ? 'No friends to show.' : stats ? 'Play a game and it will show up here.' : 'Nothing is downloading.'))}</div>`;
  hubFocus();
}
const hubConnects = () => HUB.kind === 'friends' && !HUB.items.length && !HUB.loading;  // no friends to show: A goes to Steam's account page
function hubFocus() {
  document.querySelectorAll('#hubpage .hub-row').forEach(e => e.classList.toggle('sel', +e.dataset.i === HUB.i));
  $('#hubpage .hub-row.sel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
function hubMove(dx, dy) {
  const rows = [...document.querySelectorAll('#hubpage .hub-row')], cols = rows.filter(e => e.offsetTop === rows[0]?.offsetTop).length || 1;  // 1-3 by screen shape
  const n = clamp(HUB.i + dx + dy * cols, 0, Math.max(0, HUB.items.length - 1));
  if (n !== HUB.i) { HUB.i = n; tick(700, .03); hubFocus(); }
}
function openFriendMenu(f) {
  sysMenu(f.name, [{ label: 'Send message', ic: icon('news'), run: () => messageFriend(f) }]);
  $('#quick .sys-info').innerHTML = infoRow('Status', f.status);
}
async function messageFriend(f) {
  try { await api('/api/friends/message', { id: f.id, name: f.name }); toast(`Opening Steam chat with ${f.name}`, 3000); }
  catch (e) { toast(/404/.test(e.message) ? 'This needs the latest frontend update.' : e.message); }
}
function hubOpen() {
  if (hubConnects()) return connectSteam();
  if (HUB.kind === 'friends') { const f = HUB.items[HUB.i]; return f && openFriendMenu(f); }
  // Steam has no way for another app to pause or reorder one download: its own Downloads page does that
  if (HUB.kind === 'downloads') return HUB.items.length && api('/api/steam/downloads', {}).then(() => toast('Opened Steam’s Downloads', 3000), e => toast(e.message));
  const g = HUB.kind !== 'friends' && LIB.find(x => x.id === HUB.items[HUB.i]?.id);
  if (!g) return;
  closeHub(); openDetails(g);
}
$('#hubpage').addEventListener('click', e => { const r = e.target.closest('.hub-row'); if (r) { HUB.i = +r.dataset.i; hubFocus(); hubOpen(); } else if (e.target.closest('.d-empty') && hubConnects()) connectSteam(); });

// ---------- Quick Access: the Steam button (double-press or hold) or View, on the frontend ----------
const SP = { open: false, i: 0, rows: [], volume: null, muted: false, song: null, active: 0, p: 0, m: 1, confirm: null, battery: null, friends: '' };
// The music controls (previous, play/pause, next), as in the in-game menu: Windows' media keys, so any player answers them.
// The player's album art stands in for the note when it has some.
const ICON_MUSIC = icon('music');
const MEDIA_ICONS = [
  '<svg viewBox="0 0 24 24"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg>',
  ['<svg viewBox="0 0 24 24"><path d="M7 4v16l13-8z"/></svg>', '<svg viewBox="0 0 24 24"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>'],
  '<svg viewBox="0 0 24 24"><path d="M16 5h2v14h-2zM4 5v14l11-7z"/></svg>'];
async function sysMedia() {
  const action = ['media-prev', 'media-play', 'media-next'][SP.m];
  try { await api('/api/overlay', { action }); } catch (e) { return toast(e.message); }
  if (action === 'media-play' && SP.song) { SP.song.playing = !SP.song.playing; renderSys(); }  // shown at once; Windows' word follows
  clearTimeout(sysMedia.t);
  sysMedia.t = setTimeout(() => api('/api/nowplaying').then(s => { if (SP.open) { SP.song = s?.title ? s : null; renderSys(); } }).catch(() => {}), 900);
}
function sysRows() {
  // Friends opens inside Quick Access, like a console's friends list: A messages one, B goes back
  if (SP.view === 'friends') return [{ head: `Friends · ${(SP.friendItems || []).filter(f => f.online).length} online` },
    ...(SP.friendItems || []).map(f => ({ face: f.avatar, ic: 'user', label: f.name, sub: f.status, dim: !f.online, run: () => messageFriend(f) })),
    { ic: 'back', label: 'Back', run: () => sysView('') }];
  const now = LIB.find(g => RUN.has(g.id));
  // grouped like a console's quick menu: a heading over each set, skipped when moving
  const group = (head, rows) => rows.length ? [{ head }, ...rows] : [];
  return [
    ...group('Games', [
    ...(now ? [{ ic: 'pad', label: now.title, sub: 'Running · A resumes', run: () => { closeSys(); resumeGame(now); } }] : []),
    ]),
    ...group('Sound', [
    ...(SP.volume === null ? [] : [{ id: 'volume', run: () => setSound({ mute: !SP.muted }) }]),
    ...(SP.song ? [{ id: 'music', run: sysMedia }] : []),  // the song that's playing
    // where the sound plays: A (or left / right) moves to the next speaker, headset or TV
    ...(SP.qa?.outputs?.length > 1 ? [{ id: 'output', ic: /head|ear|airpod|buds/i.test(SP.qa.outputs.find(o => o.on)?.name || '') ? 'headset' : 'speaker', label: 'Sound output',
      sub: (SP.qa.outputs.find(o => o.on)?.name || 'Choose one').replace(/\s*\([^)]*\)\s*$/, ''), value: `${SP.qa.outputs.findIndex(o => o.on) + 1} of ${SP.qa.outputs.length}`, run: () => sysOutput(1) }] : []),
    // Bluetooth headphones and speakers show up above once they're connected; this connects one that's paired but off
    { ic: 'headset', label: 'Bluetooth audio', sub: 'Connect Bluetooth headphones or a speaker, then choose it in Sound output', run: () => qaDo({ action: 'bluetooth' }).then(() => toast('Opened Windows’ Bluetooth settings')) },
    ]),
    ...group('Controllers', [
    // each controller's battery; a wireless Xbox-style one can be turned off from here
    ...(SP.qa?.pads || []).map((p, n) => ({ ic: 'pad', label: (SP.qa.pads.length > 1 ? `Controller ${n + 1}` : 'Controller'), value: p.battery ? p.battery[0].toUpperCase() + p.battery.slice(1) : '',
      sub: p.wireless ? (SP.confirm === 'pad' + p.slot ? 'Press A again to turn it off' : 'A turns it off') : p.battery === 'wired' ? 'Plugged in' : '',
      run: p.wireless ? () => SP.confirm === 'pad' + p.slot ? qaDo({ action: 'padoff', slot: p.slot }).then(() => toast('Controller turned off')) : (SP.confirm = 'pad' + p.slot, renderSys()) : null })),
    ...(SP.qa?.steamBattery != null ? [{ ic: 'pad', label: 'Steam Controller', value: `${SP.qa.steamBattery}%`, sub: 'Battery' }] : []),
    ]),
    ...group('Network and display', [
    ...(SP.qa?.wifi ? [{ ic: 'wifi', label: 'Wi-Fi', sub: SP.qa.wifi.connected ? `${SP.qa.wifi.name}${SP.qa.wifi.signal != null ? ` · ${SP.qa.wifi.signal}% signal` : ''}` : 'Not connected · A to choose a network',
      run: () => qaDo({ action: 'wifi' }).then(() => toast('Opened Windows’ Wi-Fi list')) }] : []),
    { ic: SP.qa?.dnd ? 'bellOff' : 'bell', label: 'Do not disturb', value: SP.qa?.dnd ? 'On' : 'Off', sub: 'Hides Windows’ notification pop-ups while you play', run: () => qaDo({ action: 'dnd', on: !SP.qa?.dnd }) },
    ...(SP.qa?.brightness != null ? [{ id: 'bright', ic: 'sun', label: 'Brightness', value: `${SP.qa.brightness}%`, sub: 'Left and right change it', run: () => {} }] : []),
    ]),
    ...group('More', [
    { ic: 'friends', label: 'Friends', sub: SP.friends || '', value: SP.friendItems?.length ? '›' : '', run: () => SP.friendItems?.length ? sysView('friends') : (closeSys(), closePages(), openHub('friends')) },
    { ic: 'settings', label: 'Settings', run: () => { closeSys(); closePages(); openPanel(); } },

    ]),
    { id: 'power', run: () => powerPick(powerChoices()[SP.p]) },  // the power buttons, always last
  ];
}
// Quick Access can open over a full page (News, Library, Search, Album...). What it opens takes that page's place: left
// underneath, the page would be drawn over it or take its input.
function closePages() {
  if (SR.open) closeSearch();
  if (R.open) closeReader();
  if (AP.open) closeAchievements();
  if (NP.open) closeNewsPage();
  if (LP.open) closeLibraryPage();
  if (AL.open) closeAlbum();
}
function renderSys() {
  SP.rows = sysRows();
  SP.i = clamp(SP.i, 0, SP.rows.length - 1);
  while (SP.rows[SP.i]?.head && SP.i < SP.rows.length - 1) SP.i++;
  const z = PROFILE.timezone;
  $('#syspanel .sp-time').innerHTML = `<b>${esc(timeIn(z))}</b><span>${esc(dateIn(z))}${SP.battery != null ? ` · Controller ${SP.battery}%` : ''}</span>`;
  SP.p = clamp(SP.p || 0, 0, powerChoices().length - 1);
  $('#syspanel .sp-list').innerHTML = SP.rows.map((r, i) => r.head ? `<div class="sp-head">${esc(r.head)}</div>` : r.id === 'volume'
    ? `<div class="sp-row sp-vol" data-i="${i}">${icon(SP.muted ? 'mute' : 'volume')}<div class="sp-text"><div>Volume<b>${SP.muted ? 'Muted' : SP.volume}</b></div><div class="hub-bar"><i style="width:${SP.muted ? 0 : SP.volume}%"></i></div></div></div>`
    : r.id === 'music'
    ? `<div class="sp-row sp-music" data-i="${i}">${SP.song.art ? `<img class="sp-art" src="${esc(SP.song.art)}" alt="" onerror="this.replaceWith(document.createRange().createContextualFragment(ICON_MUSIC))">` : icon('music')}<div class="sp-text"><div>${esc(SP.song.title)}</div><small>${esc([SP.song.playing === false ? 'Paused' : 'Now playing', SP.song.artist].filter(Boolean).join(' · '))}</small></div>`
      + `<div class="sp-mbtns">${[MEDIA_ICONS[0], MEDIA_ICONS[1][SP.song.playing === false ? 0 : 1], MEDIA_ICONS[2]].map((svg, j) => `<span class="sp-mb${j === SP.m ? ' on' : ''}" data-j="${j}">${svg}</span>`).join('')}</div></div>`
    : r.id === 'power'
    ? `<div class="sp-row sp-power" data-i="${i}">${powerChoices().map((p, j) => `<div class="sp-pw${j === SP.p ? ' on' : ''}${SP.confirm === p.id ? ' warn' : ''}" data-j="${j}">${icon(p.ic)}<span>${SP.confirm === p.id ? 'Press A again' : p.label}</span></div>`).join('')}</div>`
    : `<div class="sp-row${r.run ? '' : ' info'}${r.cover ? ' sp-game' : ''}${r.face ? ' sp-friend' : ''}${r.dim ? ' off' : ''}" data-i="${i}">${r.cover || r.face ? `<img class="sp-art" src="${esc(r.cover || r.face)}" alt="">` : icon(r.ic)}<div class="sp-text">${r.over ? `<small>${esc(r.over)}</small>` : ''}<div>${esc(r.label)}</div>${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</div>${r.value ? `<b class="sp-value">${esc(r.value)}</b>` : ''}</div>`).join('');
  sysFocus();
}
function sysFocus() { document.querySelectorAll('#syspanel .sp-row').forEach(e => e.classList.toggle('sel', +e.dataset.i === SP.i)); $('#syspanel .sp-row.sel')?.scrollIntoView({ block: 'nearest' }); }
async function openSys() {
  SP.open = true; SP.i = 0; SP.p = 0; SP.confirm = null; SP.view = '';
  document.body.classList.add('sys-open'); tick(600, .07); renderSys();
  api('/api/padraw').then(r => { SP.battery = r.battery; if (SP.open) renderSys(); }).catch(() => {});
  api('/api/qa').then(r => { SP.qa = r; if (SP.open) renderSys(); }).catch(() => {});
  api('/api/friends').then(r => {
    const on = (r.items || []).filter(f => f.online), busy = on.find(f => f.game);
    SP.friends = !r.items?.length ? '' : busy ? `${busy.name} is playing ${busy.game}` : on.length ? `${on.length} online` : 'Nobody online';
    SP.friendItems = (r.items || []).slice().sort((x, y) => (y.online - x.online) || (!!y.game - !!x.game));
    if (SP.open) renderSys();
  }).catch(() => {});
  const [vol, song, dl] = await Promise.all([api('/api/volume').catch(() => null), api('/api/nowplaying').catch(() => null), api('/api/downloads').catch(() => null)]);
  if (!SP.open) return;
  if (vol) { SP.volume = vol.volume; SP.muted = vol.muted; }
  SP.song = song?.title ? song : null;
  SP.active = dl?.items?.length || 0;
  renderSys();
}
function closeSys() { SP.open = false; document.body.classList.remove('sys-open'); tick(420, .06); }
function sysMove(dir) {
  let n = clamp(SP.i + dir, 0, SP.rows.length - 1);
  while (SP.rows[n]?.head && n > 0 && n < SP.rows.length - 1) n += dir;  // headings aren't stops
  if (SP.rows[n]?.head) n = SP.i;
  if (n !== SP.i) { SP.i = n; tick(700, .03); if (SP.confirm) { SP.confirm = null; renderSys(); } else sysFocus(); }
}
async function setSound(change) {
  try { const r = await api('/api/volume', change); SP.volume = r.volume; SP.muted = r.muted; renderSys(); tick(700, .03); } catch (e) { toast(e.message); }
}
function sysSide(dir) {
  const row = SP.rows[SP.i]?.id;
  if (row === 'volume') return setSound({ delta: dir * 5 });
  if (row === 'output') return sysOutput(dir);
  if (row === 'bright') return qaDo({ action: 'brightness', level: clamp((SP.qa.brightness || 0) + dir * 10, 5, 100) });
  if (row === 'music') { const n = clamp(SP.m + dir, 0, 2); if (n !== SP.m) { SP.m = n; tick(700, .03); renderSys(); } return; }
  if (row !== 'power') return;
  const n = clamp(SP.p + dir, 0, powerChoices().length - 1);
  if (n !== SP.p) { SP.p = n; SP.confirm = null; tick(700, .03); renderSys(); }
}
function sysView(v) { SP.view = v; SP.i = 0; tick(700, .05); renderSys(); }
async function qaDo(body) {
  try { SP.qa = await api('/api/qa', body); SP.confirm = null; tick(700, .03); renderSys(); } catch (e) { toast(e.message); }
}
function sysOutput(dir) {
  const o = SP.qa?.outputs || [], at = o.findIndex(x => x.on), next = o[(at + dir + o.length) % o.length];
  if (next) qaDo({ action: 'output', id: next.id }).then(() => toast(`Sound plays on ${next.name.replace(/\s*\([^)]*\)\s*$/, '')}`, 2500));
}
function sysOk() { const r = SP.rows[SP.i]; if (r?.run) { tick(880, .08); r.run(); } }
$('#syspanel').addEventListener('click', e => {
  const r = e.target.closest('.sp-row');
  const pw = e.target.closest('.sp-pw'), bar = e.target.closest('.sp-vol') && !e.target.closest('svg') && $('#syspanel .sp-vol .hub-bar').getBoundingClientRect();
  if (pw) SP.p = +pw.dataset.j;
  const mb = e.target.closest('.sp-mb');
  if (mb) SP.m = +mb.dataset.j;
  if (bar && r) {  // a tap on the bar sets the level there (as a step from now, which every helper understands); on the icon, mute
    SP.i = +r.dataset.i; sysFocus();
    return setSound({ delta: Math.round(clamp((e.clientX - bar.left) / bar.width, 0, 1) * 100) - SP.volume, ...(SP.muted && { mute: false }) });
  }
  if (r) { SP.i = +r.dataset.i; sysFocus(); sysOk(); } else if (e.target.id === 'syspanel') closeSys();
});

// ---------- libraries & accounts panel ----------
// A focus list driven by the same arrows / A / B as the home screen.
const P = { open: false, view: 'main', focus: 0, items: [], data: null, confirm: null, working: false };
// Settings is a full page: categories down the left, that category's options on the right.
// The same panel also shows the artwork picker as a dialog when opened for a game (P.game set).
const SETTINGS = [
  { id: 'profile', label: 'Profile', icon: 'user' },
  { id: 'accounts', label: 'Accounts', icon: 'link' },
  { id: 'libraries', label: 'Libraries', icon: 'library' },
  { id: 'systems', label: 'Systems', icon: 'pad' },
  { id: 'artwork', label: 'Artwork & info', icon: 'image' },
  { id: 'general', label: 'General', icon: 'sliders' },
  { id: 'pad', label: 'Controllers', icon: 'controllers' },
  { id: 'hidden', label: 'Hidden games', icon: 'eyeoff' },
  { id: 'about', label: 'About', icon: 'info' },
].filter(c => !(ON_ANDROID && c.id === 'accounts'));  // no store accounts on Android
const GAME_SERVICES = [
  { id: 'ea', name: 'EA app', logo: 'ea' },
  { id: 'ubisoft', name: 'Ubisoft Connect', logo: 'ubisoft' },
  { id: 'gog', name: 'GOG', logo: 'gogdotcom' },
  { id: 'rockstar', name: 'Rockstar Games', logo: 'rockstargames' },
  { id: 'battlenet', name: 'Battle.net', logo: 'battledotnet' },
];
const SUB_VIEW = { steam: 'accounts', epic: 'accounts', sgdb: 'accounts', ra: 'accounts', avatar: 'profile', timezone: 'profile', system: 'systems', 'add-system': 'systems', service: 'accounts' };  // pages opened from a category
const pageMode = () => !P.game && !P.setup;
// Sub-pages (connect Steam, pick an icon...) go back to whatever opened them: a Settings category or a setup step.
const subReturn = () => P.returnTo || SUB_VIEW[P.view] || 'accounts';
const catOf = v => SUB_VIEW[v] && SETTINGS.some(c => c.id === P.returnTo) ? P.returnTo : SUB_VIEW[v] || v;  // SteamGridDB from Artwork & info is under Artwork & info
// Settings > About: this version, and the newer one from the GitHub project's releases when there is one
function updateRows(u) {
  if (!u) return [];
  const ready = u.latest && u.state === 'ready';
  const note = u.off || u.error || { checking: 'Checking for a new version…', downloading: `Downloading version ${u.latest}…`,
    ready: `Version ${u.latest} is ready. It installs by itself when the frontend is closed or left alone for a few minutes.`, installing: `Installing version ${u.latest}…`,
    installed: `Version ${u.latest} is installed and takes over the next time the frontend opens` }[u.state]
    || (u.latest ? `Version ${u.latest} is available` : u.state === 'current' ? 'This is the newest version' : 'Looks for new versions every few hours');
  const nightly = u.channel === 'nightly';
  return [{ kind: 'info', label: `Version ${u.version}`, sub: note },
    // a once-a-day anonymous check-in, so the project can count how many copies are in use
    ...(u.off || !P.data?.options ? [] : [{ kind: 'row', label: 'Count this copy', value: onOff(P.data.options.usageCheckin),
      sub: 'Checks in once a day to show roughly how many people are using Ultra Front End. It only counts copies: nothing about you or your games is included',
      act: () => setOpt('usageCheckin') }]),
    // main releases, or the newest code built every night (and the releases too)
    ...(u.off ? [] : [{ kind: 'row', label: 'Updates', value: nightly ? 'Nightly' : 'Main',
      sub: nightly ? 'A build of the newest changes every night, before they’re released. Can have bugs. Choose to go back to Main'
        : 'Tested releases. Choose to get a build of the newest changes every night instead (can have bugs)',
      act: () => setChannel(nightly ? 'main' : 'nightly') }]),
    // one press: it checks, downloads, and the frontend opens again on the new version (never over a game)
    ...(u.off ? [] : [{ kind: 'row', label: u.latest ? `Update now to version ${u.latest}` : 'Check for updates',
      sub: u.latest ? 'The frontend closes and opens again on the new version' : 'If there’s a new version, it installs and the frontend opens again on it',
      act: () => updateNow('install') }])];
}
async function setChannel(channel) {
  let u;
  try { u = await api('/api/update', { action: 'channel', channel }); } catch (e) { return toast(e.message); }
  if (P.data) P.data.update = u;
  renderPanel();
  toast(channel === 'nightly' ? 'Nightly builds on: the newest one installs when the frontend is closed or left alone'
    : 'Back on Main: the main release installs when the frontend is closed or left alone', 6000);
}
async function updateNow(action) {
  let u;
  try { u = await api('/api/update', { action }); } catch (e) { return toast(e.message); }
  if (action === 'install') toast(u.latest ? `Updating to version ${u.latest}…` : 'Checking for a new version…', 4000);
  for (let i = 0; i < 120 && P.open && P.view === 'about' && ['checking', 'downloading', 'installing'].includes(u.state); i++) {  // show progress while About is open
    if (P.data) P.data.update = u;
    renderPanel();
    await new Promise(r => setTimeout(r, 2000));
    try { u = await api('/api/update'); } catch { break; }
  }
  if (P.data) P.data.update = u;
  renderPanel();
  // say how it went, so pressing it never looks like nothing happened
  toast(u.error || u.off || { current: 'You have the newest version', ready: `Version ${u.latest} is ready: choose Update now`,
    installed: `Version ${u.latest} takes over the next time the frontend opens`, checking: 'Still checking…', downloading: `Still downloading version ${u.latest}…` }[u.state]
    || (u.latest ? `Version ${u.latest} is available` : 'Couldn’t reach GitHub just now. Try again in a minute'), 5000);
}
// After an update, once: which version this is now
if (API) api('/api/update').then(u => {
  if (!u.updated) return;
  toast(`Updated to version ${u.updated.version}. See what’s new in News`, 6000);
  api('/api/update', { action: 'seen' }).catch(() => {});
}).catch(() => {});
if (API) api('/api/whatsnew/unseen').then(r => { if (r.unseen) { NEWS_DOT = true; drawButtons(); } }).catch(() => {});
// An update that arrives while the frontend is open waits for it to close (never mid-game): say so once, with the way to install it now
// and left alone for three minutes with no game running, it updates by itself and opens again (a handheld is rarely closed)
let readyShown = '', lastActive = Date.now();
['pointerdown', 'pointermove', 'keydown', 'wheel'].forEach(t => addEventListener(t, () => { lastActive = Date.now(); }, { passive: true }));
if (API) setInterval(async () => {
  if (RUN.size) return;  // never over a game
  try {
    const u = await api('/api/update');
    if (u.state !== 'ready' || !u.latest) return;
    if (Date.now() - lastActive > 180000) {
      toast(`Updating to version ${u.latest}…`, 4000);
      return api('/api/update', { action: 'install' }).catch(() => {});
    }
    if (readyShown !== u.latest && !(P.open && P.view === 'about')) {
      readyShown = u.latest;
      toast(`Version ${u.latest} is ready. Update now from Settings › About, or it installs when the frontend is left alone`, 8000);
    }
  } catch {}
}, 60000);
async function openPanel(view = P.cat || SETTINGS[0].id) {  // the category used last this session, or the first
  if (view === 'main') view = P.cat || SETTINGS[0].id;
  P.open = true; P.view = view; P.focus = 0; P.confirm = null; P.game = null; P.side = true;
  document.body.classList.add('panel-open');
  if (!API) { P.data = null; renderPanel(); return; }
  try { P.data = await api('/api/settings'); } catch (e) { toast(e.message); }
  renderPanel(); followQueue();
}
function closePanel() {
  P.open = false; P.game = null; P.mapping = false; P.setup = false; P.returnTo = null; P.lastFocus = {}; P.pick = null; P.listPlain = null;
  document.body.classList.remove('panel-open', 'settings-page', 'setup-mode'); document.activeElement?.blur?.();
  // what was typed belongs to this visit: kept, the next game's artwork search opened with this one's name in the box
  document.querySelectorAll('#panel input').forEach(i => i.remove());
}
const onOff = v => v ? 'On' : 'Off';
function panelItems() {
  const d = P.data;
  if (P.view === 'pad') return [
    { kind: 'note', label: 'Press buttons on your controller to check it’s detected. On a standard layout, Y (or △) opens a game’s quick menu and A (or ✕) selects.' },
    { kind: 'row', label: 'Set the quick-menu button', primary: P.mapping,
      sub: P.mapping ? 'Press the button you want now (for example Y)…  Esc cancels' : 'If Y does nothing, choose this, then press Y',
      value: S.optKey ? `Key: ${S.optKey === ' ' ? 'Space' : S.optKey}` : 'Y / O', act: () => { P.mapping = true; renderPanel(); } },
    { kind: 'html', html: '<div id="padlive" class="pnote padlive">Checking…</div>' },
    ...(API && ON_MAC ? [{ kind: 'row', label: 'Xbox button opens Ultra Front End', value: d?.homeOpensUs ? 'On' : 'Set up',  // macOS' own setting: only System Settings can change it
      sub: d?.homeOpensUs ? 'From anywhere, even when it’s closed. Change it in System Settings › Game Controllers'
        : 'Otherwise it opens Apple’s Games app. In System Settings › Game Controllers, set Press Home Button to Open to Other…, then Ultra Front End',
      act: () => api('/api/mac/controller-settings', {}).then(() => toast('Next to Press Home Button to Open, choose Other…, then Ultra Front End in Applications', 8000), e => toast(e.message)) }] : []),
    ...(API ? [{ kind: 'row', ic: icon('pad'), label: 'Controller tester', sub: 'See every button, trigger and stick respond live: Steam Controller, Xbox, DualSense, DualShock and others', act: openPadTester },
      ...(ON_MAC ? [] : [{ kind: 'row', label: 'Wii Remote motion from the Steam Controller', value: onOff(P.data?.options?.wiiMotion),  // Windows only
        sub: 'Shake and tilt in Dolphin. Adds keys to Wii Remote 1 in Dolphin’s settings (a copy of them is kept)', act: () => setOpt('wiiMotion').then(renderPanel) }])] : []),
  ];
  if (P.view === 'about') return [
    { kind: 'head', label: 'Ultra Front End' },
    { kind: 'note', label: ON_ANDROID ? 'A fullscreen, controller-friendly launcher for your Android games and emulators.' : 'A fullscreen, controller-friendly launcher for Steam, Epic, your own game folders, emulators and ports.' },
    ...updateRows(P.data?.update),
    ...(P.data ? emuUpdateRows(P.data) : []),  // the emulators it installed, beside the app's own updates
    // information only: these can't be highlighted, so A never seems to do nothing
    { kind: 'info', label: 'Your data', sub: `Libraries, accounts, artwork and play history are kept on ${HERE} only, in the frontend’s data folder.` },
    { kind: 'info', label: 'Artwork and info', sub: 'Steam, Epic, SteamGridDB, libretro and Wikipedia. Descriptions from Wikipedia are under CC BY-SA 4.0' },
    { kind: 'info', label: 'Trademarks', sub: 'All product names, logos and brands are the property of their owners and are used only to name platforms and stores. Ultra Front End is not affiliated with or endorsed by any of them. Valve, Steam and the Steam logo are trademarks of Valve Corporation.' },
    { kind: 'info', label: 'Open-source licences', sub: ON_ANDROID ? 'MIT. Built with AndroidX (Apache-2.0): see THIRD_PARTY_NOTICES.md and the licenses folder on the project’s GitHub page' : 'MIT. Built with Python, pywebview, Pillow and pystray (LGPL-3.0), among others: see THIRD_PARTY_NOTICES.md and the licenses folder on the project’s GitHub page' },
    { kind: 'info', label: 'Helper', sub: API ? `Running on ${HERE} (${location.host})` : 'Not running: start the frontend with Start Frontend.bat' },
    ...(API ? [{ kind: 'row', label: 'Run the setup guide again', sub: 'Name, icon, time zone, accounts and games', act: openSetup }] : []),
    ...(API && ON_MAC ? [  // on Windows this is in Settings › Apps (the installer registers it)
      { kind: 'head', label: 'Uninstall' },
      uninstallRow('uninstall-keep', false, 'Uninstall Ultra Front End', 'Moves the app to the Trash. Your settings, artwork and captures are kept, for if you install it again'),
      uninstallRow('uninstall-wipe', true, 'Uninstall and delete my settings', 'Also moves your settings, artwork, captures and recordings to the Trash. Emulators it installed stay'),
    ] : []),
  ];
  if (!API) return [{ kind: 'note', label: 'Start the frontend with "Start Frontend.bat" to add libraries and accounts. Opened as a plain file it can only show the demo games.' }];
  if (!d) return [{ kind: 'note', label: 'Loading…' }];
  const acc = d.accounts;
  const prof = d.profile || PROFILE;
  const typeName = { pc: 'PC games folder', roms: 'ROM folder', game: 'Single game', folder: 'Folder' };
  const removable = (key, label, sub, url, body, done = `Removed ${label}`, again = 'Press A / Enter again to remove') => ({ kind: 'row', key, label, sub: P.confirm === key ? again : sub, warn: P.confirm === key,
    act: () => P.confirm === key ? work(api(url, body), done) : (P.confirm = key, renderPanel()) });
  if (P.view === 'profile') return [
    { kind: 'html', html: `<div class="pprofile"><span class="avatar big">${avatarHTML(prof)}</span><div><div class="pp-name">${esc(prof.name || 'Player')}</div><div class="pp-sub">${esc(zoneName(prof.timezone))} · ${esc(timeIn(prof.timezone))}</div></div></div>` },
    { kind: 'input', id: 'pname', label: 'Your name', value: prof.name || '', placeholder: 'Shown in the top corner', max: NAME_MAX },
    { kind: 'row', label: 'Save name', act: () => saveProfile({ name: val('pname') }).then(() => { P.data.profile = PROFILE; toast('Name saved'); renderPanel(); }) },
    { kind: 'row', label: 'Profile icon', sub: 'Pick an icon or your own picture', value: 'Change', act: () => setView('avatar') },
    { kind: 'row', label: 'Time zone', sub: 'Used for the clock', value: zoneName(prof.timezone), act: () => setView('timezone') },
  ];
  if (P.view === 'avatar') return [
    { kind: 'note', label: 'Choose an icon, or use a picture from your PC.' },
    ...AVATARS.map(([id]) => ({ kind: 'thumb', html: `<span class="av-pick${prof.avatar === id ? ' on' : ''}">${avatarHTML({ avatar: id })}</span>`, act: () => pickAvatar(id) })),
    { kind: 'row', label: 'Use a picture…', sub: 'PNG, JPG, WEBP or GIF', act: () => work(api('/api/profile/picture', {})).then(r => { if (r && !r.cancelled) { PROFILE = r; P.data.profile = r; renderProfile(); setView(subReturn()); } }) },
    { kind: 'row', label: 'Use my initial', act: () => pickAvatar('') },
    { kind: 'row', label: 'Back', act: () => setView(subReturn()) },
  ];
  if (P.view === 'timezone') return [
    { kind: 'note', label: 'Choose where you are. The clock follows this time zone.' },
    ...['auto', ...TIMEZONES].map(z => ({ kind: 'row', label: zoneName(z), sub: z === 'auto' ? `Follows ${HERE}’s setting` : z.split('/')[0].replace('_', ' '),
      value: `${prof.timezone === z ? '✓  ' : ''}${timeIn(z)}`, act: () => saveProfile({ timezone: z }).then(() => { P.data.profile = PROFILE; setView(subReturn()); }) })),
  ];
  if (P.view === 'systems') {
    const mine = d.platforms.filter(p => p.chosen && p.group !== 'Other'), odd = d.platforms.filter(p => p.chosen && p.group === 'Other');
    return [
      ...emuUpdateRows(d),  // first, where it's seen: below a long list of systems it was missed
      { kind: 'head', label: 'Your systems' },
      ...(mine.length ? mine.map(p => ({ kind: 'row', key: 'sys-' + p.name, ...sysLogo(p.name), label: p.name,
        sub: [p.emulator ? p.emulator + (p.emulatorVersion ? ` ${p.emulatorVersion}` : '') : p.recommended ? `${p.recommended} not installed` : 'No emulator yet', `${p.count} game${p.count === 1 ? '' : 's'}`, p.bios?.label, jobText(p)].filter(Boolean).join(' · '),
        value: p.job?.state === 'installing' ? jobValue(p.job) : p.emulator ? 'Ready' : p.job?.state === 'waiting' ? 'Waiting' : 'Set up', ...jobBar(p), act: () => { P.system = p.name; setView('system'); } }))
        : [{ kind: 'note', label: 'No systems yet. Add the ones you play.' }]),
      // a ROMs subfolder named after no system: its games can't start until it's renamed
      ...odd.map(p => ({ kind: 'info', label: `ROMs › ${p.name}`, sub: 'Folder not recognised: rename it to a system’s name, for example SNES or Genesis', value: `${p.count} game${p.count === 1 ? '' : 's'}` })),
      { kind: 'row', key: 'sys-add', label: '+ Add a system', sub: ON_ANDROID ? 'Makes its folders in your ROMs folder' : 'Installs its emulator and makes its folders', act: () => setView('add-system') },
      { kind: 'row', ic: '⌕', label: 'Find installed emulators', sub: `Looks for emulators already on ${HERE}`, act: () => work(api('/api/emulators/find', {})).then(r => r && toast(r.found ? `Found ${r.found} emulator${r.found === 1 ? '' : 's'}` : 'No new emulators found', 3000)) },
    ];
  }
  if (P.view === 'add-system') {
    const rest = d.platforms.filter(p => !p.chosen && p.group !== 'Other');
    return [
      ...(rest.length ? groupRows(rest, p => ({ kind: 'row', key: 'add-' + p.name, ...sysLogo(p.name), label: p.name, value: 'Add',
        sub: !p.recommended ? 'Choose its program yourself' : p.emulator ? `${p.emulator} is already here` : p.install ? `Installs ${p.install}` : `${p.recommended}, from its project page`,
        act: async () => {
          const r = await work(api('/api/systems/add', { system: p.name }));
          if (!r) return;
          const q = r.platforms?.find(x => x.name === p.name);
          toast(q?.job && q.job.state !== 'ready' && !q.emulator ? `${p.name} added. Installing ${q.install}…` : `${p.name} added`, 4000);
          P.system = p.name; setView('system'); watchQueue();
        } })) : [{ kind: 'note', label: 'Every system is already in your list.' }]),
      { kind: 'row', label: 'Back', act: () => setView('systems') },
    ];
  }
  if (P.view === 'system') {
    const p = d.platforms.find(x => x.name === P.system);
    if (!p) return [{ kind: 'row', label: 'Back', act: () => setView('systems') }];
    const b = p.bios || { needs: [], folder: false, label: 'Nothing needed' }, job = p.job && p.job.state !== 'ready' && !p.emulator ? p.job : null;
    return [  // the page title names the system
      { kind: 'info', label: p.emulator ? `Plays in ${p.emulator}` : p.recommended ? `Emulator: ${p.recommended}` : 'No emulator chosen',
        sub: [p.emulatorVersion && `Version ${p.emulatorVersion}`, `${p.count} game${p.count === 1 ? '' : 's'}`, b.label, job && !p.install && jobText(p)].filter(Boolean).join(' · ') },  // (the Install row says it otherwise)
      ...(!p.emulator && p.install ? [{ kind: 'row', key: 'sys-install', ic: icon('pad'), label: `Install ${p.install}`, value: job && job.state !== 'failed' ? jobValue(job) : job ? 'Try again' : 'Install',
        sub: job ? jobText(p) : 'Downloads it from the emulator’s own project. It can take a few minutes: watch for Windows prompts.', ...jobBar(p),
        act: () => job && job.state !== 'failed' ? toast('It’s on its way', 2500) : work(api('/api/emulators/install', { system: p.name })).then(r => { if (r) { toast(`Installing ${p.install}…`, 3000); watchQueue(); } }) }] : []),
      ...(p.site ? [{ kind: 'row', ic: icon('link'), label: ON_ANDROID ? `Get ${p.recommended}` : `${p.recommended} project page`, sub: ON_ANDROID ? 'From Google Play, or from its own website' : p.site.replace(/^https:\/\/(www\.)?/, '').replace(/\/$/, ''), value: 'Open',
        act: () => api('/api/emulators/site', { system: p.name }).then(() => toast(ON_ANDROID ? 'Opened Google Play' : 'Opened in your browser', 3000), e => toast(e.message)) }] : []),
      // where it went: an install from here lands where its maker's installer puts it
      ...(p.emulator && p.emulatorDir ? [{ kind: 'row', key: 'sys-emudir', ic: icon('folder'), label: 'Open emulator folder', sub: p.emulatorDir, value: 'Open',
        act: () => api('/api/systems/emulator-folder', { system: p.name }).then(() => toast(ON_MAC ? 'Opened in Finder' : 'Opened in File Explorer', 3000), e => toast(e.message)) }] : []),
      { kind: 'row', key: 'sys-choose', ic: icon('folder'), label: 'Choose program', sub: p.emulator || `Select an emulator already on ${HERE}`, value: p.emulator ? 'Change' : 'Choose',
        act: () => work(api('/api/emulators/set', { system: p.name })).then(r => { const e = r?.platforms?.find(x => x.name === p.name)?.emulator; if (e) toast(`${p.name} games will start in ${e}`, 3000); }) },
      // a second A to stop, like every removal
      ...(p.emulator ? [removable(`stop-${p.name}`, `Stop using ${p.emulator}`, 'Its games won’t start until you choose a program again. The emulator stays installed', '/api/emulators/clear', { system: p.name },
        `${p.name} no longer uses ${p.emulator}`, 'Press A / Enter again to stop using it')] : []),
      { kind: 'head', label: 'BIOS and firmware' },
      ...(b.folder ? [
        ...b.needs.map(n => ({ kind: 'info', label: n.file, sub: n.why, value: n.found ? '✓ Found' : n.req ? 'Needed' : 'Optional' })),
        ...(b.note ? [{ kind: 'note', warn: !b.note.ok, label: b.note.msg }] : []),
        { kind: 'row', key: 'sys-bios', ic: icon('folder'), label: 'Open BIOS folder', sub: `Put the files in ROMs › ${p.name} › BIOS and they’re set up for ${p.recommended || 'its emulator'}`,
          act: () => api('/api/systems/bios', { system: p.name }).then(() => toast('Opened in File Explorer', 3000), e => toast(e.message)) },
      ] : [{ kind: 'info', label: `${p.recommended || 'Its emulator'} needs no BIOS or firmware`, value: 'Nothing needed' }]),
      ...(p.steps ? [{ kind: 'note', label: p.steps }] : []),
      ...(p.group === 'Other' ? [] : [{ kind: 'row', key: `rm-${p.name}`, warn: P.confirm === `rm-${p.name}`, label: 'Remove this system',
        sub: P.confirm === `rm-${p.name}` ? 'Press A / Enter again to remove' : `Your games, BIOS files and the emulator stay on ${HERE}`,
        act: () => P.confirm === `rm-${p.name}` ? work(api('/api/systems/remove', { system: p.name }), `Removed ${p.name}`).then(r => r && setView('systems')) : (P.confirm = `rm-${p.name}`, renderPanel()) }]),
      { kind: 'row', label: 'Back', act: () => setView('systems') },
    ];
  }
  if (P.view?.startsWith('setup-')) return setupItems(d, prof);
  if (P.view === 'hidden') {
    const hidden = LIB.filter(g => g.hidden).sort((a, b) => a.title.localeCompare(b.title));
    return [
      { kind: 'note', label: hidden.length ? 'Select a game to put it back in your library.' : 'No hidden games. Hide one from its quick menu (Y / O).' },
      ...hidden.map(g => ({ kind: 'row', label: g.title, sub: g.group, value: 'Unhide', act: () => unhideFromList(g) })),
    ];
  }
  if (P.view === 'steam') return [  // in the order they're done: get the key, fill in both, check privacy, connect
    { kind: 'note', label: 'Connecting your account shows every game you own on Steam, including ones that aren’t installed. Playing them still needs the Steam app.' },
    { kind: 'note', label: STEAM_KEY_STEPS },
    { kind: 'row', label: 'Open Steam’s API key page', sub: 'Opens steamcommunity.com/dev/apikey in your web browser', act: () => api('/api/accounts/steam/open', {}).then(() => toast('Opened in your browser')) },
    { kind: 'input', id: 'profile', label: 'Steam profile link or ID', value: d.steamSuggestedId || '', placeholder: 'https://steamcommunity.com/id/yourname' },
    { kind: 'input', id: 'key', label: 'Steam Web API key', value: '', placeholder: '32 letters and numbers' },
    { kind: 'note', label: 'Your game details must be public: Steam › Profile › Edit Profile › Privacy Settings › Game details: Public.' },
    { kind: 'row', label: 'Connect', primary: true, act: () => work(api('/api/accounts/steam', { profile: val('profile'), key: val('key') }), 'Steam connected', subReturn()) },
    { kind: 'row', label: 'Back', act: () => setView(subReturn()) },
  ];
  if (P.view === 'ra') return [
    { kind: 'note', label: 'RetroAchievements adds achievements to classic games. Sign in on retroachievements.org (free), then copy the Web API key from your settings page. Sign in to RetroAchievements inside your emulators too (RetroArch, DuckStation, PCSX2, Dolphin…) so they can unlock achievements while you play.' },
    { kind: 'row', label: 'Open RetroAchievements settings', sub: 'Opens in your web browser; the key is under "Keys"', act: () => api('/api/accounts/ra/open', {}).then(() => toast('Opened in your browser')) },
    { kind: 'input', id: 'rauser', label: 'Username', value: '', placeholder: 'Your RetroAchievements username' },
    { kind: 'input', id: 'rakey', label: 'Web API key', value: '', placeholder: 'Paste the key here' },
    { kind: 'row', label: 'Connect', primary: true, act: () => work(api('/api/accounts/ra', { user: val('rauser'), key: val('rakey') }), 'RetroAchievements connected', subReturn()) },
    { kind: 'row', label: 'Back', act: panelBack },
  ];
  if (P.view === 'sgdb') return [
    ...(P.game ? [{ kind: 'note', label: 'Changing a cover, logo or background uses SteamGridDB, a free artwork site. Connect it once here.' }] : []),
    { kind: 'note', label: 'Optional. Covers already come from Steam for Steam games and from libretro for emulated ones, with no account. SteamGridDB, a free community site, adds a choice of covers, backgrounds and logos for every game, animated covers and backgrounds, and covers for Switch games.' },
    { kind: 'note', label: '1. Choose “Open SteamGridDB” below. Its API page opens in your web browser.\n2. Sign in there, or make a free account if you don’t have one.\n3. On that page, choose “Generate API Key”, then copy the key.\n4. Come back here, select the box below and choose Paste on the keyboard (or press Ctrl+V), then Connect.' },
    { kind: 'row', label: 'Open SteamGridDB', sub: 'Its API page, in your web browser', act: () => api('/api/accounts/sgdb/open', {}).then(() => toast('Opened in your browser')) },
    { kind: 'input', id: 'sgdbkey', label: 'SteamGridDB API key', value: '', placeholder: 'Paste the key here' },
    { kind: 'row', label: 'Connect', primary: true, act: async () => { const r = await work(api('/api/accounts/sgdb', { key: val('sgdbkey') }), 'SteamGridDB connected', P.game ? 'game' : subReturn()); if (r && P.game) openArt(P.artKind); } },
    { kind: 'row', label: 'Back', act: panelBack },
  ];
  if (P.view === 'game') {
    const g = P.game, svg = n => n === 'play' ? ICON_PLAY : icon(n);  // same icons as the quick menu
    return [
      { kind: 'note', label: [g.group, g.installed === false ? 'Not installed' : '', g.minutes ? `${Math.round(g.minutes / 6) / 10} h played` : ''].filter(Boolean).join(' · ') },
      { kind: 'row', ic: svg('play'), label: g.installed === false ? 'Install' : 'Play', primary: true, act: () => { closePanel(); launchGame(g); } },
      ...(D.open ? [] : [{ kind: 'row', ic: svg('info'), label: 'Game details', sub: 'Playtime, news and more', act: () => { closePanel(); openDetails(g); } }]),
      ...(g.source === 'Emulators' ? [] : [{ kind: 'row', ic: svg('folder'), label: 'Change app location', sub: g.appPath || 'Choose a different game or launcher .exe', act: () => changeAppLocation(g) }]),
      ...(g.appPath ? [{ kind: 'row', ic: svg('reset'), label: 'Restore default app location', sub: 'Use the original launch option for this game', act: () => changeAppLocation(g, true) }] : []),
      { kind: 'row', ic: svg('image'), label: 'Change cover', sub: 'The art in the game row', act: () => artOrConnect('cover') },
      { kind: 'row', ic: svg('image'), label: 'Change logo', sub: 'The title logo on the game details screen', act: () => artOrConnect('logo') },
      ...(g.customLogo ? [{ kind: 'row', ic: svg('reset'), label: 'Reset logo', act: () => resetArt(g, 'logo') }] : []),
      { kind: 'row', ic: svg('wide'), label: 'Change background', sub: 'The art behind the game’s details screen', act: () => artOrConnect('hero') },
      ...(g.custom ? [{ kind: 'row', ic: svg('reset'), label: 'Reset cover', act: () => resetArt(g, 'cover') }] : []),
      ...(g.customHero ? [{ kind: 'row', ic: svg('reset'), label: 'Reset background', act: () => resetArt(g, 'hero') }] : []),
      { kind: 'row', ic: svg(g.hidden ? 'eye' : 'eyeoff'), label: g.hidden ? 'Unhide game' : 'Hide game', sub: g.hidden ? 'Put it back in your library' : 'Find it again in Settings › Hidden games', act: () => setHidden(g, !g.hidden) },
      { kind: 'row', ic: svg('back'), label: 'Back', act: closePanel },
    ];
  }
  if (P.view === 'art') {
    const A = P.art;
    return [
      ...(A.loading ? [{ kind: 'note', label: 'Loading artwork…' }]
        : A.grids.length ? A.grids.map(a => ({ kind: 'thumb', thumb: a.thumb, badge: a.animated ? 'Animated' : '', label: a.author ? `by ${a.author}` : '', act: () => chooseArt(a.url) }))
        : [{ kind: 'note', label: !A.current && A.games.length ? 'Which game is it? Pick it below, or search by name.'
          : `No ${P.artKind === 'logo' ? 'logos' : P.artKind === 'hero' ? 'backgrounds' : 'covers'} found for this game. Try another name below.` }]),
      { kind: 'head', label: A.current ? `Showing: ${A.current.name}${A.current.year ? ` (${A.current.year})` : ''}. Not the right game?` : 'Search' },
      ...A.games.filter(x => !A.current || x.id !== A.current.id).map(x => ({ kind: 'row', label: `${x.name}${x.year ? ` (${x.year})` : ''}`, act: () => loadArt({ sgdbId: x.id, query: A.query }) })),
      { kind: 'input', id: 'artq', label: 'Search by name', value: A.query || P.game.title, placeholder: 'Game name' },
      { kind: 'row', label: 'Search', act: () => loadArt({ query: val('artq') }) },
      { kind: 'row', label: 'Back', act: closePanel },  // as B does
    ];
  }
  if (P.view === 'epic') return [
    { kind: 'note', label: 'Epic has no official way to share your library, so this uses the same sign-in method as the Heroic and Legendary launchers. You sign in on Epic’s own website; this app never sees your password.' },
    { kind: 'row', label: '1. Open Epic sign-in', sub: 'Opens in your web browser', act: () => api('/api/accounts/epic/open', {}).then(() => toast('Opened in your browser')) },
    { kind: 'note', label: 'After signing in, the page shows a short block of text containing "authorizationCode". Copy it (or the whole page) and paste it below. Codes expire after a few minutes.' },
    { kind: 'input', id: 'code', label: '2. Paste the code', value: '', placeholder: 'authorizationCode…' },
    { kind: 'row', label: 'Connect', primary: true, act: () => work(api('/api/accounts/epic', { code: val('code') }), 'Epic connected', subReturn()) },
    { kind: 'row', label: 'Back', act: () => setView(subReturn()) },
  ];
  if (P.view === 'accounts') return [
    ...(ON_MAC && !d.steamDetected ? [{ kind: 'note', label: 'Steam games play through the Steam app, which isn’t included. Install Steam for Mac from steampowered.com to play them.' }] : []),
    { logo: 'steam', ...(acc.steam ? removable('acc-steam', 'Steam', `Connected · ${acc.steam.label} · ${acc.steam.count} games`, '/api/accounts/remove', { name: 'steam' })
      : { kind: 'row', label: 'Connect Steam', sub: 'Show every game you own on Steam, installed or not', act: () => setView('steam') }) },
    { logo: 'epicgames', ...(acc.epic ? removable('acc-epic', 'Epic Games', `Connected · ${acc.epic.label} · ${acc.epic.count} games`, '/api/accounts/remove', { name: 'epic' })
      : { kind: 'row', label: 'Connect Epic Games', sub: 'Show every game you own on Epic', act: () => setView('epic') }) },
    { img: SGDB_LOGO, ...(acc.sgdb ? removable('acc-sgdb', 'SteamGridDB', 'Connected · used for covers, backgrounds and logos', '/api/accounts/remove', { name: 'sgdb' })
      : { kind: 'row', label: 'Connect SteamGridDB (optional)', sub: 'Choose any game’s artwork, animated covers and backgrounds, Switch covers', act: () => setView('sgdb') }) },
    { ic: icon('crown'), ...(acc.ra ? removable('acc-ra', 'RetroAchievements', `Connected · ${acc.ra.label} · ${acc.ra.points} points`, '/api/accounts/remove', { name: 'ra' })
      : { kind: 'row', label: 'Connect RetroAchievements', sub: 'Achievements for your ROMs and emulated games', act: () => setView('ra') }) },
    ...GAME_SERVICES.map(service => {
      const libraries = d.libraries.filter(l => l.provider === service.id);
      const found = d.options[service.id + 'Local'] && d.services?.[service.id]?.count;
      return { kind: 'row', logo: service.logo, ic: service.ic, label: service.name,
        sub: [found && `${found} installed game${found === 1 ? '' : 's'} found`, libraries.length && `${libraries.length} game source${libraries.length === 1 ? '' : 's'} added`].filter(Boolean).join(' · ')
          || (d.services?.[service.id] ? `Finds games installed on ${HERE}` : `Add games installed on ${HERE}`),
        value: libraries.length ? 'Manage' : 'Set up', act: () => { P.service = service.id; setView('service'); } };
    }),
    ...launcherRows(d, false),
    { kind: 'note', label: 'Select a connected account twice to disconnect it.' },
  ];
  if (P.view === 'service') {
    const service = GAME_SERVICES.find(s => s.id === P.service);
    const add = async kind => {
      const r = await work(api('/api/libraries/add', { kind, provider: service.id }));
      if (r?.added) toast(`${service.name} games added`);
    };
    const auto = d.services?.[service.id];  // EA app, Ubisoft Connect, GOG and Battle.net games are found automatically
    const key = service.id + 'Local';
    return [  // the page title names the service
      ...(auto ? [
        { kind: 'row', logo: service.logo, ic: service.ic, label: 'Find installed games automatically', value: onOff(d.options[key]),
          sub: !d.options[key] ? 'Off' : auto.count ? `${auto.count} found on ${HERE} · they start through ${service.name}`
            : auto.detected ? `${service.name} is installed, but no games from it were found` : `${service.name} isn’t installed on ${HERE}`,
          act: () => setOpt(key) },
        { kind: 'note', label: `Games ${service.name} installs show up by themselves. Your online library (games you own but haven’t installed) isn’t shown, because ${service.name} doesn’t share it. Keep ${service.name} signed in so games can start.` },
        { kind: 'head', label: 'Games it doesn’t find' },
      ] : [{ kind: 'note', label: `Add installed games from ${HERE}. Your online account library is not synced. Keep the service’s launcher signed in for games that require it.` }]),
      { kind: 'row', logo: service.logo, ic: service.ic, label: 'Add games folder', sub: 'Choose the folder containing your installed games, with one subfolder per game', act: () => add('pc') },
      { kind: 'row', ic: icon('folder'), label: 'Add a game or launcher', sub: 'Choose a specific .exe; you can change its app location later', act: () => add('game') },
      ...d.libraries.filter(l => l.provider === service.id).map(l => removable(l.id, l.type === 'game' ? 'Game or launcher' : 'Games folder', l.path, '/api/libraries/remove', { id: l.id })),
      { kind: 'row', label: 'Back', act: () => setView('accounts') },
    ];
  }
  if (P.view === 'libraries') return [
    ...(LIB.length ? [] : [{ kind: 'row', label: 'Run the setup guide again', sub: 'Your games aren’t set up yet: the guide finds your emulators and games, and connects your accounts', primary: true, act: openSetup }]),
    { kind: 'head', label: 'ROMs folder' },
    { kind: 'row', ic: icon('folder'), label: d.romRoot ? 'ROMs folder' : 'Set up a ROMs folder', value: d.romRoot ? 'Change' : 'Choose',
      sub: d.romRoot || 'One folder with a subfolder for each console. Drop ROMs and ISOs into the matching folder.', act: chooseRomRoot },
    // set up before 1.2.5: ROMs and the emulators the app downloaded can join everything else in C:\Ultra-Front-End
    ...(d.homeMove && (d.homeMove.roms || d.homeMove.emus.length) ? [(() => {
      const m = d.homeMove, what = [m.roms && 'your ROMs folder', m.emus.length && `${m.emus.join(', ')}`].filter(Boolean).join(' and ');
      return { kind: 'row', key: 'home-move', ic: icon('folder'), warn: P.confirm === 'home-move', label: `Move into ${m.home}`, value: 'Move',
        sub: P.confirm === 'home-move' ? 'Press A / Enter again to move. Close any emulator first'
          : `Moves ${what} there, with every game’s playtime, favourites and artwork${m.why ? `. ${m.why}` : ''}`,
        act: async () => {
          if (P.confirm !== 'home-move') { P.confirm = 'home-move'; return renderPanel(); }
          P.confirm = null;
          const r = await work(api('/api/home/move', {}));
          if (r) { toast(r.failed?.length ? `${r.moved.length ? `Moved ${r.moved.join(', ')}. ` : ''}${r.failed.join(', ')} ${r.failed.length === 1 && !r.failed[0].includes(',') ? 'is' : 'are'} in use by another program, so ${r.moved.length ? 'that stayed' : 'nothing moved'}. Restart Windows, then press Move again` : `Moved into ${m.home}`, 9000); await afterLibraryChange(); }
        } };
    })()] : []),
    ...(d.romRoot ? [{ kind: 'row', label: 'Open ROMs folder', sub: `Opens it in ${ON_ANDROID ? 'Files' : 'File Explorer'} so you can add games`, act: () => api('/api/romroot/open', {}).then(() => toast(ON_ANDROID ? 'Opened in Files' : 'Opened in File Explorer')) }] : []),
    ...(ON_ANDROID ? [{ kind: 'note', label: 'Android games on this device show up by themselves.' }] : [
    { kind: 'head', label: 'Other libraries' },
    ...d.libraries.map(l => removable(l.id, l.type === 'folder' ? `Folder: ${l.path.split(/[\\/]/).filter(Boolean).pop() || l.path}` : l.name,
      l.type === 'folder' ? l.path : `${typeName[l.type]} · ${l.path} · ${l.count} game${l.count === 1 ? '' : 's'}`, '/api/libraries/remove', { id: l.id })),
    ...(d.libraries.length ? [{ kind: 'note', label: 'Select a library twice to remove it (your files are not touched).' }] : []),
    { kind: 'row', label: '+ Add a folder of PC games', sub: 'Each subfolder becomes a game, e.g. decompiled ports or DRM-free games', act: () => addLib('pc') },
    { kind: 'row', label: '+ Add a ROM folder and emulator', sub: 'Pick the ROM folder, then the emulator’s .exe', act: () => addLib('roms') },
    { kind: 'row', label: '+ Add a single game', sub: 'Pick any game’s .exe', act: () => addLib('game') },
    { kind: 'row', label: '+ Add a folder', sub: `A tile that opens a folder in ${ON_MAC ? 'Finder' : 'File Explorer'}, for apps, movies or anything you open often`, act: () => addLib('folder') }]),
  ];
  if (P.view === 'artwork') return [
    { kind: 'row', ic: icon('bolt'), label: 'Intro', value: onOff(introOn()), sub: 'The short animation and sound when the frontend opens',
      act: () => { try { if (localStorage.getItem('fe-outro') === null) localStorage.setItem('fe-outro', outroEnabled() ? 'on' : 'off'); localStorage.setItem('fe-intro', introOn() ? 'off' : 'on'); } catch {} renderPanel(); } },
    { kind: 'row', ic: icon('bolt'), label: 'Outro', value: onOff(outroEnabled()), sub: 'The short animation and sound when the frontend closes', act: () => { try { localStorage.setItem('fe-outro', outroEnabled() ? 'off' : 'on'); } catch {} renderPanel(); } },
    { kind: 'row', ic: icon('wide'), label: 'Full-screen game art', value: onOff(d.options.artBackground), sub: 'The selected game’s art fills the home screen behind the row, instead of the night scenery', act: () => setOpt('artBackground').then(() => { S.artBg = P.data.options.artBackground; applyBackgroundMode(); }) },
    { kind: 'row', label: 'Find artwork & info online', value: onOff(d.options.onlineCovers), sub: 'Covers, logos, backgrounds and descriptions for games that don’t have them', act: () => setOpt('onlineCovers') },
    ...(ON_ANDROID ? [] : [{ kind: 'row', img: SGDB_LOGO, label: 'SteamGridDB', value: acc.sgdb ? 'Connected' : 'Optional', sub: 'More artwork to choose from, animated covers and backgrounds', act: () => acc.sgdb ? toast('SteamGridDB is connected') : setView('sgdb') }]),
    { kind: 'note', label: 'To change one game’s art, select it and press Y (or O) for its quick menu.' },
  ];
  return [  // general
    ...(/Windows/.test(navigator.userAgent) ? [{ kind: 'row', label: 'Start with Windows', value: STARTUP.find(s => s.mode === startupMode(d)).label.replace(/^Don’t start with Windows$/, 'Off'),
      sub: STARTUP.find(s => s.mode === startupMode(d)).sub, act: () => setStartup(STARTUP[(STARTUP.findIndex(s => s.mode === startupMode(d)) + 1) % STARTUP.length].mode) }] : []),
    ...(ON_MAC ? [{ kind: 'row', ic: icon('power'), label: 'Open at login', value: onOff(startupMode(d) === 'open'), sub: 'Opens full screen when you sign in to your Mac',
      act: () => setStartup(startupMode(d) === 'open' ? 'off' : 'open') }] : []),
    ...autologonRows(d),
    ...(/Windows/.test(navigator.userAgent) ? [{ kind: 'row', ic: icon('pad'), label: 'Keep games on screen', value: onOff(d.options.keepOnScreen),
      sub: 'Games that minimize when the in-game menu opens are asked to stay on screen, so the menu opens without the game pausing. Steam games pick this up after Steam restarts. Games in true fullscreen may still minimize: set them to borderless window in their own settings',
      act: () => setOpt('keepOnScreen') }] : []),
    ...(/Windows/.test(navigator.userAgent) ? [{ kind: 'row', ic: icon('pad'), label: 'Open with the Xbox button', value: onOff(d.options.guideOpens), sub: 'The Xbox button on a controller opens Ultra Front End, or brings it to the front; so does holding View + Start, which also works through Steam (Steam keeps the Xbox and Steam buttons for itself while it runs). A Steam Controller’s Steam button does it with a double-press or a hold. In a game, they open the overlay.', act: () => setOpt('guideOpens') }] : []),
    ...(ON_ANDROID ? [] : [{ kind: 'row', label: 'Installed Steam games', value: d.steamDetected ? onOff(d.options.steamLocal) : 'Steam not found',
      sub: !d.steamDetected ? '' : d.options.steamLocal ? `${d.localSteamCount} found on ${HERE}` : 'Off: your installed Steam games are hidden', act: () => d.steamDetected && setOpt('steamLocal') },
    { kind: 'row', label: 'Show games that aren’t installed', value: onOff(d.options.showUninstalled),
      sub: acc.steam || acc.epic ? 'Owned games from your accounts' : 'Owned games from connected accounts (none connected)', act: () => setOpt('showUninstalled') }]),
    { kind: 'row', label: 'UI scale', value: `${Math.round(uiScale() * 100)}%`, sub: 'Press left or right to make everything bigger or smaller', bar: (uiScale() - SCALE.min) / (SCALE.max - SCALE.min) * 100,
      adjust: dx => setUiScale(dx * SCALE.step), act: () => setUiScale(uiScale() >= SCALE.max ? SCALE.min - uiScale() : SCALE.step) },
    { kind: 'row', label: 'Platform icons', value: onOff(S.tabIcons !== false), sub: 'Logos next to All Games, PC, PlayStation, Xbox, Switch… in the bottom bar', act: () => { S.tabIcons = S.tabIcons === false; save(); renderTabs(); renderPanel(); } },
    { kind: 'row', label: 'Sounds', value: onOff(S.sound), act: () => { S.sound = !S.sound; save(); renderPanel(); } },
    { kind: 'row', label: 'UI sounds volume', value: `${S.uiVolume ?? 60}`, sub: 'Press left or right to change it', bar: S.uiVolume ?? 60, adjust: dx => setUiVolume(dx * 10), act: () => setUiVolume((S.uiVolume ?? 60) >= 100 ? -100 : 10) },
    // the app's own window is always full screen (and a page can't go full screen from a controller press)
    ...(window.pywebview || ON_ANDROID ? [] : [{ kind: 'row', label: 'Fullscreen', value: onOff(!!document.fullscreenElement), act: () => { toggleFS(); setTimeout(renderPanel, 300); } }]),
    { kind: 'row', label: 'Rescan everything', sub: 'Look for new games in every library and account', act: () => work(api('/api/rescan', {}), 'Library updated') },
    ...(d.extras?.presentmon?.available || d.extras?.recorder?.available ? [{ kind: 'head', label: 'Extras' }, ...recorderRows(d), ...extraRows(d)] : []),
    ...d.errors.map(e => ({ kind: 'note', warn: true, label: e })),
  ];
}
const val = id => $(`#panel input[data-id="${id}"]`)?.value || '';
// ---------- extras: optional tools that install through the emulator queue (Settings › General and the setup guide) ----------
const PM_RIGHTS = { ready: 'Ready', signout: 'Sign out and back in to finish', needed: 'Needs permission' };
// Game launchers (Steam, Epic, EA app, Ubisoft Connect, GOG Galaxy, Battle.net, Rockstar): installed through the same queue
// as the emulators when they're missing, from the setup guide's Accounts step and Settings › Accounts.
const LAUNCHER_LOGO = { steam: 'steam', epic: 'epicgames', ea: 'ea', ubisoft: 'ubisoft', gog: 'gogdotcom', battlenet: 'battledotnet', rockstar: 'rockstargames' };
function launcherRows(d, setup) {
  const list = d.launchers || [];
  if (!list.length) return [];
  const missing = list.filter(l => !l.installed);
  const install = l => l.job && ['waiting', 'installing'].includes(l.job.state) ? toast('It’s on its way', 2500)
    : work(api('/api/launchers/install', { id: l.id })).then(r => { if (r) { toast(`Installing ${l.name}…`, 3000); watchQueue(); } });
  return [
    { kind: 'head', label: 'Game launchers' },
    { kind: 'note', label: missing.length ? `${setup ? 'Don’t have one you use? ' : ''}Press A to install it from its maker. Their games then show up here by themselves.`
      : 'Every launcher is installed.' },
    ...list.map(l => {
      const job = !l.installed && l.job && l.job.state !== 'ready' ? l.job : null;
      return { kind: 'row', key: 'launcher-' + l.id, logo: LAUNCHER_LOGO[l.id], label: l.name,
        value: l.installed ? '✓ Installed' : job ? (job.state === 'failed' ? 'Try again' : jobValue(job)) : 'Install',
        sub: l.installed ? '' : job?.state === 'failed' ? `Install failed: ${job.error}` : job?.state === 'installing' && job.stage ? progressText(job)
          : job ? 'Waiting to install' : `Not installed on ${HERE}`,
        ...jobBar({ job }), act: () => l.installed ? toast(`${l.name} is installed`, 2000) : install(l) };
    }),
  ];
}
// Video recording: the app's own copy of FFmpeg, fetched into its data folder. Screenshots need nothing extra.
function recorderRows(d, setup) {
  const rec = d.extras?.recorder;
  if (!rec?.available) return [];
  const job = rec.job && rec.job.state !== 'ready' ? rec.job : null, what = 'Record gameplay with sound from the in-game menu';
  const install = () => job && job.state !== 'failed' ? toast('It’s on its way', 2500)
    : work(api('/api/extras/install', { name: 'recorder' })).then(r => { if (r) { toast('Setting up video recording…', 3000); watchQueue(); } });
  if (!rec.installed) return [{ kind: 'row', key: 'rec', ic: icon('album'), label: setup ? `Video recording: ${what}` : 'Video recording',
    value: job ? (job.state === 'failed' ? 'Try again' : jobValue(job)) : setup ? '' : 'Set up',
    sub: job?.state === 'failed' ? `Couldn’t set it up: ${job.error}` : job?.state === 'installing' && job.stage ? progressText(job) : job ? 'Downloading FFmpeg (about 80 MB, once)…'
      : setup ? 'Press A to tick it. Ultra Front End downloads FFmpeg (about 80 MB, once) to record with' : `${what}. Downloads FFmpeg (about 80 MB, once)`,
    ...jobBar({ job }), act: install }];
  const rm = P.confirm === 'rec-rm';
  return [
    { kind: 'row', key: 'rec', ic: icon('album'), label: setup ? `Video recording: ${what}` : 'Video recording', value: setup ? '✓' : 'Ready',
      sub: 'Record video and take screenshots from the in-game menu; they appear in the Album', act: () => toast('Ready: use Record video in the in-game menu', 3000) },
    ...(setup ? [] : [{ kind: 'row', key: 'rec-rm', warn: rm, label: 'Remove video recording', sub: rm ? 'Press A / Enter again to remove' : 'Deletes FFmpeg from the data folder (your videos stay)',
      act: () => rm ? work(api('/api/extras/remove', { name: 'recorder' }), 'Video recording removed') : (P.confirm = 'rec-rm', renderPanel()) }]),
  ];
}
function extraRows(d, setup) {
  const pm = d.extras?.presentmon;
  if (!pm?.available) return [];
  const job = pm.job && pm.job.state !== 'ready' ? pm.job : null, what = 'FPS, frame times, CPU and GPU in games';
  const install = () => job && job.state !== 'failed' ? toast('It’s on its way', 2500)
    : work(api('/api/extras/install', { name: 'presentmon' })).then(r => { if (r) { toast('Installing the performance overlay…', 3000); watchQueue(); } });
  if (!pm.installed) return [{ kind: 'row', key: 'pm', ic: icon('bolt'), label: setup ? `Performance overlay: ${what}` : 'Performance overlay',
    value: job ? (job.state === 'failed' ? 'Try again' : jobValue(job)) : setup ? '' : 'Install',
    sub: job?.state === 'failed' ? `Install failed: ${job.error}` : job?.state === 'installing' && job.stage ? progressText(job) : job ? 'Downloading Intel’s PresentMon from its GitHub page…'
      : setup ? 'Press A to tick it and install Intel’s PresentMon, which reads frame times from Windows' : `${what}. Installs Intel’s PresentMon`, ...jobBar({ job }), act: install }];
  const rm = P.confirm === 'pm-rm';
  return [
    { kind: 'row', key: 'pm', ic: icon('bolt'), label: setup ? `Performance overlay: ${what}` : 'Performance overlay', value: setup ? '✓' : PM_RIGHTS[pm.rights],
      sub: `PresentMon ${pm.version} · ${{ ready: 'Ready to show in games', signout: 'Windows gives you the permission at your next sign-in',
        needed: 'PresentMon needs permission to read frame times' }[pm.rights]}`, act: () => pm.rights === 'needed' ? allowPresentmon() : toast(PM_RIGHTS[pm.rights], 3000) },
    ...(setup || !pm.mode ? [] : [{ kind: 'row', key: 'pm-mode', label: 'Show in games', value: pm.mode[0].toUpperCase() + pm.mode.slice(1),
      sub: 'Off, Compact (FPS) or Full (frame times, CPU and GPU). Press A to change',
      act: () => api('/api/hud', {}).then(r => { pm.mode = r.mode; renderPanel(); }).catch(e => toast(e.message)) }]),
    ...(pm.rights === 'needed' ? [{ kind: 'row', key: 'pm-allow', label: 'Give permission', value: 'Allow', act: allowPresentmon,
      sub: 'Adds you to Windows’ Performance Log Users group. Windows asks first, then you sign out and back in' }] : []),
    ...(setup ? [] : [{ kind: 'row', key: 'pm-rm', warn: rm, label: 'Remove the performance overlay', sub: rm ? 'Press A / Enter again to remove' : 'Deletes PresentMon from the data folder',
      act: () => rm ? work(api('/api/extras/remove', { name: 'presentmon' }), 'Performance overlay removed') : (P.confirm = 'pm-rm', renderPanel()) }]),
  ];
}
async function allowPresentmon() {
  toast('Answer Windows’ prompt to give permission…', 4000);
  const r = await work(api('/api/extras/permission', { name: 'presentmon' }));
  const now = r?.extras?.presentmon?.rights;
  if (now && now !== 'needed') toast(now === 'ready' ? 'Ready' : 'Done. Sign out of Windows and back in to finish.', 6000);
}
// ---------- systems (Settings › Systems and the setup guide) ----------
const sysLogo = name => PLATFORM_LOGO[name] ? { logo: PLATFORM_LOGO[name] } : { ic: icon('pad') };
const jobValue = j => j.state === 'installing' && j.progress != null ? `${Math.floor(j.progress)}%` : ({ waiting: 'Waiting', installing: 'Installing…', failed: 'Failed', ready: 'Ready' })[j.state];
// An emulator install for this system: waiting its turn, installing (how far it's got), or failed (and why)
function jobText(p) {
  const j = p.job;
  if (!j || p.emulator) return '';
  return { waiting: 'Waiting to install', installing: j.stage ? progressText(j) : `Installing ${p.install || p.recommended}…`, failed: `Install failed: ${j.error}`, ready: '' }[j.state];
}
// "Downloading 34% · 12 of 35 MB", or the stage alone while there's no telling how far it's got
const mb = n => { const v = n / 1048576; return v < 10 ? v.toFixed(1).replace(/\.0$/, '') : Math.round(v); };
function progressText(j) {
  if (j.progress == null) return `${j.stage}…`;
  return `${j.stage} ${Math.floor(j.progress)}%${j.total ? ` · ${mb(j.done || 0)} of ${mb(j.total)} MB` : ''}`;
}
// While a job installs, its rows get a bar: how far, or a short sliding bar while that isn't known. Nothing otherwise.
const jobBar = p => p.job?.state === 'installing' && !p.emulator ? { bar: p.job.progress ?? 'busy' } : {};
// The setup guide's systems step: which install of how many, and how far the current one is ("Installing 2 of 5 · ares 34%")
function queueLine(q) {
  const batch = (q?.jobs || []).filter(j => j.id >= (q.batch || 0)), now = batch.find(j => j.state === 'installing');
  if (!q?.busy || !now) return [];
  const n = batch.filter(j => ['ready', 'failed'].includes(j.state)).length + 1;
  return [{ kind: 'info', key: 'pick-progress', label: `Installing ${n} of ${batch.length} · ${now.emulator}${now.progress != null ? ` ${Math.floor(now.progress)}%` : ''}`,
    sub: now.stage ? progressText(now) : 'Starting…', bar: now.progress ?? 'busy' }];
}
// Rows under a heading per maker, in the helper's order
function groupRows(list, row) {
  const out = [];
  list.forEach((p, i) => { if (p.group !== list[i - 1]?.group) out.push({ kind: 'head', label: p.group }); out.push(row(p)); });
  return out;
}
// While emulators install, the open system pages follow along
let queueTimer = 0;
const QUEUE_VIEWS = ['systems', 'system', 'add-system', 'setup-systems', 'general', 'setup-extras', 'accounts', 'setup-accounts'];
const followQueue = () => { if (QUEUE_VIEWS.includes(P.view) && P.data?.queue?.busy) watchQueue(); };  // however the page was reached
const queueStates = q => (q?.jobs || []).map(j => `${j.id}:${j.state}`).join();
function watchQueue() {
  if (queueTimer) return;
  const step = async () => {
    let q;
    try { q = await api('/api/systems/queue'); } catch { q = null; }
    const showing = P.open && QUEUE_VIEWS.includes(P.view);
    if (showing && !P.working && q && P.data) {
      if (queueStates(q) !== queueStates(P.data.queue)) {  // one started, finished or failed: the rows change too
        try { P.data = await api('/api/settings'); } catch {}
      } else {  // only how far it's got: onto the jobs already shown
        const byId = Object.fromEntries(q.jobs.map(j => [j.id, j]));
        P.data.queue = q;
        [...(P.data.platforms || []).map(p => p.job), P.data.extras?.presentmon?.job].forEach(j => { if (j && byId[j.id]) Object.assign(j, byId[j.id]); });
      }
      renderPanel();
    }
    queueTimer = q?.busy && P.open ? setTimeout(step, 500) : 0;
  };
  queueTimer = setTimeout(step, 500);
}
// Game menu (Y / O / right-click on a cover).
async function openGame(g, view) {
  if (!g) return;
  if (!API) return toast('Start the frontend with Start Frontend.bat to change artwork');
  P.open = true; P.game = g; P.view = 'game'; P.focus = 0; P.confirm = null;
  document.body.classList.add('panel-open');
  tick(640, .06);
  try { P.data = await api('/api/settings'); } catch (e) { toast(e.message); }
  if (view === 'cover' || view === 'hero' || view === 'logo') return artOrConnect(view);
  renderPanel();
}
async function changeAppLocation(g, reset = false) {
  const r = await work(api('/api/game/app-location', { id: g.id, reset }));
  if (!r || r.cancelled) return;
  if (P.open) P.game = LIB.find(game => game.id === g.id) || g;
  renderPanel();
  if (D.open) refreshDetails();
  toast(reset ? 'Default app location restored' : 'App location updated');
}
// Emulated games also get libretro's box art and screens, so their picker works without SteamGridDB.
function artOrConnect(kind) { P.artKind = kind; P.data?.accounts?.sgdb || (P.artKind !== 'logo' && P.game?.source === 'Emulators') ? openArt(kind) : setView('sgdb'); }
function openArt(kind = 'cover') { P.artKind = kind; P.view = 'art'; P.art = { loading: true, games: [], grids: [], current: null }; P.focus = 0; renderPanel(); loadArt({}); }
async function chooseArt(url) {
  const id = P.game.id;
  const r = await work(api('/api/art/set', { id, url, kind: P.artKind }), P.artKind === 'logo' ? 'Logo updated' : P.artKind === 'hero' ? 'Background updated' : 'Cover updated');
  if (r) { forgetArt(id); closePanel(); refreshDetails(); }
}
async function resetArt(g, kind) {
  await work(api('/api/art/reset', { id: g.id, kind }), kind === 'logo' ? 'Logo reset' : kind === 'hero' ? 'Background reset' : 'Cover reset');
  forgetArt(g.id); closePanel(); refreshDetails();
}
// New art for a game: drop what this page looked up for it before (its background, its details and logo). Kept, the home
// background, the launch screen and the details screen went on showing the old art until the frontend restarted.
function forgetArt(id) {
  delete HERO_CACHE[id]; delete HERO_DONE[id]; delete HERO_ANIM[id]; delete DCACHE[id];
  if (game()?.id === id) { bgShown = null; scheduleBackground(game(), 0); }
}
async function loadArt(params) {
  P.art = { ...P.art, loading: true, query: params.query || P.art.query }; renderPanel();
  try { P.art = { ...(await api('/api/art/options', { id: P.game.id, kind: P.artKind, ...params })), query: params.query || P.art.query, loading: false }; }
  catch (e) { toast(e.message, 4000); P.art = { ...P.art, loading: false }; }
  P.focus = 0; renderPanel();
}
function setView(v) {
  if (SUB_VIEW[v] && !SUB_VIEW[P.view]) P.returnTo = P.view;  // remember where a sub-page was opened from
  P.lastFocus = { ...P.lastFocus, [P.view]: P.focus };  // and which row, to land on it again on the way back
  // every emulator (and every service) shares one view, and none has a page of its own to come back from: always the top
  if (v === 'systems' && P.view === 'system') P.focusKey = 'sys-' + P.system;  // rows may have come or gone above it since
  P.view = v; P.focus = v === 'system' || v === 'service' ? 0 : P.lastFocus[v] ?? 0; P.confirm = null; renderPanel();
  followQueue();
}
async function pickAvatar(id) {
  await saveProfile({ avatar: id });
  if (P.data) P.data.profile = PROFILE;
  setView(subReturn());
}
async function chooseRomRoot(useDefault) {
  if (useDefault !== true) toast('Choose or create a folder in the window that just opened…', 4000);
  const r = await work(api(useDefault === true ? '/api/romroot/default' : '/api/romroot/choose', {}));
  if (!r || r.cancelled) return;
  const has = (r.platforms || []).filter(p => p.count), n = has.reduce((s, p) => s + p.count, 0), emus = r.found ? `${r.found} emulator${r.found === 1 ? '' : 's'}` : '';
  toast(n ? `Found ${n} game${n === 1 ? '' : 's'} for ${has.map(p => p.name).join(', ')}${emus ? ` and ${emus}` : ''}`
    : `ROMs folder ready${r.made ? `: made ${r.made} console folders` : ''}. Drop games into the console folders${emus ? `. Found ${emus}` : ''}`, 5000);
}

// ---------- first-time setup guide ----------
// Runs inside the panel as a centred card: welcome, profile, time zone, accounts, games, done.
// a Mac has no Windows-only extras (the performance overlay) or start-with-Windows step
const SETUP_STEPS = ['setup-welcome', 'setup-profile', 'setup-time', ...(ON_ANDROID ? [] : ['setup-accounts']), 'setup-games', 'setup-systems',
  ...(ON_MAC || ON_ANDROID ? [] : ['setup-extras', 'setup-startup']), 'setup-done'];
const SETUP_TITLES = { 'setup-welcome': 'Ultra Front End', 'setup-profile': 'Your profile', 'setup-time': 'Time zone', 'setup-accounts': 'Accounts',
  'setup-games': 'Emulators & games', 'setup-systems': 'Your systems', 'setup-extras': 'Extras', 'setup-startup': 'Starting up', 'setup-done': 'All done' };
// Start with Windows: the choices, in Settings and in the setup guide
const STARTUP = [
  { mode: 'background', label: 'Start in the background', sub: 'Nothing opens, but the controller’s guide button (Xbox or Steam), holding View + Start, or the tray icon brings the frontend up straight away' },
  { mode: 'open', label: 'Open the frontend', sub: 'It opens full screen when you sign in, like a console' },
  { mode: 'off', label: 'Don’t start with Windows', sub: 'Open it yourself when you want it' },
];
const startupMode = d => d?.options?.startup || 'background';
// Signing in to Windows by itself, so the PC goes straight to the frontend. Windows asks for administrator permission;
// an account with a password types it into Windows' own User Accounts window, never into this app.
function autologonRows(d, setup) {
  const al = d.autologon;
  if (!al?.available) return [];
  const sure = P.confirm === 'autologon';
  const sub = al.on ? 'Windows skips its sign-in screen when the PC starts and when it wakes from sleep'
    : sure ? `Anyone who turns on ${HERE} is signed in as you. Press A again to turn it on`
    : al.other ? `Windows signs in ${al.other} by itself now. Turn it on to sign in ${al.user} instead`
    : 'Skip Windows’ sign-in screen, so the PC goes straight to Ultra Front End. Windows asks for permission first';
  return [
    { kind: 'row', key: 'autologon', warn: sure, label: 'Sign in to Windows automatically', value: setup ? (al.on ? '✓' : '') : al.other && !al.on ? 'Another account' : onOff(al.on), sub,
      act: () => al.on || sure ? setAutologon(!al.on, al) : (P.confirm = 'autologon', renderPanel()) },
    ...(al.other && !al.on ? [{ kind: 'row', key: 'autologon-off', label: `Stop signing in ${al.other} automatically`, sub: 'Windows asks for the sign-in again', act: () => setAutologon(false, al) }] : []),
  ];
}
async function setAutologon(on, al) {
  P.confirm = null;
  toast(on ? `Answer Windows’ prompt. If your account has a password, Windows’ User Accounts window opens: select ${al.user}, untick “Users must enter a user name and password”, choose OK, then type your Windows password` : 'Answer Windows’ prompt…', on ? 20000 : 6000);
  const r = await work(api('/api/autologon', { on }));
  if (!r) return;
  // a password goes into Windows' own window: it was open (and waited for) by the time this answer came
  if (r.autologonState === 'cancelled') toast('Nothing changed: the User Accounts window was closed', 5000);
  else toast(on ? 'Windows will sign you in by itself' : 'Windows will ask you to sign in again', 4000);
}
async function setStartup(mode) {
  try { P.data = { ...P.data, ...(await api('/api/options', { startup: mode })) }; } catch (e) { toast(e.message); }
  renderPanel();
}
async function openSetup() {
  if (P.open) P.lastFocus = { ...P.lastFocus, [P.view]: P.focus };  // run from About: B on Welcome lands on this row again
  P.open = true; P.setup = true; P.game = null; P.view = SETUP_STEPS[0]; P.focus = 0; P.confirm = null; P.returnTo = null; P.pick = null;
  document.body.classList.add('panel-open', 'setup-mode');
  try { P.data = await api('/api/settings'); } catch (e) { toast(e.message); }
  renderPanel();
}
function setupGo(dir) {
  const i = SETUP_STEPS.indexOf(P.view);
  if (i + dir < 0) return;
  if (i + dir >= SETUP_STEPS.length) return finishSetup();
  P.returnTo = null; tick(dir > 0 ? 760 : 520, .06); setView(SETUP_STEPS[i + dir]);
}
const setupBack = () => setupGo(-1);
async function finishSetup(skipped) {
  const mode = startupMode(P.data);
  if (API) await api('/api/options', { startup: mode }).catch(() => {});  // skipped or not, the choice (or the default) applies
  await saveProfile({ setupDone: true });
  P.setup = false;
  document.body.classList.remove('setup-mode');
  closePanel();
  // skipped, the start-up step wasn't seen: say what was chosen for it, and where it changes
  if (skipped === true && API && mode !== 'off' && /Windows/.test(navigator.userAgent))
    toast(`Ultra Front End will ${mode === 'open' ? 'open' : 'start in the background'} when you sign in to Windows. Change it in Settings › General.`, 6000);
}
function setupItems(d, prof) {
  const acc = d.accounts, next = { kind: 'row', label: 'Next', primary: true, act: () => setupGo(1) };
  switch (P.view) {
    case 'setup-welcome': return [
      { kind: 'html', html: '<div class="sw-hero"><div class="sw-big">Welcome</div><p>Let’s set up your game library. It takes a minute, and you can change everything later in Settings.</p></div>' },
      { kind: 'row', label: 'Get started', primary: true, act: () => setupGo(1) },
      { kind: 'row', label: 'Skip setup', sub: 'Go straight to your games', act: () => finishSetup(true) },
    ];
    case 'setup-profile': return [
      { kind: 'html', html: `<div class="pprofile"><span class="avatar big">${avatarHTML(prof)}</span><div><div class="pp-name">${esc(prof.name || 'Your name')}</div><div class="pp-sub">Shown in the top corner</div></div></div>` },
      { kind: 'input', id: 'pname', label: 'What should we call you?', value: prof.name || '', placeholder: 'Your name', max: NAME_MAX },
      { kind: 'row', label: 'Choose a profile icon', value: 'Pick', act: () => saveProfile({ name: val('pname') }).then(() => { P.data.profile = PROFILE; setView('avatar'); }) },
      { ...next, act: () => saveProfile({ name: val('pname') }).then(() => { P.data.profile = PROFILE; setupGo(1); }) },
    ];
    case 'setup-time': return [
      { kind: 'note', label: 'Where are you? The clock uses this time zone.' },
      { ...next, sub: `Keep ${zoneName(prof.timezone || 'auto')}` },
      ...['auto', ...TIMEZONES].map(z => ({ kind: 'row', label: zoneName(z), value: `${prof.timezone === z ? '✓  ' : ''}${timeIn(z)}`,
        act: () => saveProfile({ timezone: z }).then(() => { P.data.profile = PROFILE; setupGo(1); }) })),
    ];
    case 'setup-accounts': return [
      { kind: 'note', label: `${d.steamDetected ? 'Your installed Steam games are already here: connecting Steam adds the ones you haven’t installed. ' : 'Connect the stores you use to see every game you own. '}`
        + 'Each needs a key or code from its website, easiest with a keyboard, so it’s fine to skip this and do it later in Settings › Accounts.'
        + (ON_MAC && !d.steamDetected ? ' Steam games play through the Steam app, which isn’t included: install Steam for Mac from steampowered.com to play them.' : '') },
      acc.steam ? { kind: 'row', logo: 'steam', label: 'Steam', value: '✓ Connected', sub: `${acc.steam.count} games`, act: () => {} } : { kind: 'row', logo: 'steam', label: 'Connect Steam', sub: 'Every game you own on Steam', act: () => setView('steam') },
      acc.epic ? { kind: 'row', logo: 'epicgames', label: 'Epic Games', value: '✓ Connected', sub: `${acc.epic.count} games`, act: () => {} } : { kind: 'row', logo: 'epicgames', label: 'Connect Epic Games', sub: 'Every game you own on Epic', act: () => setView('epic') },
      { kind: 'note', label: 'Optional: more artwork. Your games already get covers without it.' },
      acc.sgdb ? { kind: 'row', img: SGDB_LOGO, label: 'SteamGridDB', value: '✓ Connected', sub: 'Choose artwork, animated covers', act: () => {} } : { kind: 'row', img: SGDB_LOGO, label: 'SteamGridDB (optional)', sub: 'Choose covers and backgrounds, animated ones too, and Switch covers. Free account', act: () => setView('sgdb') },
      ...launcherRows(d, true),
      next,
    ];
    case 'setup-games': {
      const withEmu = d.platforms.filter(p => p.emulator), pc = d.libraries.filter(l => l.type === 'pc' && !l.provider);
      return [
        { kind: 'note', label: 'Emulated games: pick one ROMs folder and the frontend makes a subfolder for every console. Drop your ROMs and ISOs into the right one.' },
        ...(d.romRoot ? [{ kind: 'row', label: 'ROMs folder', sub: d.romRoot, value: '✓ Change', act: chooseRomRoot }]
          : [{ kind: 'row', label: ON_ANDROID ? 'Use the ROMs folder on this device (recommended)' : ON_MAC ? 'Use the ROMs folder in your home folder (recommended)' : 'Use C:\\Ultra-Front-End\\ROMs (recommended)',
            sub: ON_ANDROID ? 'Internal storage › ROMs, with a folder for each system you play inside' : ON_MAC ? '~/ROMs, with a folder for each system you play inside' : 'A folder for each system you play goes inside', value: 'Use', act: () => chooseRomRoot(true) },
            { kind: 'row', label: 'Choose a different folder', sub: 'Somewhere else, like another drive', value: 'Choose', act: chooseRomRoot }]),
        { kind: 'row', label: 'Find installed emulators', sub: withEmu.length ? `Ready: ${withEmu.map(p => `${p.name} (${p.emulator})`).join(', ')}` : `Looks for emulators already on ${HERE}`, act: () => work(api('/api/emulators/find', {})).then(r => r && toast(r.found ? `Found ${r.found} emulator${r.found === 1 ? '' : 's'}` : 'No new emulators found', 3000)) },
        ...(ON_ANDROID ? [{ kind: 'note', label: 'Android games on this device show up by themselves.' }] : [{ kind: 'row', label: '+ Add a folder of PC games', act: () => addLib('pc'), value: pc.length ? '✓ Add another' : '',  // what's been added stays on show
          sub: pc.length ? pc.map(l => `${l.path} · ${l.count} game${l.count === 1 ? '' : 's'}`).join('; ') : 'Optional: decompiled ports or DRM-free games' }]),
        next,
      ];
    }
    case 'setup-systems': {
      const known = d.platforms.filter(p => p.group !== 'Other');
      if (!P.pick) { P.pick = new Set(); P.unpicked = new Set(); }
      // the ones chosen or with games come ticked, also when they got games after this step was first shown; unticked stays unticked
      known.forEach(p => { if ((p.chosen || p.count) && !P.unpicked.has(p.name)) P.pick.add(p.name); });
      const todo = known.filter(p => P.pick.has(p.name) && !p.emulator && p.install && !['waiting', 'installing'].includes(p.job?.state));
      const save = install => work(api('/api/systems/choose', { systems: [...P.pick], install }));
      const go = { ...next, key: 'pick-next', primary: !todo.length,
        sub: todo.length ? `Installs the emulators for ${todo.length} ticked system${todo.length === 1 ? '' : 's'}` : P.pick.size ? `${P.pick.size} system${P.pick.size === 1 ? '' : 's'} ticked` : '',
        act: async () => { if (await save(todo.length > 0)) { if (todo.length) { toast('Installing… Windows may ask once for permission. You can carry on', 5000); watchQueue(); } setupGo(1); } } };
      return [
        { kind: 'note', label: 'Which systems do you play? Press A to tick or untick one. Each gets its own folder in your ROMs folder' + (ON_ANDROID ? '. Get its emulator from Google Play: Settings › Systems shows which one.' : ', and its emulator is installed for you.') },
        ...queueLine(d.queue),
        ...(todo.length ? [{ kind: 'row', key: 'pick-install', primary: true, label: `Install emulators for ${todo.length} system${todo.length === 1 ? '' : 's'}`,
          sub: 'One at a time, from each emulator’s own project. You can carry on while they install',
          act: async () => { if (await save(true)) { toast('Installing… Windows may ask once for permission. You can carry on', 5000); watchQueue(); } } }] : []),
        go,
        ...groupRows(known, p => ({ kind: 'row', key: 'pick-' + p.name, ...sysLogo(p.name), label: p.name, value: P.pick.has(p.name) ? '✓' : '', ...jobBar(p),
          sub: jobText(p) || [p.emulator ? `${p.emulator} · Ready` : p.recommended, p.count ? `${p.count} game${p.count === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · '),
          act: () => { const off = P.pick.has(p.name); off ? P.pick.delete(p.name) : P.pick.add(p.name); off ? P.unpicked.add(p.name) : P.unpicked.delete(p.name); tick(760, .05); renderPanel(); } })),
        { ...go, key: 'pick-next-end' },
      ];
    }
    case 'setup-extras': {
      const pm = d.extras?.presentmon, rec = d.extras?.recorder;
      const chosen = pm?.installed || pm?.job && pm.job.state !== 'failed' || rec?.installed || rec?.job && rec.job.state !== 'failed';
      return [
        { kind: 'note', label: 'Optional extras. Press A to tick one and it installs. You can add or remove them later in Settings › General.' },
        ...recorderRows(d, true),
        ...extraRows(d, true),
        { ...next, key: 'extras-next', label: chosen ? 'Next' : 'Skip', sub: chosen ? '' : 'Nothing extra for now' },
      ];
    }
    case 'setup-startup': return [
      { kind: 'note', label: 'Should Ultra Front End start when you sign in to Windows? You can change this later in Settings › General, or from its tray icon.' },
      ...STARTUP.map(s => ({ kind: 'row', label: s.label + (s.mode === 'background' ? ' (recommended)' : ''), sub: s.sub,
        value: startupMode(d) === s.mode ? '✓' : '', act: () => setStartup(s.mode) })),
      ...autologonRows(d, true),
      next,
    ];
    default: return [
      { kind: 'html', html: `<div class="sw-hero"><span class="avatar big">${avatarHTML(prof)}</span><div class="sw-big">You’re all set${prof.name ? ', ' + esc(prof.name) : ''}</div><p>Press A on a game to see its details, Y for its quick menu, and LB / RB to switch platforms.</p></div>` },
      { kind: 'row', label: 'Start playing', primary: true, act: finishSetup },
    ];
  }
}

// Unhide from the Settings list and stay on it, so several games can be brought back in a row.
async function unhideFromList(g) {
  try { await api('/api/game/hide', { id: g.id, hidden: false }); } catch (e) { return toast(e.message); }
  await loadLibrary(); buildRow(false);
  toast(`${g.title} is back in your library`);
  if (!LIB.some(x => x.hidden)) P.side = true;  // the last one: nothing left to highlight here, so back to the categories
  renderPanel();
}
async function setOpt(k) { await work(api('/api/options', { [k]: !P.data.options[k] })); }
// Settings › Systems: newer versions of the emulators the app installed. Downloaded ones update by themselves when nothing
// is running; ones with an installer wait here, since their installers may ask Windows for permission.
function emuUpdateRows(d) {
  if (ON_MAC || ON_ANDROID || !d.emuUpdates) return [];
  const list = d.emuUpdates.list || [], run = name => api('/api/emulators/update', name ? { name } : {})
    .then(r => { P.data = r; renderPanel(); watchQueue(); toast(name ? `Updating ${name}…` : 'Updating your emulators…', 3000); }, e => toast(e.message));
  return [
    { kind: 'head', label: 'Emulator updates' },
    ...list.map(u => ({ kind: 'row', key: 'emu-up-' + u.name, ic: icon('download'), label: `Update ${u.name}`, value: 'Update',
      sub: [u.to && `New: ${u.to}`, u.systems.join(', '), u.installer && 'Its installer may ask Windows for permission'].filter(Boolean).join(' · '), act: () => run(u.name) })),
    ...(list.length > 1 ? [{ kind: 'row', key: 'emu-up-all', label: 'Update all', value: `${list.length}`, sub: 'One after another, with one Windows prompt for the installers', act: () => run() }] : []),
    { kind: 'row', key: 'emu-up-check', label: 'Check for emulator updates',
      sub: d.emuUpdates.checked ? `Checked ${fmtDate(d.emuUpdates.checked)}${list.length ? '' : ': all up to date'}. Checked every day; downloaded emulators update by themselves` : 'Checked every day; downloaded emulators update by themselves',
      act: () => work(api('/api/emulators/update', { check: true })).then(r => r && toast(r.emuUpdates?.list?.length ? `${r.emuUpdates.list.length} update${r.emuUpdates.list.length === 1 ? '' : 's'} found` : 'Your emulators are up to date', 3000)) },
  ];
}
async function addLib(kind) {
  toast('Choose in the window that just opened…', 4000);
  const r = await work(api('/api/libraries/add', { kind }));
  if (r?.added) toast(kind === 'folder' ? 'Folder added: Play opens it' : `Added ${r.added}: ${r.count} game${r.count === 1 ? '' : 's'}`, 3000);
}
// Run a request, then refresh the panel and the game row.
// Settings › About › Uninstall (Mac): press twice; the helper moves things to the Trash and the app quits
function uninstallRow(key, wipe, label, sub) {
  return { kind: 'row', key, label, warn: P.confirm === key, sub: P.confirm === key ? 'Press A / Enter again to uninstall' : sub,
    act: async () => {
      if (P.confirm !== key) { P.confirm = key; return renderPanel(); }
      P.confirm = null;
      try {
        const r = await api('/api/uninstall', { wipe });
        if (!r.ok) return toast(`Couldn’t uninstall: ${r.failed.join(', ')}`, 8000), renderPanel();
        toast(wipe ? 'Uninstalled. The app and your settings are in the Trash' : 'Uninstalled. The app is in the Trash; your settings were kept', 8000);
      } catch (e) { toast(e.message); renderPanel(); }
    } };
}
async function work(promise, okMsg, nextView) {
  P.working = true; renderPanel();
  try {
    const r = await promise;
    P.data = r && r.options ? r : await api('/api/settings');
    if (okMsg) toast(okMsg);
    if (nextView) P.view = nextView;
    P.confirm = null;
    await loadLibrary(); buildRow(true);
    return r;
  } catch (e) { toast(e.message, Math.max(4000, e.message.length * 60)); }  // long enough to read
  finally { P.working = false; renderPanel(); }
}
function renderPanel() {
  if (!P.open) return;
  const typed = {};
  document.querySelectorAll('#panel input').forEach(i => typed[i.dataset.id] = i.value);
  // artwork is told apart by its picture: many pieces share a label ("by" the same artist, or libretro)
  const rowKey = it => it && (it.key || it.id || (it.kind === 'thumb' && it.thumb) || it.label);
  const was = P.focusKey || (P.drawn === P.view ? rowKey(P.items?.[P.focusIdx?.[P.focus]]) : null);
  P.focusKey = null;
  P.items = panelItems();
  const focusable = P.items.map((it, i) => ['row', 'input', 'thumb'].includes(it.kind) ? i : -1).filter(i => i >= 0);
  const same = was ? focusable.findIndex(i => rowKey(P.items[i]) === was) : -1;  // the highlight stays on its row when rows come or go
  P.focus = clamp(same >= 0 ? same : P.focus, 0, focusable.length - 1);
  P.drawn = P.view;
  P.focusIdx = focusable;
  const page = pageMode(), inSide = page && P.side;
  document.body.classList.toggle('settings-page', page);
  if (page) {
    if (SETTINGS.some(c => c.id === catOf(P.view))) P.cat = catOf(P.view);  // Settings opens on it again next time
    $('#panel .pside').innerHTML = `<div class="pside-title">${icon('settings')}<span>Settings</span></div>` +
      SETTINGS.map(c => `<div class="pcat${catOf(P.view) === c.id ? ' cur' : ''}${inSide && catOf(P.view) === c.id ? ' sel' : ''}" data-cat="${c.id}">${icon(c.icon)}<span>${c.label}</span></div>`).join('');
    $('#panel .pside .pcat.cur')?.scrollIntoView({ block: 'nearest' });  // at a large UI scale the categories scroll
  }
  const title = { steam: 'Connect Steam', epic: 'Connect Epic Games', sgdb: 'Connect SteamGridDB', ra: 'Connect RetroAchievements', avatar: 'Profile icon', timezone: 'Time zone', system: P.system, 'add-system': 'Add a system',
    service: GAME_SERVICES.find(s => s.id === P.service)?.name, game: P.game?.title,
    art: `${P.artKind === 'logo' ? 'Logo' : P.artKind === 'hero' ? 'Background' : 'Cover'} · ${P.game?.title}` }[P.view] || SETTINGS.find(c => c.id === P.view)?.label || '';
  $('#panel .ptitle').innerHTML = P.setup && SETUP_STEPS.includes(P.view)
    ? `<span class="psteps">${SETUP_STEPS.map((s, i) => `<i class="${s === P.view ? 'on' : SETUP_STEPS.indexOf(P.view) > i ? 'done' : ''}"></i>`).join('')}</span>${esc(SETUP_TITLES[P.view])}`
    : esc(title);
  $('#panel .pbox').classList.toggle('wide', P.view === 'art');
  // Moving the highlight only moves the highlight: rewriting the list restarted every animated preview and redrew every
  // picture, which flickered. The list is written again only when what it shows has changed.
  const selI = inSide ? -1 : focusable[P.focus], list = $('#panel .plist');
  const draw = s => P.items.map((it, i) => {
    const on = s === i ? ' sel' : '';
    // consecutive thumbs share one grid container
    if (it.kind === 'thumb') return `${P.items[i - 1]?.kind === 'thumb' ? '' : `<div class="pthumbs${P.view === 'avatar' ? ' avatars' : P.artKind === 'logo' ? ' logos' : P.artKind === 'hero' ? ' wide' : ''}">`}<div class="pthumb${on}" data-i="${i}" title="${esc(it.label || '')}">${it.html || (/\.webm(\?|$)/i.test(it.thumb || '')
      // SteamGridDB previews its animated art as short videos: they play here, silent and looping, as the art will
      ? `<video src="${esc(it.thumb)}" muted autoplay loop playsinline preload="auto"></video>`
      : `<img src="${esc(it.thumb)}" alt="" loading="lazy">`)}${it.badge ? `<b class="pbadge">${esc(it.badge)}</b>` : ''}</div>${P.items[i + 1]?.kind === 'thumb' ? '' : '</div>'}`;
    if (it.kind === 'head') return `<div class="phead">${esc(it.label)}</div>`;
    if (it.kind === 'html') return it.html;
    if (it.kind === 'note') return `<div class="pnote${it.warn ? ' warn' : ''}">${esc(it.label)}</div>`;
    if (it.kind === 'input') return `<label class="prow pinput${on}" data-i="${i}"><span>${esc(it.label)}<i class="pkb">${icon('keyboard')}A opens the keyboard</i></span><input data-id="${it.id}" value="${esc(typed[it.id] ?? it.value)}" placeholder="${esc(it.placeholder)}"${it.max ? ` maxlength="${it.max}"` : ''} spellcheck="false" autocomplete="off"></label>`;
    const logo = it.logo || it.img;  // logos are drawn white through a mask; a name with an extension is used as-is
    const lead = logo ? `<span class="ticon plogo ${logo.split('.')[0]}" style="--logo:url(assets/platforms/${logo.includes('.') ? logo : logo + '.svg'})"></span>`
      : it.ic ? `<span class="pic">${it.ic}</span>` : '';
    return `<div class="prow${on}${it.kind === 'info' ? ' info' : ''}${it.primary ? ' primary' : ''}${it.warn ? ' warn' : ''}" data-i="${i}">${it.bar === 'busy' ? '<div class="pbar busy" style="overflow:hidden"><i style="width:30%"></i></div>' : it.bar != null ? `<div class="pbar"><i style="width:${it.bar}%"></i></div>` : ''}<div class="prow-main">${lead ? `<span class="picon-slot">${lead}</span>` : ''}<div><div class="pl">${esc(it.label)}</div>${it.sub ? `<div class="ps">${esc(it.sub)}</div>` : ''}</div></div>${it.value ? `<div class="pv">${esc(it.value)}</div>` : ''}</div>`;
  }).join('');
  const plain = draw(-1);
  if (plain === P.listPlain && list.children.length) list.querySelectorAll('[data-i]').forEach(e => e.classList.toggle('sel', +e.dataset.i === selI));
  else { list.innerHTML = draw(selI); P.listPlain = plain; }
  $('#panel .pbusy').classList.toggle('on', P.working);
  // on the page's own clock (startTime 0), so the bar slides on smoothly when the rows are drawn again
  document.querySelectorAll('#panel .pbar.busy i').forEach(i => { i.animate([{ transform: 'translateX(-100%)' }, { transform: 'translateX(334%)' }], { duration: 1400, iterations: Infinity, easing: 'ease-in-out' }).startTime = 0; });
  const cur = $('#panel .plist .sel');
  // only when the highlight moved: an install's progress redraws twice a second, and scrolling back each time held the
  // list on its row so it couldn't be scrolled with the mouse or by touch
  const at = P.view + '|' + (selI >= 0 ? rowKey(P.items[selI]) || selI : '');
  if (at !== P.scrolledTo) { cur?.scrollIntoView({ block: 'nearest' }); P.scrolledTo = at; }
  const input = cur?.querySelector('input');
  if (input && !SR.open) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }  // typing goes on the end
  else document.activeElement?.blur?.();  // under the on-screen keyboard, real keys type there
}
function enterContent() {
  if (!P.focusIdx?.length) return;
  P.side = false; P.focus = 0; P.confirm = null; tick(700, .05); renderPanel();
}
const thumbCols = () => { const els = [...document.querySelectorAll('#panel .pthumb')]; return els.filter(e => e.offsetTop === els[0]?.offsetTop).length || 1; };
function focusOn(n) { if (n === P.focus) return; P.focus = n; P.confirm = null; tick(640, .04); renderPanel(); }
function panelMove(dy) {
  P.mapping = false;
  if (pageMode() && P.side) {  // moving through the categories shows each one straight away
    const i = SETTINGS.findIndex(c => c.id === catOf(P.view)), n = clamp(i + dy, 0, SETTINGS.length - 1);
    if (n !== i) { P.view = SETTINGS[n].id; P.focus = 0; P.confirm = null; tick(640, .04); renderPanel(); followQueue(); }
    return;
  }
  if (!P.focusIdx?.length) return;
  const thumbs = P.focusIdx.map((i, f) => P.items[i].kind === 'thumb' ? f : -1).filter(f => f >= 0);
  const t = thumbs.indexOf(P.focus);
  if (t >= 0) {  // in the artwork grid, up/down moves a whole row
    const cols = thumbCols(), nt = t + dy * cols;
    if (nt >= 0 && nt < thumbs.length) return focusOn(thumbs[nt]);
    if (dy > 0 && Math.floor(t / cols) < Math.floor((thumbs.length - 1) / cols)) return focusOn(thumbs[thumbs.length - 1]);
    return focusOn(clamp((dy > 0 ? thumbs[thumbs.length - 1] : thumbs[0]) + dy, 0, P.focusIdx.length - 1));
  }
  focusOn(clamp(P.focus + dy, 0, P.focusIdx.length - 1));
}
function setUiVolume(change) {
  S.uiVolume = clamp((S.uiVolume ?? 60) + change, 0, 100);
  save(); tick(760, .08); renderPanel();  // the tick lets you hear the new level
}
function setUiScale(change) {
  S.uiScale = Math.round(clamp(uiScale() + change, SCALE.min, SCALE.max) * 100) / 100;
  applyScale(); save(); tick(760, .08); renderPanel();
}
function panelMoveX(dx) {
  if (!P.side && P.items[P.focusIdx?.[P.focus]]?.adjust) return P.items[P.focusIdx[P.focus]].adjust(dx);
  const onThumb = P.items[P.focusIdx?.[P.focus]]?.kind === 'thumb';
  if (pageMode()) {
    if (P.side && dx > 0) return enterContent();
    if (!P.side && dx < 0 && !SUB_VIEW[P.view]) { P.side = true; P.confirm = null; tick(640, .04); return renderPanel(); }
  }
  if (!onThumb) return;
  const n = P.focus + dx;
  if (P.items[P.focusIdx[n]]?.kind === 'thumb') focusOn(n);
}
function panelActivate() {
  if (P.working) return;
  if (pageMode() && P.side) return enterContent();
  const it = P.items[P.focusIdx[P.focus]];
  if (!it) return;
  tick(880, .08);
  if (it.kind === 'input') return lastSrc === 'key' ? panelMove(1) : fieldKeyboard(it);  // a real keyboard types straight into the field
  Promise.resolve(it.act?.()).catch(e => toast(e.message, 4000));
}
function panelBack() {
  if (P.working) return;
  if (P.mapping) { P.mapping = false; return renderPanel(); }
  if (P.confirm) { P.confirm = null; return renderPanel(); }
  if (P.setup && P.view === 'setup-welcome' && PROFILE.setupDone) {  // run again from About: Settings as it was
    P.setup = false; document.body.classList.remove('setup-mode'); return setView('about');
  }
  if (P.setup) return SUB_VIEW[P.view] ? setView(subReturn()) : setupBack();
  if (!pageMode()) return closePanel();  // artwork dialog from the quick menu or details: straight back
  if (SUB_VIEW[P.view]) return setView(subReturn());
  if (!P.side) { P.side = true; tick(420, .05); return renderPanel(); }
  closePanel();
}
function toggleFS() { (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.())?.catch(() => {}); }  // refused without a click or key

// ---------- input ----------
// Every key and controller button goes through here to whichever layer is on top: panel, then details, then home.
// ---------- Controller tester (Settings > Controllers) ----------
// A Steam Controller is read through the helper (its own report, so it works without Steam or a game); any other pad through the
// browser's Gamepad API, or the helper's copy of its XInput state when Steam Input hides an Xbox pad from the browser. Every
// control lights up on a drawing; LB / RB switch drawings. Hold B or press Esc to leave (B is being tested too).
// [name, byte, bit, x, y] with x, y in the drawing's 830x615 frame. Bits follow SDL's Steam Controller driver; L stick and R stick are thumb touch, by their place among the bits.
const PT_BITS = [['A', 2, 0, 665, 163], ['B', 2, 1, 711, 122], ['X', 2, 2, 618, 120], ['Y', 2, 3, 664, 77], ['Up', 3, 5, 162, 88], ['Down', 3, 2, 162, 160],
  ['Left', 3, 4, 125, 123], ['Right', 3, 3, 200, 123], ['L1', 4, 3, 175, 20], ['R1', 3, 1, 655, 20], ['L2', 5, 3, 110, 40], ['R2', 4, 7, 720, 40], ['Steam', 4, 0, 414, 118],
  ['View', 3, 6, 270, 66], ['Menu', 2, 6, 558, 66], ['...', 2, 4, 414, 333], ['L3', 3, 7, 292, 170], ['R3', 2, 5, 535, 170], ['L pad', 5, 2, 260, 330], ['R pad', 4, 6, 570, 330],
  ['L4', 4, 1, 40, 320], ['L5', 4, 2, 40, 390], ['R4', 2, 7, 790, 320], ['R5', 3, 0, 790, 390], ['L stick', 5, 0, 292, 215], ['R stick', 4, 4, 535, 215]];
const INTRO = { open: false, timer: 0 };
const PT = { open: false, timer: 0, last: null, change: 'Press something', bHeld: 0, live: '', drawn: '', pick: null, padId: '', prev: [] };
const PT_FOOT = { '': 'Press B or Esc, or click, to leave', steam: 'Hold B for 2 seconds, or press Esc, to leave',
  pad: 'Hold B for 2 seconds, press Esc, or click, to leave · LB / RB switch drawings' };
const PT_ART = { steam: ['controller-steam.png', 'Steam Controller'], xbox: ['pad-xbox.png', 'Xbox controller'], ps5: ['pad-ps5.png', 'DualSense'],
  ps4: ['pad-ps4.png', 'DualShock 4'], ps3: ['pad-ps3.png', 'DualShock 3'], sw2: ['pad-sw2.png', 'Pro Controller 2'], sw1: ['pad-sw1.png', 'Pro Controller'] };
const PT_PADS = ['xbox', 'ps5', 'ps4', 'ps3', 'sw2', 'sw1'];
// The standard Gamepad layout's buttons, as pads.json names them (17 is the touchpad on PlayStation pads, Share on Xbox ones)
const PT_STD = ['a', 'b', 'x', 'y', 'lb', 'rb', 'lt', 'rt', 'view', 'menu', 'ls', 'rs', 'dup', 'ddown', 'dleft', 'dright', 'guide', 'touchpad share', 'mic'];
const XI_BITS = [0x1000, 0x2000, 0x4000, 0x8000, 0x100, 0x200, 0, 0, 0x20, 0x10, 0x40, 0x80, 0x1, 0x2, 0x4, 0x8, 0x400];  // XInput's buttons in that order
let PADS_AT = null;  // assets/pads.json: where each control is on each drawing
const pct = (x, y) => `left:${x / 8.3}%;top:${y / 6.15}%`;
function ptName(draw, k) {
  if (draw === 'sw1' || draw === 'sw2')  // Nintendo's letters sit swapped: the bottom button is B, the right one A
    return { dup: 'Up', ddown: 'Down', dleft: 'Left', dright: 'Right', a: 'B', b: 'A', x: 'Y', y: 'X', lb: 'L', rb: 'R', lt: 'ZL', rt: 'ZR', ls: 'L3', rs: 'R3',
      guide: 'Home', view: '−', menu: '+', share: 'Capture' }[k] || '';
  const ps = draw !== 'xbox';
  return { dup: 'Up', ddown: 'Down', dleft: 'Left', dright: 'Right', a: ps ? '✕' : 'A', b: ps ? '○' : 'B', x: ps ? '□' : 'X', y: ps ? '△' : 'Y',
    lb: ps ? 'L1' : 'LB', rb: ps ? 'R1' : 'RB', lt: ps ? 'L2' : 'LT', rt: ps ? 'R2' : 'RT', ls: ps ? 'L3' : 'LS', rs: ps ? 'R3' : 'RS', guide: ps ? 'PS' : 'Xbox',
    view: { xbox: 'View', ps5: 'Create', ps4: 'Share', ps3: 'Select' }[draw], menu: { xbox: 'Menu', ps3: 'Start' }[draw] || 'Options',
    share: 'Share', touchpad: 'Touchpad', mic: 'Mic' }[k] || '';
}
// The drawing for a pad, from the browser's id ('DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6)')
function padDrawing(id) {
  const m = id.match(/vendor:?\s*([0-9a-f]{4}).*?product:?\s*([0-9a-f]{4})/i) || id.match(/^([0-9a-f]{4})-([0-9a-f]{4})-/i);
  const vp = m ? `${m[1]}:${m[2]}`.toLowerCase() : '';
  if (/^057e:/.test(vp)) return vp === '057e:2009' ? 'sw1' : 'sw2';  // Nintendo: the first Pro Controller, else the newer one
  return /^054c:(0ce6|0df2)$/.test(vp) ? 'ps5' : /^054c:(05c4|09cc)$/.test(vp) ? 'ps4' : vp === '054c:0268' ? 'ps3' : 'xbox';
}
const padKnown = id => /xinput|xbox|045e/i.test(id) || padDrawing(id) !== 'xbox';
const padName = id => id.replace(/\s*\([^()]*(STANDARD GAMEPAD|Vendor:|XInput)[^()]*\)\s*$/i, '').replace(/^[0-9a-f]{4}-[0-9a-f]{4}-/i, '').trim() || 'Controller';
function ptBuild(box, draw) {
  const [file, name] = PT_ART[draw];
  PT.drawn = draw;
  const marks = draw === 'steam'
    ? PT_BITS.map(([n, , , x, y]) => `<i class="pt-dot" data-n="${n}" style="${pct(x, y)}"><b>${n}</b></i>`).join('')
      + `<i class="pt-stick" data-axis="l" style="${pct(292, 170)}"></i><i class="pt-stick" data-axis="r" style="${pct(535, 170)}"></i>`
      + `<i class="pt-zone" data-pad="l" style="${pct(260, 330)}"><u></u></i><i class="pt-zone" data-pad="r" style="${pct(570, 330)}"><u></u></i>`
    : Object.entries(PADS_AT?.[draw] || {}).map(([k, c]) => {
      const w = c.r ? c.r * 2 : c.w, h = c.r ? c.r * 2 : c.h, trig = k === 'lt' || k === 'rt';
      return `<i class="pt-ctl${c.r ? ' round' : ''}${trig ? ' pt-trig' : ''}" data-k="${k}" style="left:${(c.x - w / 2) / 8.3}%;top:${(c.y - h / 2) / 6.15}%;width:${w / 8.3}%;height:${h / 6.15}%">`
        + `${trig ? '<u></u>' : ''}<b>${esc(ptName(draw, k))}</b></i>${k === 'ls' || k === 'rs' ? `<i class="pt-stick" data-axis="${k}" style="${pct(c.x, c.y)}"></i>` : ''}`;
    }).join('');
  box.querySelector('.pt-pic').innerHTML = `<img src="assets/${file}" alt="${name}" draggable="false">${marks}`;
}
async function openPadTester() {
  PT.open = true; PT.last = null; PT.bHeld = 0; PT.change = 'Press something'; PT.live = ''; PT.drawn = ''; PT.pick = null; PT.padId = ''; PT.prev = [];
  const box = document.createElement('div');
  box.id = 'padtester';
  box.addEventListener('click', () => PT.last || closePadTester());  // a Steam Controller's pads click like a mouse: while one is in use, Esc or holding B
  box.innerHTML = `<h2>Controller tester</h2><div class="pt-pic"></div>
    <div class="pt-info"><span id="pt-state">Waiting for a controller…</span><span id="pt-change"></span></div>
    <div class="pt-foot">${PT_FOOT['']}</div>`;
  document.body.appendChild(box);
  addEventListener('keydown', padTesterKey, true);
  if (!PADS_AT) PADS_AT = await fetch('assets/pads.json').then(r => r.json()).catch(() => null);
  if (PT.open) padTesterTick();
}
function padTesterKey(e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closePadTester(); } }
function closePadTester() {
  PT.open = false; clearTimeout(PT.timer);
  removeEventListener('keydown', padTesterKey, true);
  $('#padtester')?.remove();
}
function steamTick(box, b) {
  if (PT.drawn !== 'steam') ptBuild(box, 'steam');
  PT_BITS.forEach(([n, byte, bit]) => box.querySelector(`[data-n="${n}"]`).classList.toggle('on', !!(b[byte] >> bit & 1)));
  const word = i => { const v = b[i] | b[i + 1] << 8; return v > 32767 ? v - 65536 : v; };
  const lx = word(10) / 32768, ly = word(12) / 32768;
  // reach is in vh of the full-size 66vh drawing; --ph is its real height
  const nudge = (el, x, y, reach) => { el.style.transform = `translate(calc(-50% + ${x * reach / 66} * var(--ph)), calc(-50% + ${-y * reach / 66} * var(--ph)))`; };
  nudge(box.querySelector('[data-axis="l"]'), lx, ly, 3.4);
  if (b.length >= 30) {
    nudge(box.querySelector('[data-axis="r"]'), word(14) / 32768, word(16) / 32768, 3.4);
    // Touch bits and finger position: the zones light while a finger is on the pad, whether or not it is pressed in
    [['l', 5, 1, 18, 22], ['r', 4, 5, 24, 28]].forEach(([side, byte, bit, at, force]) => {
      const zone = box.querySelector(`[data-pad="${side}"]`), on = !!(b[byte] >> bit & 1);
      zone.classList.toggle('on', on);
      if (on) nudge(zone.firstChild, word(at) / 32768, word(at + 2) / 32768, 5);
      zone.title = on ? `Pressure ${word(force)}` : '';
    });
  }
  box.querySelector('#pt-state').textContent = 'Steam Controller connected: left stick ' + Math.round(lx * 100) + ', ' + Math.round(ly * 100);
  if (PT.last) for (let i = 2; i < 6; i++) for (let k = 0; k < 8; k++) {
    const was = PT.last[i] >> k & 1, now = b[i] >> k & 1;
    if (was !== now && now) {
      const hit = PT_BITS.find(x => x[1] === i && x[2] === k);
      PT.change = `Last pressed: ${hit ? hit[0] : 'not mapped yet'} (byte ${i}, bit ${k})`;
    }
  }
  PT.last = b;
  PT.bHeld = b[2] >> 1 & 1 ? PT.bHeld || performance.now() : 0;
}
// Any other pad, in the standard Gamepad layout: buttons, trigger pressure and both sticks
function padTick(box, pad) {
  if (pad.id !== PT.padId) { PT.padId = pad.id; PT.pick = null; PT.prev = []; PT.change = 'Press something'; }
  const auto = padDrawing(pad.id), on = i => !!pad.pressed[i];
  // LB / RB read here rather than as menu actions: for an Xbox pad those also come through the helper
  [[4, -1], [5, 1]].forEach(([i, dir]) => { if (on(i) && !PT.prev[i]) PT.pick = PT_PADS[(PT_PADS.indexOf(PT.pick || auto) + dir + PT_PADS.length) % PT_PADS.length]; });
  const draw = PT.pick || auto, at = PADS_AT?.[draw] || {}, key = i => (PT_STD[i] || '').split(' ').find(k => at[k]);
  if (PT.drawn !== draw) ptBuild(box, draw);
  PT_STD.forEach((_, i) => {
    const el = key(i) && box.querySelector(`[data-k="${key(i)}"]`);
    if (!el) return;
    const v = pad.buttons[i] || 0, trig = i === 6 || i === 7;
    el.classList.toggle('on', on(i) || trig && v > .04);
    if (trig) el.style.setProperty('--v', v.toFixed(3));
  });
  [['ls', 0], ['rs', 2]].forEach(([k, a]) => {
    const c = at[k], el = box.querySelector(`[data-axis="${k}"]`);
    if (c && el) { el.style.left = `${(c.x + (pad.axes[a] || 0) * c.r * .7) / 8.3}%`; el.style.top = `${(c.y + (pad.axes[a + 1] || 0) * c.r * .7) / 6.15}%`; }
  });
  const hit = pad.pressed.findIndex((p, i) => p && !PT.prev[i]);
  if (hit >= 0) PT.change = `Last pressed: ${ptName(draw, key(hit)) || 'not on this drawing'} (button ${hit})`;
  PT.prev = pad.pressed.slice();
  const name = pad.slot != null ? `Xbox controller (XInput, player ${pad.slot + 1})`
    : /^wireless controller$/i.test(padName(pad.id)) ? PT_ART[auto][1] : padName(pad.id);  // Sony's DualShock 4 is just 'Wireless Controller'
  box.querySelector('#pt-state').textContent = `Detected: ${name}` + (draw !== auto ? ` · showing the ${PT_ART[draw][1]} drawing`
    : !padKnown(pad.id) ? ' · a layout this doesn’t know, shown as an Xbox controller' : '')
    + ` · left stick ${Math.round((pad.axes[0] || 0) * 100)}, ${Math.round(-(pad.axes[1] || 0) * 100)}`;
  PT.bHeld = on(1) ? PT.bHeld || performance.now() : 0;
}
// The browser's pad (standard layout first), or else the helper's XInput copy
async function testerPad() {
  const gp = [...(navigator.getGamepads?.() || [])].filter(Boolean).sort((a, b) => (b.mapping === 'standard') - (a.mapping === 'standard'))[0];
  if (gp) return { id: gp.id, buttons: gp.buttons.map(x => x.value || +x.pressed), pressed: gp.buttons.map(x => x.pressed), axes: [...gp.axes] };
  const x = API ? (await api('/api/xinput').catch(() => null))?.pads?.[0] : null;
  if (!x) return null;
  const buttons = XI_BITS.map((bit, i) => i === 6 ? x.lt / 255 : i === 7 ? x.rt / 255 : +!!(x.buttons & bit));
  return { id: 'xinput', slot: x.slot, buttons, pressed: buttons.map((v, i) => i === 6 || i === 7 ? v > .5 : !!v), axes: [x.lx / 32767, -x.ly / 32767, x.rx / 32767, -x.ry / 32767] };
}
async function padTesterTick() {
  if (!PT.open) return;
  try {
    const r = API ? await api('/api/padraw').catch(() => null) : null, box = $('#padtester');
    const b = (r?.hex?.match(/../g) || []).map(h => parseInt(h, 16));
    if (box && b.length && r.age < 2) { PT.live = 'steam'; steamTick(box, b); }
    else if (box) {
      PT.last = null;  // none (or it went to sleep): one B, Esc or a click leaves again
      const pad = await testerPad();
      PT.live = pad ? 'pad' : '';
      if (pad) padTick(box, pad);
      else {
        PT.bHeld = 0;
        if (!PT.drawn) ptBuild(box, 'xbox');
        box.querySelector('#pt-state').textContent = 'No controller found. Press a button on it, or check it’s plugged in, or paired and switched on.';
      }
    }
    if (PT.bHeld && performance.now() - PT.bHeld > 2000) return closePadTester();
    if (box) { box.querySelector('#pt-change').textContent = PT.live ? PT.change : ''; box.querySelector('.pt-foot').textContent = PT_FOOT[PT.live]; }
  } catch {}
  PT.timer = setTimeout(padTesterTick, 40);
}
function input(action) {
  if (action.startsWith('zoom') && !R.open) return;  // the right stick only zooms a post; elsewhere it does nothing
  if (INTRO.open) return endIntro(true);  // any button skips the intro
  // The launch screen is over everything: B takes it down; nothing else may reach the menus hidden under it
  if (S.busy) return action === 'back' ? cancelLaunch() : undefined;
  if (PT.open) return action === 'back' && !PT.live ? closePadTester() : undefined;  // a controller in use is being tested: its B is held 2 s instead
  if (SP.open) return ({ up: () => sysMove(-1), down: () => sysMove(1), left: () => sysSide(-1), right: () => sysSide(1), ok: sysOk, back: () => SP.view ? sysView('') : closeSys(), system: closeSys })[action]?.();
  if (action === 'system') return Q.open || V.open || P.open ? undefined : openSys();
  const kb = { up: () => searchMove(0, -1), down: () => searchMove(0, 1), left: () => searchMove(-1, 0), right: () => searchMove(1, 0), ok: searchEnter, back: closeSearch,
    options: () => searchType('Delete') };
  const layers = SR.entry ? kb  // the keyboard is over the panel, typing into one of its fields
    : P.open
    ? { up: () => panelMove(-1), down: () => panelMove(1), left: () => panelMoveX(-1), right: () => panelMoveX(1), ok: panelActivate, back: panelBack }
    : Q.open
      ? { up: () => quickMove(-1), down: () => quickMove(1), ok: quickActivate, back: closeQuick, options: closeQuick }
    : V.open
      ? { left: () => showMedia(V.i - 1), right: () => showMedia(V.i + 1), ok: viewerToggle, back: closeViewer, prevTab: () => showMedia(V.i - 1), nextTab: () => showMedia(V.i + 1), options: viewerMore }
    : R.open
      ? { up: () => readerScroll(-1), down: () => readerScroll(1), ok: () => R.update ? readerUpdate() : readerScroll(3), back: closeReader, zoomIn: () => readerZoom(.03), zoomOut: () => readerZoom(-.03), zoomReset: () => readerZoom(0), prevTab: () => readerZoom(-.15), nextTab: () => readerZoom(.15) }
    : AP.open
      ? { up: () => achMove(0, -1), down: () => achMove(0, 1), left: () => achMove(-1, 0), right: () => achMove(1, 0), back: closeAchievements,
          prevTab: () => achTab(-1), nextTab: () => achTab(1) }
    : NP.open
      ? { up: () => newsMove(0, -1), down: () => newsMove(0, 1), left: () => newsMove(-1, 0), right: () => newsMove(1, 0), ok: newsOpen, back: closeNewsPage,
          prevTab: () => newsTab(-1), nextTab: () => newsTab(1) }
    : SR.open
      ? kb
    : HUB.open
      ? { up: () => hubMove(0, -1), down: () => hubMove(0, 1), left: () => hubMove(-1, 0), right: () => hubMove(1, 0), ok: hubOpen, back: closeHub }
    : LP.open
      ? { up: () => lpMove(0, -1), down: () => lpMove(0, 1), left: () => lpMove(-1, 0), right: () => lpMove(1, 0), ok: lpOpen, back: closeLibraryPage,
          prevTab: () => lpCat(-1), nextTab: () => lpCat(1), options: lpSort }
    : AL.open
      ? { up: () => albumMove(0, -1), down: () => albumMove(0, 1), left: () => albumMove(-1, 0), right: () => albumMove(1, 0), ok: albumOpen, back: closeAlbum,
          prevTab: () => albumTab(-1), nextTab: () => albumTab(1), options: () => albumMore() }
    : D.open
      ? { up: () => detailsMove(0, -1), down: () => detailsMove(0, 1), left: () => detailsMove(-1, 0), right: () => detailsMove(1, 0), ok: detailsActivate, back: detailsBack, options: () => openQuick(D.game) }
      : { up: () => move(0, -1), down: () => move(0, 1), left: () => move(-1, 0), right: () => move(1, 0), ok: activate, back,
          options: () => openQuick(game()), prevTab: () => setTab(S.tab - 1), nextTab: () => setTab(S.tab + 1) };
  layers[action]?.();
}
const KEYS = { arrowup: 'up', arrowdown: 'down', arrowleft: 'left', arrowright: 'right', enter: 'ok', escape: 'back', f2: 'system' };
const LETTER_KEYS = { w: 'up', s: 'down', a: 'left', d: 'right', ' ': 'ok', backspace: 'back', o: 'options', contextmenu: 'options',
  q: 'prevTab', e: 'nextTab', pageup: 'prevTab', pagedown: 'nextTab' };
// Directions repeat on our own timer while the key is down. Controllers that Steam turns into keyboard
// presses (Steam Input "desktop" mode) never auto-repeat, so the OS repeat can't be relied on.
const DIRS = new Set(['up', 'down', 'left', 'right']);
const keyHold = {};
function stopKeyHolds() { Object.values(keyHold).forEach(clearTimeout); for (const k in keyHold) delete keyHold[k]; }
const recentKeys = [];
addEventListener('keydown', e => {
  const k = e.key.toLowerCase(), typing = e.target.tagName === 'INPUT' && !SR.entry;
  if (!e.repeat) { recentKeys.unshift(e.key === ' ' ? 'Space' : e.key); recentKeys.length = Math.min(recentKeys.length, 6); }
  if (P.mapping && !e.repeat) {  // Controllers screen is waiting for the quick-menu button
    e.preventDefault();
    P.mapping = false;
    if (k !== 'escape' && !KEYS[k]) { S.optKey = k; save(); toast(`Quick menu set to that button (${e.key === ' ' ? 'Space' : e.key})`); }
    return renderPanel();
  }
  if (e.ctrlKey && ['+', '-', '=', '0'].includes(e.key)) return e.preventDefault();  // no page zoom: Settings › General › UI scale does that
  if (S.busy) {  // the launch screen: only B (Esc, Backspace) does anything
    const a = KEYS[k] || LETTER_KEYS[k];
    if (a) { e.preventDefault(); if (!e.repeat) inputFrom('key', a); }
    return;
  }
  // Quick Access over the Library page or Search takes the keys itself
  if (LP.open && !SR.open && !P.open && !SP.open && !e.ctrlKey && !e.altKey && !e.metaKey && e.key.length === 1 && /[a-z0-9]/i.test(e.key) && k !== S.optKey
      && !LETTER_KEYS[k]) { e.preventDefault(); openSearch(LP.mode); return searchKey(e.key); }  // typing on the Library page searches it
  if (SR.open && !SP.open && !e.ctrlKey && !e.altKey && !e.metaKey) {
    if (e.key === 'Backspace') { e.preventDefault(); searchType('Delete'); return afterKey(); }
    if (SR.entry && e.key.length === 1 && k !== S.optKey) { e.preventDefault(); return entryKey(e.key); }
    if (e.key.length === 1 && /[a-z0-9 ]/i.test(e.key) && k !== S.optKey) { e.preventDefault(); return searchKey(e.key); }
  }
  if (SR.entry && e.ctrlKey && k === 'v') { e.preventDefault(); kbToDone(); searchFocus(); return searchType('Paste'); }
  if (!typing && S.optKey && k === S.optKey && (!P.open || SR.entry)) { e.preventDefault(); if (!e.repeat) input('options'); return; }
  // While typing in a field, only up/down/Enter/Esc belong to the panel; everything else types.
  let act = KEYS[k] || (!typing && (P.open ? (k === ' ' ? 'ok' : null) : LETTER_KEYS[k]));
  if (typing && (k === 'arrowleft' || k === 'arrowright')) act = null;
  if (act && DIRS.has(act)) {
    e.preventDefault();
    if (e.repeat || keyHold[k]) return;
    const start = performance.now();
    inputFrom('key', act);
    const again = () => { inputFrom('key', act); keyHold[k] = setTimeout(again, performance.now() - start > 1500 ? 55 : 105); };
    keyHold[k] = setTimeout(again, 340);
  } else if (act) { e.preventDefault(); if (!e.repeat) inputFrom('key', act); }
  else if (!typing && !P.open && k === 'f') toggleFS();
  else if (!typing && !P.open && k === 'm') { S.sound = !S.sound; save(); toast(`Sound ${S.sound ? 'on' : 'off'}`); }
  S.pad = false;
});
addEventListener('keyup', e => { const k = e.key.toLowerCase(); clearTimeout(keyHold[k]); delete keyHold[k]; });
addEventListener('blur', stopKeyHolds);
let wheelAt = 0;
addEventListener('wheel', e => {
  if (e.ctrlKey) return e.preventDefault();  // Ctrl + wheel (and a touchpad pinch) would zoom the page
  if (P.open || D.open || R.open || V.open || Q.open || NP.open || AL.open || SR.open || LP.open || HUB.open || SP.open) return;  // only the home row, not under a page or menu
  const now = performance.now(); if (now - wheelAt < 90) return; wheelAt = now;
  if (S.zone !== 0) { S.zone = 0; update(); }
  move(Math.sign(e.deltaY || e.deltaX), 0);
}, { passive: false });
// No pinch zoom either (styles.css touch-action says so too, but a window doesn't always honour it)
addEventListener('touchmove', e => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
// Touch: a sideways drag over the covers moves along the row, one cover per cover-width dragged. The tap that ends a
// drag doesn't open anything.
const SWIPE = { id: null, x: 0, moved: false };
strip.addEventListener('pointerdown', e => { SWIPE.moved = false; if (e.pointerType === 'touch' && !S.busy) Object.assign(SWIPE, { id: e.pointerId, x: e.clientX }); });
strip.addEventListener('pointermove', e => {
  if (e.pointerId !== SWIPE.id) return;
  const step = (STRIP.w + STRIP.gap) * uiScale() || innerWidth / 8;  // the row is scaled with the UI
  while (Math.abs(e.clientX - SWIPE.x) >= step) {
    const d = e.clientX < SWIPE.x ? 1 : -1;
    SWIPE.x -= d * step; SWIPE.moved = true;
    if (S.zone !== 0) S.zone = 0;
    move(d, 0);
  }
});
['pointerup', 'pointercancel'].forEach(t => strip.addEventListener(t, e => { if (e.pointerId === SWIPE.id) SWIPE.id = null; }));
strip.addEventListener('click', e => {
  if (SWIPE.moved) { SWIPE.moved = false; return; }
  const t = e.target.closest('.tile'); if (!t) return;
  const i = +t.dataset.i;
  S.zone = 0;
  if (i === idx()) activate(); else { select(i); tick(760, .035, .022); save(); update(); }
});
let idleT;
let mouseAt = null;  // a window opening under a still pointer fires one move: only real movement shows it
addEventListener('mousemove', e => { const at = e.screenX + ',' + e.screenY, first = !mouseAt, same = at === mouseAt; mouseAt = at; if (first || same) return; pointerUsed(true); document.body.classList.remove('idle'); clearTimeout(idleT); idleT = setTimeout(() => document.body.classList.add('idle'), 2500); });
// The mouse's own Back button works like B everywhere, so a mouse can leave pages that have nothing to click to close them
addEventListener('mouseup', e => { if (e.button === 3) { e.preventDefault(); safely(() => inputFrom('mouse', 'back')); } });
// Touch and mouse: one round back button over every page and menu, doing what B does on the top one. It shows once a
// pointer is used and goes again with the controller or the keys, so a controller-only screen never has it.
const pointerUsed = on => document.body.classList.toggle('ptr', on);
document.body.classList.add('idle');  // no pointer at start: it shows once the mouse moves
addEventListener('pointerdown', () => pointerUsed(true), { capture: true, passive: true });
$('#backbtn').addEventListener('click', () => PT.open ? closePadTester() : inputFrom('mouse', 'back'));
// The corner with the name and the clock opens Quick Access (the controller's View or Steam button), for touch
$('header').addEventListener('click', e => { if (e.target.closest('.user, .status')) inputFrom('mouse', 'system'); });
// The platform tabs fade when not in use and can't be tapped then: a touch or the mouse at the bottom brings them back
function peekTabs() { document.body.classList.add('tabs-peek'); clearTimeout(tabsPeekT); tabsPeekT = setTimeout(() => document.body.classList.remove('tabs-peek'), 2500); }
let tabsWereHidden = false;  // the touch that brings them back doesn't also pick one
$('footer').addEventListener('pointerdown', () => { tabsWereHidden = !document.body.matches('.zone-2, .tabs-peek'); peekTabs(); });
$('footer').addEventListener('pointermove', e => { if (e.pointerType === 'mouse') peekTabs(); });
// Settings by mouse: the right button goes back as B does (not in a text field, which keeps its own menu), and a click
// beside a dialog (the artwork picker) closes it
$('#panel').addEventListener('contextmenu', e => { if (e.target.closest('input')) return; e.preventDefault(); if (!SR.open) inputFrom('mouse', 'back'); });
$('#panel').addEventListener('click', e => { if (e.target.id === 'panel' && !P.setup && !pageMode()) panelBack(); });
let wallT;  // the scenery is redrawn for the new shape once resizing settles
addEventListener('resize', () => { sizeCanvases(); placeStrip(false); tabsInView(false); clearTimeout(wallT); wallT = setTimeout(buildWallpaper, 250); });
document.addEventListener('fullscreenchange', () => setTimeout(() => placeStrip(false), 50));

// Gamepad (standard mapping): d-pad / left stick with key-repeat, A select, B back, LB/RB source, Start fullscreen.
const held = {};
// Holding a direction repeats after a short pause, and speeds up after holding for a while.
function rep(k, on, t, fn) {
  if (!on) return void delete held[k];
  const h = held[k];
  if (!h) { held[k] = { next: t + 340, start: t }; safely(fn); }
  else if (t >= h.next) { h.next = t + (t - h.start > 1500 ? 55 : 105); safely(fn); }
}
function edge(k, on, fn) { if (on && !held[k]) { held[k] = 1; safely(fn); } else if (!on) delete held[k]; }
// A failing handler must never stop the polling loop, or the controller goes dead until a reload.
function safely(fn) { try { const r = fn(); r?.catch?.(e => console.error(e)); } catch (e) { console.error(e); } }
// ---------- controller through the helper ----------
// The helper reads XInput itself (Xbox pads, and a Steam Controller or any pad Steam Input presents as an Xbox pad) and
// sends each action here, so the controller works even when the browser's gamepad support doesn't see it.
const HP = { live: false, seq: 1e12, pads: 0 };
async function helperPad() {
  for (;;) {
    try {
      const r = await (await fetch(`/api/pad?after=${HP.seq}`, { cache: 'no-store' })).json();
      HP.live = true; HP.pads = r.pads;
      // Every page open on the helper hears the controller: only Ultra Front End's own window acts on it, or a browser tab
      // you're looking at. A tab in the background (or a test page) pressing along opened program pickers by itself.
      const mine = window.pywebview || window.AndroidApp || (document.visibilityState === 'visible' && document.hasFocus());
      if (mine) r.actions.forEach(a => { S.pad = true; inputFrom('xinput', a); });
      HP.seq = r.seq;
    } catch {
      HP.live = false;
      await new Promise(res => setTimeout(res, 3000));
    }
  }
}
// One press can arrive twice: from the helper and as a key Steam Input types for the same controller. Count it once.
const LAST_INPUT = {};
let lastSrc = null;  // 'key', 'xinput', 'pad' or 'mouse': A on a text field opens the on-screen keyboard unless it came from a real keyboard
function inputFrom(src, act) {
  wake(); lastActive = Date.now();
  const now = performance.now(), last = LAST_INPUT[act];
  if (last && last.src !== src && now - last.t < 220) return;
  LAST_INPUT[act] = { src, t: now }; lastSrc = src;
  if (src !== 'mouse') { pointerUsed(false); document.body.classList.add('idle'); }  // a controller or the keyboard: the mouse pointer goes until the mouse moves
  safely(() => input(act));
}
const PAD_ICON = $('#pad');
function poll() {
  requestAnimationFrame(poll);
  const t = performance.now();
  // XInput pads already come through the helper; the browser handles the rest (DualSense, Switch Pro, any pad on a Mac)
  // Only while this window has the focus: a browser reads the pad even behind a game, so B there opened the Exit menu here
  const gp = !document.hasFocus() ? null : [...(navigator.getGamepads?.() || [])].find(p => p && !(HP.live && HP.pads && /xinput|xbox/i.test(p.id)));
  if (gp) {
    const b = n => !!gp.buttons[n]?.pressed, ax = n => gp.axes[n] || 0;
    if (!S.pad && (gp.buttons.some(x => x.pressed) || gp.axes.some(a => Math.abs(a) > .5))) S.pad = true;
    rep('u', b(12) || ax(1) < -.55, t, () => inputFrom('pad', 'up'));
    rep('d', b(13) || ax(1) > .55, t, () => inputFrom('pad', 'down'));
    rep('l', b(14) || ax(0) < -.55, t, () => inputFrom('pad', 'left'));
    rep('r', b(15) || ax(0) > .55, t, () => inputFrom('pad', 'right'));
    edge('A', b(0), () => inputFrom('pad', 'ok'));
    edge('B', b(1), () => inputFrom('pad', 'back'));
    edge('Y', b(3), () => inputFrom('pad', 'options'));
    edge('LB', b(4), () => inputFrom('pad', 'prevTab'));
    edge('RB', b(5), () => inputFrom('pad', 'nextTab'));
    edge('VW', b(8), () => inputFrom('pad', 'system'));
    edge('ST', b(9), () => inputFrom('pad', 'options'));  // Start, like Y: the game's menu
    edge('L3R3', b(10) && b(11), () => inputFrom('pad', 'zoomReset'));
    if (Math.abs(ax(3)) > .35 && t - (poll.zoomT || 0) > 50) { poll.zoomT = t; inputFrom('pad', ax(3) < 0 ? 'zoomIn' : 'zoomOut'); }
  }
  const padIcon = gp ? 'on' : 'off';
  if (PAD_ICON.dataset.s !== padIcon) { PAD_ICON.dataset.s = padIcon; PAD_ICON.innerHTML = gp ? icon('pad') : ''; }
  if (P.open && P.view === 'pad') padLive();
}
// Controllers screen: shows what the browser sees, to sort out controllers with unusual button layouts.
const PAD_NAMES = ['A', 'B', 'X', 'Y', 'LB', 'RB', 'LT', 'RT', 'View', 'Menu', 'L3', 'R3', 'Up', 'Down', 'Left', 'Right', 'Guide'];
function padLive() {
  const el = $('#padlive'); if (!el) return;
  const pads = [...(navigator.getGamepads?.() || [])].filter(Boolean);
  const keys = `<br><br><b>Keys received:</b> ${recentKeys.length ? recentKeys.map(esc).join(', ') : 'none yet'}`;
  el.innerHTML = ON_MAC && !pads.length && HP.pads  // a Mac reads controllers through macOS (the helper), not the page
    ? `<b>Controller connected</b> (${HP.pads === 1 ? 'one' : HP.pads}). Ultra Front End reads it through macOS.${keys}`
    : ON_MAC && !pads.length ? `<b>No controller connected.</b> Pair it in System Settings › Bluetooth, or plug it in with a cable.${keys}`
    : !pads.length
    ? `<b>No controller seen directly.</b> If pressing its buttons adds entries below, Steam is turning your controller into keyboard keys (Steam Input desktop mode). Add the frontend to Steam as a non-Steam game and open it from there, or use “Set the quick-menu button” above for Y.${keys}`
    : pads.map(p => {
      const down = p.buttons.map((x, i) => x.pressed ? `${i}${p.mapping === 'standard' && PAD_NAMES[i] ? ` (${PAD_NAMES[i]})` : ''}` : null).filter(Boolean);
      return `<b>${esc(p.id)}</b><br>${p.mapping === 'standard' ? 'Standard layout' : 'Non-standard layout: buttons may be mixed up'} · ${p.buttons.length} buttons<br>Pressed now: ${down.length ? down.join(', ') : 'nothing'}`;
    }).join('<br><br>') + keys;
}
function clock() { $('#clock').textContent = timeIn(PROFILE.timezone); }

// ---------- boot ----------
drawButtons();
$('#buttons').addEventListener('click', e => { const b = e.target.closest('.btn'); if (b) { S.zone = 1; S.btn = +b.dataset.i; update(); activate(); } });
$('#tabs').addEventListener('click', e => { const t = e.target.closest('.tab'); if (t && !tabsWereHidden) setTab(+t.dataset.i); tabsWereHidden = false; });
strip.addEventListener('contextmenu', e => {
  const t = e.target.closest('.tile'); if (!t) return;
  e.preventDefault(); S.zone = 0; select(+t.dataset.i); update(); openQuick(game());
});
$('#panel .pside').addEventListener('click', e => {
  const c = e.target.closest('.pcat'); if (!c) return;
  P.view = c.dataset.cat; P.focus = 0; P.confirm = null; P.side = false; tick(640, .04); renderPanel(); followQueue();
});
$('#panel .plist').addEventListener('click', e => {
  const r = e.target.closest('.prow, .pthumb'); if (!r || SR.open || r.classList.contains('info')) return;
  if (r.classList.contains('pinput')) e.preventDefault();  // the label would pass the click on to its field and focus it under the keyboard
  P.side = false;
  P.focus = P.focusIdx.indexOf(+r.dataset.i); P.confirm = P.confirm && P.items[+r.dataset.i]?.key === P.confirm ? P.confirm : null;
  lastSrc = 'mouse'; panelActivate();
});
buildWallpaper();
sizeCanvases();
clock(); setInterval(clock, 5000);
W.raf = requestAnimationFrame(drawWorld);
requestAnimationFrame(poll);
// The helper quits a while after the UI is closed (when started by Start Frontend.bat); the ping also picks up new games.
if (API) setInterval(watchLibrary, 5000);
if (API) setInterval(watchRunning, 3000);
// A quiet warning when the controller runs low, once per charge
let lowWarned = false;
if (API) setInterval(async () => {
  const b = (await api('/api/padraw').catch(() => ({}))).battery;
  if (b == null) return;
  if (b > 20) lowWarned = false;
  else if (b <= 15 && !lowWarned) { lowWarned = true; toast(`Controller battery low: ${b}%`, 6000); }
}, 60000);
if (API) helperPad();
renderProfile();
runIntro();
// Nothing shows until the games and background are ready, then it all fades in together. The timer means it can never stay dark.
const pageReady = () => document.body.classList.add('ready');
setTimeout(pageReady, 4000);
const firstRow = loadLibrary().then(() => buildRow(true));
let firstSettings = Promise.resolve();
if (API) {
  firstSettings = api('/api/settings').then(d => {
    PROFILE = d.profile; renderProfile();
    S.artBg = d.options.artBackground; applyBackgroundMode();
    if (!PROFILE.setupDone) openSetup();  // first launch: the setup guide
  }).catch(() => {});
}
Promise.all([firstRow, firstSettings]).then(() => {
  const t0 = performance.now();
  const wait = () => !S.artBg || $('#gamebg').children.length || performance.now() - t0 > 1200 ? pageReady() : setTimeout(wait, 40);
  wait();
}).catch(pageReady);
