# Writing an add-on for Ultra Front End

An add-on is one JavaScript file that the app loads when someone installs it from **Settings › Add-ons**.

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
  id: 'weather',                 // the same id as in the catalogue
  mount(api) { /* draw it */ },  // runs when it's installed, and every time the app starts
  unmount(api) { /* tidy up */ },// runs when it's removed (and before a settings change redraws it)
  options(api) { return [ /* rows for its page in Settings › Add-ons */ ]; },
});
```

What `api` gives you:

| | |
|---|---|
| `api.slot('header')` | the place next to the clock, to add your own element to |
| `api.settings(id)` | this add-on's saved settings |
| `api.saveSettings(id, { ... })` | save settings; the add-on is redrawn with them |
| `api.timezone()` | the time zone chosen in Settings › Profile |
| `api.ask(label, done)` | the on-screen keyboard, for typing something in |
| `api.toast(text)` | a short message at the bottom of the screen |

A row in `options()` looks like `{ kind: 'row', label: 'Show humidity', value: 'On', act: () => { ... } }`.

## Submitting one

Open a pull request on [the project](https://github.com/ImSammyTTV/Ultra-Front-End) that adds your script and icon to
`app/addons/` and an entry to `catalog.json`. Keep it small, use only free services that need no account, and say
which sites it talks to in its description.
