# Ultra Front End for Android

The Android app shows the same page as Windows and Mac (`../app/`, packed into the APK's assets) in a full-screen WebView.
A small server inside the app answers the page's `/api` calls on `127.0.0.1:8137` with the same shapes as `server.py`,
so `app.js` runs unchanged apart from a few `ON_ANDROID` branches.

| File | What it does |
|---|---|
| `MainActivity.kt` | The full-screen WebView, the controller (keys and sticks become the page's actions), the folder picker and permission screens |
| `HttpServer.kt` | The page's server on 127.0.0.1:8137 (this device only) |
| `Backend.kt` | The `/api` routes: library, settings, systems, ROMs folder, volume, sounds, updates, what's new |
| `Library.kt` | Finds Android games (apps marked as games) and ROMs (`ROMs/<console>/`), draws or fetches covers |
| `Launcher.kt` | Starts Android games, and ROMs in an emulator with the intent from `assets/systems.json` |
| `Pad.kt` | Controller actions for the page's long poll (`/api/pad`) |
| `Store.kt` | The app's JSON files (`config.json`, `overrides.json`, `play.json`) and the systems table |

## Emulators

`app/src/main/assets/systems.json` lists every console, its ROM extensions and the Android emulators that play it,
with the intent that starts a game. It is made from ES-DE's Android tables (MIT, see `THIRD_PARTY_NOTICES.md`):

```
python tools/make_android_tables.py <folder with ES-DE's resources/systems/android/es_systems.xml and es_find_rules.xml>
```

Each console's games start in the emulator chosen in Settings › Systems, or else the first one installed.

## Building

Needs JDK 17 and the Android SDK (platform 35, build-tools 35). `local.properties` (not in git) points at the SDK:
`sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk`.

```
gradlew assembleDebug      # app/build/outputs/apk/debug/app-debug.apk
gradlew assembleRelease    # signed with the release key, if there is one
```

The version comes from `VERSION` in `../server.py`, so every platform shares one number.

## The release key

Updates only install over a copy signed with the same key, so the key must never change or be lost. It is kept
outside the repo: `%LocalAppData%\Ultra Front End\android-key.properties` (or the file named by `UFE_ANDROID_KEY`) with

```
storeFile=C:/path/to/android-release.jks
storePassword=...
keyAlias=ultrafrontend
keyPassword=...
```

Back up the `.jks` and its passwords. Without the file the release build is signed with the debug key.

## Testing

An emulator works for everything except real controllers and real emulator apps. Debug builds allow WebView
debugging: `adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>`, then any DevTools client.
