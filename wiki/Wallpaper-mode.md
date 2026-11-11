# Wallpaper mode (Windows)

Ultra Front End can be your desktop: your games behind the desktop icons, live, and usable with the mouse, a
controller, the mouse wheel and (if you switch it on) the keyboard. It uses
[Wallpaper Engine](https://store.steampowered.com/app/431960/Wallpaper_Engine/), which you'll need.

## Setting it up

1. Turn on **Settings › General › Start with Windows** (either **Open the frontend** or **Start in the background**).
   The wallpaper shows Ultra Front End, so it needs to be running.
2. Choose **Settings › General › Use as your wallpaper (Wallpaper Engine)**. It opens in Wallpaper Engine as your
   wallpaper. (If Wallpaper Engine isn't found, its folder opens instead: in Wallpaper Engine choose **Open Wallpaper**
   and that folder's `project.json`.)

If Ultra Front End isn't running yet, the wallpaper says **Waiting for Ultra Front End…** and shows it as soon as it starts.

## Using it

Click an empty spot on the desktop first, so the desktop is the window in front. Then:

| | |
|---|---|
| **Mouse** | Click games, buttons and menus. **Play** starts a game as usual. |
| **Controller** | Xbox-style controllers and the Steam Controller move around as on the home screen. |
| **Mouse wheel** | Moves along the row, and scrolls lists like the Library. |
| **Keyboard** | Off unless you turn on **Settings › General › Type on the wallpaper**. Then it types into Search and Rename and moves around. |

While any other window is in front, none of these reach the wallpaper.

## Safety

The wallpaper can't shut down, restart or sleep the PC, quit Ultra Front End, close a game, or delete or remove
anything. Those are refused both in the wallpaper and by Ultra Front End itself. Keys Wallpaper Engine passes to it
directly are ignored, since they can arrive from other windows.

## Good to know

- **Enter on the desktop** also opens a selected desktop icon. Hiding the desktop icons (right-click the desktop ›
  **View › Show desktop icons**) avoids that.
- With a **Steam Controller**, Steam still moves the mouse pointer with its trackpads on the desktop.
- Wallpaper Engine pauses the wallpaper while a game or other fullscreen app is in front.
- **Something not reaching it?** Open `http://127.0.0.1:8137/api/wallpaper` in a browser (not as a wallpaper). It shows
  whether the wallpaper is checking in and what Windows said was in front.
