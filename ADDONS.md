# Writing an add-on for Ultra Front End

An add-on is one JavaScript file that the app loads when someone installs it from **Settings › Add-ons**. It can draw
by the clock, over the home screen or at the top of Quick Access, add its own rows to Quick Access and Settings, react
to games starting and stopping, to the song playing and to the controller, and keep its own settings and data.

Everything an add-on adds through its `api` (listeners, timers, styles, elements, rows) is taken away when it's
removed, so it leaves nothing behind.

## Your own add-ons, loaded live

You don't need to rebuild the app to try one. In **Settings › Add-ons**, choose **Add-ons folder**: it opens
`dataddons` next to the app. Give each add-on a folder of its own there, with:

- `addon.json`: the same entry as in the catalogue below, with `script` and `icon` as file names in that folder
- the script, and its icon if it has one

It shows up in Settings › Add-ons within a few seconds. Install it there, and from then on every time you save the
script it's taken down and loaded again by itself, so you see your changes at once.

## The catalogue

`app/addons/catalog.json` lists the add-ons people can install:

```json
{
  "id": "weather",
  "title": "Weather",
  "description": "What it does, in one or two sentences.",
  "author": "Your name",
  "version": "1.0",
  "icon": "addons/weather.png",
  "script": "addons/weather.js"
}
```

The icon is a square picture (256 × 256 works well).

## The script

```js
UFE.addon({
  id: 'weather',                  // the same id as in the catalogue
  mount(api) { /* draw it */ },   // runs when it's installed, and every time the app starts
  unmount(api) { /* tidy up */ }, // runs when it's removed, and before a settings change redraws it
  options(api) { return [ /* rows for its page in Settings › Add-ons */ ]; },
});
```

## What `api` gives you

### Places to draw

| | |
|---|---|
| `api.add('header', element)` | puts your element next to the clock |
| `api.add('home', element)` | a layer over the home screen (hidden while a menu or page is open); position your element yourself |
| `api.add('quickaccess', element)` | under the time at the top of Quick Access |
| `api.slot(name)` | the place itself, if you'd rather add to it yourself (then remove your element in `unmount`) |
| `api.css(text)` | adds a stylesheet; give your classes your add-on's id as a prefix |
| `api.icon(name)` | one of the app's own icons as SVG text (`'music'`, `'pad'`, `'wifi'`, `'bell'`, `'star'`, ...) |

### Quick Access rows

```js
api.quickAccess(() => [
  { icon: 'music', label: 'Lyrics', sub: 'Shows the words to the song', value: 'Off', run: () => { ... } },
]);
api.refresh();  // redraws Quick Access, after something in your rows changed
```

Your rows fold under one row of their own, like Sound and Batteries. Give it a title and icon with
`api.quickAccess(rows, { title: '3D printer', icon: 'printer' })` (your add-on's title if you don't).
`rows()` is asked for each time Quick Access is drawn. Rows without `run` are just information.

### A card over the game

```js
api.hud({ icon: 'printer', text: 'Benchy', sub: '42% · 1 h 10 min left', progress: 42 });
api.hud(null);  // takes it away
```

A small card in the top-left corner over the game you're playing. It never takes the focus or the clicks, so the
game keeps the controller. It's only there while a game is running, and hides while the in-game menu is open. Send
it again at least every two minutes (an `api.every` does it), or it's taken away. Icons: `printer`, `bolt`, `music`,
`clock`, `pad`, `bell`, `star`. The Bambu Lab add-on (`app/addons/bambu.js`) is a full example.

### Events

```js
api.on('game:start', ({ game }) => { ... });
```

| Event | What comes with it |
|---|---|
| `game:start` | `{ game }`: a game was launched from the app |
| `game:running` | `{ games }`: the ids of the games running now, whenever that changes |
| `game:exit` | `{ game }`: a game stopped |
| `song` | `{ title, artist, playing, art }`, or `null` when nothing is playing (checked every 5 seconds while you listen) |
| `quickaccess:open` / `quickaccess:close` | |
| `input` | the action pressed: `'up'`, `'down'`, `'left'`, `'right'`, `'ok'`, `'back'`, `'options'`, `'system'`, ... Return `true` to take the press, so the app doesn't act on it (only do that while your own thing is on screen) |
| `library` | the number of games, when the library has loaded |

`api.on` returns a function that stops listening.

### Games

| | |
|---|---|
| `api.games()` | every game: `{ id, title, platform, cover, installed, lastPlayed, favorite }` |
| `api.game(id)` | one game, or `null` |
| `api.running()` | the games running now |
| `api.launch(id)` | starts a game, with the app's own launch screen |

### Music and sound

| | |
|---|---|
| `await api.nowPlaying()` | the song Windows is playing, or `null` |
| `api.media('play' \| 'next' \| 'prev')` | the media controls |
| `await api.volume()` / `api.setVolume(delta)` | the PC's volume (`{ volume, muted }`), and turning it up or down |
| `api.sound(pitch, level)` | one of the app's small interface sounds |

### The person and the app

| | |
|---|---|
| `api.profile()` | `{ name, avatar, timezone }` |
| `api.timezone()` | the time zone chosen in Settings › Profile |
| `api.toast(text, ms)` | a short message at the bottom of the screen |
| `api.ask(label, done)` | the on-screen keyboard, for typing something in |
| `api.openSettings()` | opens Settings |
| `await api.request(path, body)` | the app's own server (GET without a body, POST with one), for an add-on with a part on the server, like Bambu Lab's `/api/bambu` |

### Saving things

| | |
|---|---|
| `api.settings()` | your saved settings |
| `api.saveSettings({ ... })` | saves settings; your add-on is redrawn with them |
| `api.store.get(key, fallback)` / `api.store.set(key, value)` / `api.store.remove(key)` | a small store for anything else (lists, the last reading); values are saved as JSON |

### Timers

`api.every(ms, fn)` (at most once a second) and `api.after(ms, fn)` work like `setInterval` and `setTimeout`, but are
stopped for you when the add-on is removed.

### Rows in Settings

A row in `options()` looks like `{ kind: 'row', label: 'Show humidity', value: 'On', act: () => { ... } }`.

## An example

A small add-on that counts how many games you've started today and shows it by the clock:

```js
UFE.addon({
  id: 'today',
  mount(api) {
    const el = document.createElement('span');
    el.className = 'today-count';
    api.add('header', el);
    const day = () => new Date().toDateString();
    const draw = () => { const s = api.store.get('count', { day: day(), n: 0 }); el.textContent = s.day === day() ? `${s.n} today` : ''; };
    api.on('game:start', () => {
      const s = api.store.get('count', { day: day(), n: 0 });
      api.store.set('count', s.day === day() ? { ...s, n: s.n + 1 } : { day: day(), n: 1 });
      draw();
    });
    api.quickAccess(() => [{ icon: 'pad', label: 'Games started today', value: String(api.store.get('count', { n: 0 }).n) }]);
    draw();
  },
});
```

## Submitting one

Open a pull request on [the project](https://github.com/ImSammyTTV/Ultra-Front-End) that adds your script and icon to
`app/addons/` and an entry to `catalog.json`. Keep it small, use only free services that need no account, and say
which sites it talks to in its description.
