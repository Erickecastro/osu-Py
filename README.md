# osu-Py

osu-Py is a fan-made rhythm game inspired by osu!, written in Python with pygame-ce. Its goal is to load local beatmaps in the `.osu` format, play the referenced audio, and render a playable experience with hit circles, sliders, spinners, HUD, a custom cursor, song selection, and difficulty metadata parsing.

The project is experimental and educational. The core gameplay is already functional, but the project does not aim for full parity with official osu!.

## Current Features

- Automatic beatmap loading from `songs/`.
- Parser support for the main `.osu` sections: `General`, `Metadata`, `Difficulty`, `TimingPoints`, `Colours`, `Events`, and `HitObjects`.
- Gameplay support for hit circles, sliders, reverse arrows, slider ball/follow circle, and spinners.
- Hit judgment using `300`, `100`, `50`, and miss windows.
- Score, combo, accuracy, health bar, hit error bar, and hit/miss visual effects.
- Custom cursor with relative/raw mouse support during gameplay.
- Animated main menu with background music, circular visualizer, track switching, and mouse sensitivity settings.
- Song selection screen with search, sorting, beatmap-set grouping, audio preview, and information panels.
- Background and asset loading from beatmap folders.
- Basic skin system based on files in `assets/skins/default/`.
- Built-in profiler for FPS, frame time, and subsystem timing investigation.
- Fullscreen/windowed switching with `F11`.

## Requirements

- Python 3.12 recommended.
- Windows is the main development and testing environment.
- Dependencies listed in `requirements.txt`:
  - `pygame-ce`
  - `pygame_gui`
  - `numpy`

Install dependencies:

```bash
pip install -r requirements.txt
```

If you use the Windows Python launcher:

```bash
py -3.12 -m pip install -r requirements.txt
```

## Running

```bash
py -3.12 main.py
```

or:

```bash
python main.py
```

## Controls

### Global

- `F11`: toggle fullscreen/windowed mode.
- `F3`: toggle the profiler overlay.
- `Alt + F4`: close the game.

### Main Menu

- Click the logo: open the menu.
- `Left`/`Right` or `A`/`D`: change menu music.
- `Space`: pause/resume menu music.
- `Esc`: close the menu or settings panel.
- Mouse wheel/drag in the settings panel: adjust mouse sensitivity.

### Song Selection

- `Up`/`Down` or mouse wheel: navigate.
- Click a group: expand/collapse difficulties.
- Click the selected difficulty or press `Enter`: start gameplay.
- `Ctrl + F` or direct typing: enable search.
- `Backspace`: remove search characters.
- `Tab`: cycle sorting mode.
- `Esc`: return to the main menu.

### Gameplay

- `Z`/`X`: hit objects.
- Left/right mouse button: hit objects.
- `Esc`: return to the previous scene.

## Beatmaps

Beatmaps should be placed in `songs/`, preserving the original osu! extracted folder structure.

Expected structure:

```text
songs/
  Beatmap name/
    file.osu
    audio.mp3
    background.jpg
    optional hitsounds
    optional storyboard/assets
```

The loader scans subdirectories in `songs/`, detects `.osu` files, loads available difficulties, and sorts beatmaps by display name. The preferred audio file is the `AudioFilename` declared in the `.osu`; when needed, the project attempts to find a compatible music file in the same folder.

Beatmaps can be downloaded from:

https://osu.ppy.sh/beatmapsets

## Skins and Assets

The default skin is located at:

```text
assets/skins/default/
```

The project looks for assets in the active skin first, then falls back to legacy paths under `assets/`. To test another skin with the same asset filenames:

```powershell
$env:PYOSU_SKIN_DIR="assets/skins/my-skin"
py -3.12 main.py
```

Important assets include the cursor, hit circles, approach circle, combo numbers, reverse arrow, spinner, health bar, hit sounds, and menu images.

## Settings and Local Data

- Mouse sensitivity: saved to `%APPDATA%/PyOsu/settings.json` on Windows.
- Local ranking: the song selection screen reads `scores/local_scores.json` when it exists. Saving new scores is still in progress.
- Large beatmap and asset files remain local under `songs/` and `assets/`.

## Environment Variables

```powershell
$env:PYOSU_SKIN_DIR="assets/skins/default"
$env:PYOSU_PROFILE="1"
$env:PYOSU_DEBUG_PERFORMANCE="1"
$env:PYOSU_TARGET_FPS="1000"
$env:PYOSU_BUSY_FRAME_PACER="1"
py -3.12 main.py
```

- `PYOSU_SKIN_DIR`: sets the active skin directory.
- `PYOSU_PROFILE=1`: starts with the profiler overlay enabled.
- `PYOSU_DEBUG_PERFORMANCE=1`: enables performance instrumentation by default.
- `PYOSU_TARGET_FPS`: sets the frame limit. The current code default is `1000`.
- `PYOSU_BUSY_FRAME_PACER=1`: uses `tick_busy_loop`, reducing frame-time variance at the cost of higher CPU usage.

## Architecture

```text
main.py                  Application entry point
core/
  game.py                Main loop, window, global events, cursor, and scenes
  scene_manager.py       Scene stack and transitions
  beatmap_loader.py      Beatmap discovery and loading
  osu_sections.py        .osu section parser
  osu_hitobjects.py      Hit object parser
  slider_paths.py        Slider path geometry generation
  beatmap_timing.py      Timing points and slider durations
  gameplay*.py           Accuracy, state, and gameplay input helpers
  audio.py               Music lookup/preload/start helpers
  performance.py         Performance and low-latency flags
  profiler.py            Per-frame metrics and overlay
  settings.py            Local settings persistence
scenes/
  main_menu_scene.py     Custom main menu
  song_select_scene.py   Beatmap selection, search, sorting, and preview
  gameplay_scene.py      Gameplay scene and object lifecycle
  base_scene.py          Common scene interface
rendering/
  cursor.py              Custom cursor
  hud.py                 Score, combo, accuracy, health, and hit error bar
  sliders.py             Slider rendering/cache
  spinner.py             Spinner rendering
  effects.py             Effects and combo numbers
  primitives.py          Drawing helpers
assets/                  Game skins and assets
songs/                   Local beatmaps
```

## Game Pipeline

1. `main.py` creates `Game`.
2. `Game` initializes pygame, audio, window, profiler, settings, and `SceneManager`.
3. `BeatmapLoader` scans `songs/` and builds the beatmap/difficulty list.
4. `MainMenuScene` starts the menu and menu playlist.
5. `SongSelectScene` converts loaded beatmaps into navigable items.
6. `GameplayScene` prepares playfield scaling, notes, audio, slider caches, and renderers.
7. During the loop, global events are handled by `Game`; scene-specific events are forwarded to the current scene.
8. The current scene updates state, renders, and `Game` draws the profiler/cursor when applicable.

## Performance

The project uses several strategies to reduce stutter:

- frame `dt` clamping;
- low mixer buffer;
- isolated music preload/start logic in `core/audio.py`;
- surface caching for circles, sliders, backgrounds, HUD, and text;
- incremental precaching for heavy slider and surface work;
- optional busy-loop frame pacing;
- per-subsystem profiler.

Useful commands:

```powershell
$env:PYOSU_PROFILE="1"
py -3.12 main.py
```

```powershell
$env:PYOSU_TARGET_FPS="360"
py -3.12 main.py
```

## Known Limitations

- `.osu` compatibility currently covers only what the gameplay needs.
- `.osb` storyboards may exist in beatmap folders, but there is no complete storyboard system yet.
- Local ranking is read by the UI, but saving new scores is not finalized.
- The project does not implement every official osu! mode, rule, mod, or online system.
- Some skin/beatmap PNGs may emit `libpng warning: iCCP: known incorrect sRGB profile`; this usually does not affect gameplay.

## License and Disclaimer

This project is fan-made, educational, and non-commercial. It is not affiliated with, endorsed by, or associated with the official osu! game, its developers, or its publishers.
