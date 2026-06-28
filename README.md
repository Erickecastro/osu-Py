# osu-Py

osu-Py is a fan-made rhythm game inspired by osu!, written in Python with pygame-ce. Its goal is to load local osu! beatmaps, play the referenced audio, and render a playable experience with hit circles, sliders, spinners, HUD, a custom cursor, song selection, local scores, and difficulty metadata parsing.

The project is experimental and educational. The core gameplay is already functional, but the project does not aim for full parity with official osu!.

## Current Features

- Automatic beatmap loading from `songs/`.
- `.osz` import from drag-and-drop, the `imports/` folder, or files placed next to the executable.
- Duplicate import protection using beatmap set IDs and `.osu` file hashes.
- Parser support for the main `.osu` sections: `General`, `Metadata`, `Difficulty`, `TimingPoints`, `Colours`, `Events`, and `HitObjects`.
- Gameplay support for hit circles, sliders, slider ticks/scorepoints, reverse arrows, slider ball/follow circle, and spinners.
- Hit judgment using `300`, `100`, `50`, and miss windows.
- Score, combo, accuracy, health bar, hit error bar, pause/lose/result screens, and hit/miss visual effects.
- Custom cursor with relative/raw mouse support, tablet absolute-input mode, configurable hit keys, and optional mouse-button blocking during gameplay.
- Animated main menu with background music, circular FFT/BPM visualizer, track switching, settings, and smooth exit fade.
- Song selection screen with search, sorting, beatmap-set grouping, audio preview, information panels, local ranking, result viewing, score deletion, and beatmap deletion.
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

The `.venv` folder is for local development only. It is not bundled into the executable.

## Running (Development)

```bash
python main.py
```

or:

```bash
py -3.12 main.py
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
- Settings panel: mouse sensitivity, hit keys, raw mouse input, tablet absolute input, gameplay dim, and mouse hit-button blocking.

### Song Selection

- `Up`/`Down` or mouse wheel: navigate.
- Click a group: expand difficulties and select the easiest difficulty first.
- Click a selected beatmap/difficulty again or press `Enter`: start gameplay.
- Right-click a beatmap card: request permanent deletion with confirmation.
- `Ctrl + F` or direct typing: enable search.
- `Backspace`: remove search characters.
- `Tab`: cycle sorting mode.
- `Esc`: clear search first; when search is empty, return to the main menu.
- Left-click a local score: view its result screen.
- Right-click a local score: request score deletion with confirmation.

### Gameplay

- `Z`/`X`: hit objects.
- Left/right mouse button: hit objects.
- `Esc`: return to the previous scene.

## Beatmaps

During development, place extracted beatmaps in the project `songs/` folder. For packaged builds, place beatmaps in the user data `songs/` folder or import `.osz` files through the game.

The loader searches, in order:

1. `PYOSU_SONGS_DIR` when set.
2. `songs/` beside the executable.
3. `songs/` in the current working directory.
4. `../songs/` when the executable lives in `dist/`.

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

- Settings are saved to `%LOCALAPPDATA%/PyOsu/settings.json` on Windows when available, falling back to `%APPDATA%/PyOsu/settings.json` or `settings.json` in development.
- Local scores are saved in `scores/local_scores.json` and shown on the song selection screen.
- Beatmaps are runtime/user data under `songs/` and new beatmap files are ignored by git.
- Imported `.osz` files are runtime/user data under `imports/` and new import files are ignored by git.
- Assets under `assets/` are source-controlled because they define the default skin and UI.

## Environment Variables

```powershell
$env:PYOSU_SKIN_DIR="assets/skins/default"
$env:PYOSU_PROFILE="1"
$env:PYOSU_DEBUG_PERFORMANCE="1"
$env:PYOSU_TARGET_FPS="1000"
$env:PYOSU_BUSY_FRAME_PACER="1"
py -3.12 main.py
```

- `PYOSU_SONGS_DIR`: sets the beatmaps directory explicitly.
- `PYOSU_SKIN_DIR`: sets the active skin directory.
- `PYOSU_PROFILE=1`: starts with the profiler overlay enabled.
- `PYOSU_DEBUG_PERFORMANCE=1`: enables performance instrumentation by default.
- `PYOSU_TARGET_FPS`: sets the frame limit. The current code default is `480`.
- `PYOSU_BUSY_FRAME_PACER=1`: uses `tick_busy_loop`, reducing frame-time variance at the cost of higher CPU usage.

## Building the Windows Executable

Install PyInstaller in your development environment (it is not required to run the game):

```bash
pip install pyinstaller
```

Generate a single-file executable with bundled assets:

```bash
pyinstaller --onefile --noconsole --add-data "assets;assets" main.py
```

On Linux or macOS, use `:` instead of `;` in `--add-data` (for example: `--add-data "assets:assets"`).

The command above embeds everything under `assets/` into the executable. At runtime, PyInstaller extracts those files to a temporary folder and the game resolves them through `resource_path()` in `core/utils.py`.

After the build finishes, the executable is written to `dist/main.exe`. Rename it if you prefer (for example, `PyOsu.exe`).

Place user beatmaps next to the executable or import them through the game. Do not bundle user beatmaps inside the `.exe`:

```text
PyOsu.exe
assets/          (embedded in the .exe)
songs/           (external user beatmaps)
imports/         (optional .osz drop folder)
scores/          (optional, created at runtime)
```

## Importing Beatmaps

The game supports `.osz` packages:

- Drag an `.osz` file into the game window.
- Put `.osz` files in `imports/` before starting the game.
- Put `.osz` files next to the executable in packaged builds.

Imported beatmaps are extracted into the runtime `songs/` folder. Successfully processed `.osz` files from `imports/` are moved to `imports/imported/`.

Duplicate protection checks official beatmap set IDs when available and falls back to `.osu` content hashes. This prevents importing the same beatmap more than once even when the `.osz` file name changes.

Real beatmap folders and imported `.osz` files are intentionally ignored by git. Keep only `songs/.gitkeep` and `imports/.gitkeep` in source control.

If a local clone already tracks beatmap folders, remove them from the git index before publishing while keeping the files on disk:

```bash
git rm --cached -r songs
git add songs/.gitkeep
```

## Architecture

```text
main.py                  Application entry point
core/
  game.py                Main loop, window, global events, cursor, and scenes
  utils.py               resource_path(), app/user data paths, and PyInstaller helpers
  assets.py              Asset lookup, caching, and startup preload
  scene_manager.py       Scene stack and transitions
  beatmap_loader.py      Beatmap discovery and loading
  osz_importer.py        .osz import, safe extraction, and duplicate detection
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
  song_select_scene.py   Beatmap selection, search, sorting, preview, local ranking, and deletion
  gameplay_scene.py      Gameplay scene and object lifecycle
  result_scene.py        Result summary, rank display, retry, and quit actions
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

- configurable frame pacing with `pygame.time.Clock()` and optional busy-loop pacing;
- frame `dt` clamping;
- low mixer buffer;
- startup preload of shared UI assets in `core/assets.py`;
- isolated music preload/start logic in `core/audio.py`;
- surface caching for circles, sliders, backgrounds, HUD, and text;
- incremental precaching for heavy slider and surface work;
- optional busy-loop frame pacing;
- per-subsystem profiler;
- gameplay timing driven by `pygame.time.get_ticks()` instead of frame count.

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

- `.osu` compatibility currently covers the gameplay systems implemented by the project.
- `.osb` storyboards may exist in beatmap folders, but there is no complete storyboard system yet.
- Online osu! services, login, multiplayer, and official score submission are not implemented.
- The project does not implement every official osu! mode, rule, mod, or online system.
- Some skin/beatmap PNGs may emit `libpng warning: iCCP: known incorrect sRGB profile`; this usually does not affect gameplay.

## License and Disclaimer

This project is fan-made, educational, and non-commercial. It is not affiliated with, endorsed by, or associated with the official osu! game, its developers, or its publishers.
