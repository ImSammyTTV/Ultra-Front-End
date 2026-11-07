# Third-party notices

Ultra Front End is MIT (see [LICENSE](LICENSE)), but the Windows exe also contains the software below, each under its own licence. The full licence texts are in the [licenses](licenses) folder, which ships inside the exe and with every release.

## What the exe contains

| Name | Version | Licence | Link |
|---|---|---|---|
| CPython (python312.dll and the standard library) | 3.12.10 | [PSF License (Python-2.0)](licenses/Python-LICENSE.txt) | https://www.python.org |
| OpenSSL, inside CPython (libssl-3.dll, libcrypto-3.dll) | 3.0.16 | [Apache-2.0](licenses/Python-LICENSE.txt) | https://www.openssl.org |
| Tcl/Tk, inside CPython (folder picker) | 8.6.15 | [Tcl/Tk licence](licenses/Python-LICENSE.txt) | https://www.tcl-lang.org |
| Other libraries inside CPython: bzip2 1.0.8, libffi, zlib 1.3.1, expat 2.7.1, libmpdec 2.5.1, liblzma (xz) | as listed | [their own licences](licenses/Python-incorporated-software.txt) | https://docs.python.org/3.12/license.html |
| Microsoft Visual C++ runtime (VCRUNTIME140.dll, VCRUNTIME140_1.dll), from the Python install | 14.42.34438 | Microsoft Distributable Code, under the "Additional Conditions for this Windows binary build" in [Python-LICENSE.txt](licenses/Python-LICENSE.txt) | https://docs.python.org/3.12/license.html |
| PyInstaller bootloader and loader | 6.22.3 | [GPL-2.0-or-later with the Bootloader Exception](licenses/PyInstaller-COPYING.txt), which lets the exe ship under any licence | https://pyinstaller.org |
| PyInstaller run-time hooks (pyi_rth_inspect, pyi_rth_pkgutil, pyi_rth_multiprocessing, pyi_rth__tkinter) | 6.22.3 | [Apache-2.0](licenses/PyInstaller-COPYING.txt) | https://github.com/pyinstaller/pyinstaller |
| pywebview (incl. WebBrowserInterop.x64.dll / x86.dll) | 6.2.1 | [BSD-3-Clause](licenses/pywebview-LICENSE.txt) | https://github.com/r0x0r/pywebview |
| domJSON, inside pywebview | 0.1.2 | [MIT](licenses/pywebview-js-libraries.txt) | https://github.com/azaslavsky/domJSON |
| Native Promise Only, inside pywebview | 0.8.1 | [MIT](licenses/pywebview-js-libraries.txt) | https://github.com/getify/native-promise-only |
| symbol-es6, inside pywebview | - | [MIT](licenses/pywebview-js-libraries.txt) | https://github.com/rousan/symbol-es6 |
| Microsoft WebView2 SDK (Microsoft.Web.WebView2.Core.dll, .WinForms.dll, WebView2Loader.dll), inside pywebview | 1.0.3856.49 | [BSD-style Microsoft licence](licenses/WebView2-SDK-LICENSE.txt) | https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.3856.49 |
| pythonnet (Python.Runtime.dll) | 3.2.1 | [MIT](licenses/pythonnet-LICENSE.txt) | https://github.com/pythonnet/pythonnet |
| clr_loader (ClrLoader.dll) | 0.3.1 | [MIT](licenses/clr_loader-LICENSE.txt) | https://github.com/pythonnet/clr-loader |
| cffi | 2.1.1 | [MIT-0](licenses/cffi-LICENSE.txt) | https://github.com/python-cffi/cffi |
| pycparser | 3.11 | [BSD-3-Clause](licenses/pycparser-LICENSE.txt) | https://github.com/eliben/pycparser |
| bottle | 0.13.4 | [MIT](licenses/bottle-LICENSE.txt) | https://github.com/bottlepy/bottle |
| proxy_tools | 0.1.0 | [BSD](licenses/proxy_tools-LICENSE.txt) (its PyPI entry says MIT; the text here is the repo's LICENSE.txt) | https://github.com/jtushman/proxy_tools |
| typing_extensions | 4.16.0 | [PSF-2.0](licenses/typing_extensions-LICENSE.txt) | https://github.com/python/typing_extensions |
| pystray | 0.19.5 | [LGPL-3.0-or-later](licenses/pystray-LGPL-3.0.txt) (see below) | https://github.com/moses-palmer/pystray |
| six | 1.17.0 | [MIT](licenses/six-LICENSE.txt) | https://github.com/benjaminp/six |
| windows-capture (windows_capture.pyd only: the in-game menu's live backdrop) | 2.0.1 | [MIT](licenses/windows-capture-LICENSE.txt) | https://github.com/NiiightmareXD/windows-capture |
| Pillow | 12.3.0 | [MIT-CMU](licenses/Pillow-LICENSE.txt) | https://github.com/python-pillow/Pillow |
| Libraries inside Pillow: brotli 1.2.0, FreeType 2.14.3, HarfBuzz 14.2.1, lcms2 2.19.1, libavif 1.4.2, libjpeg-turbo 3.1.4.1, libpng 1.6.58, libwebp 1.6.0, OpenJPEG 2.5.4, libtiff 4.7.1, xz 5.8.3, zlib-ng 2.3.3 | as listed | [their own licences, all in Pillow's LICENSE](licenses/Pillow-LICENSE.txt) | https://github.com/python-pillow/Pillow |

## What the Android app contains

The Android app (`UltraFrontEnd-android.apk`, built from `android/`) runs the same page (`app/`) in Android's own WebView. Besides the project's own code it contains:

| Component | Licence | Source |
|---|---|---|
| AndroidX Core (androidx.core:core-ktx 1.13.1) and the AndroidX and Kotlin libraries it brings with it | [Apache-2.0](licenses/AndroidX-Apache-2.0.txt) | https://developer.android.com/jetpack/androidx |

## Required credits

- Microsoft WebView2 SDK: Copyright (C) Microsoft Corporation. All rights reserved.
- Portions of this software are copyright © 2026 The FreeType Project (https://freetype.org). All rights reserved.
- This software is based in part on the work of the Independent JPEG Group.
- "The Graphics Interchange Format(c) is the Copyright property of CompuServe Incorporated. GIF(sm) is a Service Mark property of CompuServe Incorporated."

## pystray (LGPL)

The exe uses pystray 0.19.5, Copyright (C) 2016-2022 Moses Palmér, for its tray icon. pystray is free software under the GNU Lesser General Public License, version 3 or (at your option) any later version. The licence texts are in [licenses/pystray-LGPL-3.0.txt](licenses/pystray-LGPL-3.0.txt) and [licenses/pystray-GPL-3.0.txt](licenses/pystray-GPL-3.0.txt).

pystray's source code, exactly as bundled, is in [licenses/pystray-source](licenses/pystray-source). It is also at https://github.com/moses-palmer/pystray and https://pypi.org/project/pystray/0.19.5/. To use a changed pystray, install it and rebuild the exe from this repository with `Game Frontend.spec` (see the README).

## Logos

The platform logos in `app/assets/platforms` come from Simple Icons (CC0 1.0) and Wikimedia Commons (public domain).

The logos of the older systems, made plain white and trimmed to the artwork (the Commons files are text logos, public domain as too simple for copyright; they stay trademarks of their owners):

| File | Mark | Source | Licence |
|---|---|---|---|
| atari.svg | Atari (Atari 8-bit) | [Simple Icons](https://cdn.jsdelivr.net/npm/simple-icons@16.36.0/icons/atari.svg) | CC0 1.0 |
| commodore.svg | Commodore (C64, VIC-20) | [Simple Icons](https://cdn.jsdelivr.net/npm/simple-icons@16.36.0/icons/commodore.svg) | CC0 1.0 |
| gogdotcom.svg | GOG | [Simple Icons](https://cdn.jsdelivr.net/npm/simple-icons@16.36.0/icons/gogdotcom.svg) | CC0 1.0 |
| nec.svg | NEC (PC Engine CD) | [Simple Icons](https://cdn.jsdelivr.net/npm/simple-icons@16.36.0/icons/nec.svg) | CC0 1.0 |
| nintendo64dd.svg | 64DD | [Commons: 64DD logo (1999).svg](https://commons.wikimedia.org/wiki/File:64DD_logo_%281999%29.svg) | Public domain |
| fds.svg | Family Computer Disk System | [Commons: Family Computer Disk System logo.svg](https://commons.wikimedia.org/wiki/File:Family_Computer_Disk_System_logo.svg) | Public domain |
| virtualboy.svg | Virtual Boy | [Commons: Virtualboy logo.svg](https://commons.wikimedia.org/wiki/File:Virtualboy_logo.svg) | Public domain |
| gameandwatch.svg | Game & Watch | [Commons: Game and watch logo.svg](https://commons.wikimedia.org/wiki/File:Game_and_watch_logo.svg) | Public domain |
| sega32x.svg | 32X | [Commons: Sega 32X logo.svg](https://commons.wikimedia.org/wiki/File:Sega_32X_logo.svg) | Public domain |
| mastersystem.svg | Master System | [Commons: Master System Logo.svg](https://commons.wikimedia.org/wiki/File:Master_System_Logo.svg) | Public domain |
| gamegear.svg | Game Gear | [Commons: Game gear us-jp logo.svg](https://commons.wikimedia.org/wiki/File:Game_gear_us-jp_logo.svg) | Public domain |
| sg1000.svg | SG-1000 | [Commons: SG-1000 Logo.svg](https://commons.wikimedia.org/wiki/File:SG-1000_Logo.svg) | Public domain |
| atomiswave.svg | Atomiswave | [Commons: Atomiswave logo.svg](https://commons.wikimedia.org/wiki/File:Atomiswave_logo.svg) | Public domain |
| pcengine.svg | PC Engine | [Commons: PC engine logo red.svg](https://commons.wikimedia.org/wiki/File:PC_engine_logo_red.svg) | Public domain |
| pcfx.svg | PC-FX | [Commons: PC-FX textlogo.svg](https://commons.wikimedia.org/wiki/File:PC-FX_textlogo.svg) | Public domain |
| neogeopocket.svg | Neo Geo Pocket | [Commons: Neo Geo Pocket logo.svg](https://commons.wikimedia.org/wiki/File:Neo_Geo_Pocket_logo.svg) | CC0 1.0 |
| atarijaguar.svg | Atari Jaguar | [Commons: Atari Jaguar logo.svg](https://commons.wikimedia.org/wiki/File:Atari_Jaguar_logo.svg) | Public domain |
| atarilynx.svg | Atari Lynx | [Commons: Atari Lynx logo.svg](https://commons.wikimedia.org/wiki/File:Atari_Lynx_logo.svg) | Public domain |
| atari7800.svg | Atari 7800 | [Commons: Atari 7800 logo-01.svg](https://commons.wikimedia.org/wiki/File:Atari_7800_logo-01.svg) | Public domain |
| atari5200.svg | Atari 5200 | [Commons: Atari 5200 logo.svg](https://commons.wikimedia.org/wiki/File:Atari_5200_logo.svg) | Public domain |
| atari2600.svg | Atari 2600 | [Commons: Atari 2600 logo.svg](https://commons.wikimedia.org/wiki/File:Atari_2600_logo.svg) | Public domain |
| atarist.svg | Atari ST | [Commons: Atari ST logo-01.svg](https://commons.wikimedia.org/wiki/File:Atari_ST_logo-01.svg) | Public domain |
| wonderswan.svg | WonderSwan | [Commons: WonderSwan logo.svg](https://commons.wikimedia.org/wiki/File:WonderSwan_logo.svg) | Public domain |
| threedo.svg | 3DO (the lettering only) | [Commons: 3DO Logo.svg](https://commons.wikimedia.org/wiki/File:3DO_Logo.svg) | Public domain |
| cdi.svg | CD-i | [Commons: CD-i logo 2.svg](https://commons.wikimedia.org/wiki/File:CD-i_logo_2.svg) | Public domain |
| intellivision.svg | Intellivision | [Commons: Intellivision-logo.svg](https://commons.wikimedia.org/wiki/File:Intellivision-logo.svg) | Public domain |
| ngage.svg | N-Gage | [Commons: N-Gage console logo.svg](https://commons.wikimedia.org/wiki/File:N-Gage_console_logo.svg) | Public domain |
| amiga.svg | Amiga | [Commons: Amiga Logo 1985.svg](https://commons.wikimedia.org/wiki/File:Amiga_Logo_1985.svg) | Public domain |
| zxspectrum.svg | Sinclair ZX Spectrum | [Commons: Sinclair ZX Spectrum-01.svg](https://commons.wikimedia.org/wiki/File:Sinclair_ZX_Spectrum-01.svg) | Public domain |
| msx.svg | MSX | [Commons: MSX-Logo.svg](https://commons.wikimedia.org/wiki/File:MSX-Logo.svg) | Public domain |
| apple2.svg | Apple II | [Commons: Apple2Logo.svg](https://commons.wikimedia.org/wiki/File:Apple2Logo.svg) | Public domain |

## Controller pictures

The controller pictures in `app/assets` (`pad-xbox.png`, `pad-ps5.png`, `pad-ps4.png`, `pad-ps3.png`, `pad-sw1.png`, `pad-sw2.png`) are original pictures made for this project with an image generator. They have no logos. `controller-steam.png` is Valve's product image of the Steam Controller; the Steam Controller and the Steam logo belong to Valve Corporation.

## Data the app fetches

None of this is part of the project or covered by its MIT licence, and none of it is bundled in the repo or the exe.

- Game descriptions can come from Wikipedia. That text is by Wikipedia's contributors under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) and may be shortened.
- Genres, developers and release years can come from Wikidata, which is [CC0](https://creativecommons.org/publicdomain/zero/1.0/).
- Covers, logos, backgrounds, trailers and news from Steam, SteamGridDB and libretro-thumbnails (and the Epic Games, PlayStation Store and RetroAchievements services) belong to their owners. The app fetches them at run time for your own library; they are never shipped with it.
