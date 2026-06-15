# OSU-Py

osu-Py is a fan-made rhythm game project inspired by osu!, built with Python and pygame-ce. Its goal is to load beatmaps in the `.osu` format, play the corresponding music, and render a playable gameplay experience featuring hit circles, sliders, approach circles, combo tracking, score, accuracy, a custom cursor, and song/difficulty selection.

The project is still under development, but the core gameplay is already functional. The codebase is being gradually reorganized to improve maintainability, enhance performance, and better separate responsibilities between loaders, scenes, renderers, and gameplay systems.

## Current Features

* Loads beatmaps from the `songs/` directory.
* Parses metadata, difficulty settings, timing points, hit circles, sliders, and combo colors.
* Gameplay support for hit circles, sliders, reverse markers, slider balls, fade-in/fade-out animations, miss indicators, score, combo, and accuracy.
* Renders cursor, notes, sliders, spinner, HUD, and menus using the default skin located in `assets/skins/default/`.
* Song and difficulty selection menus powered by `pygame_gui`.
* Fullscreen support with seamless switching between fullscreen and windowed mode using `F11`.

## Requirements

* Python 3.12 recommended.
* Windows was the primary development and testing environment.
* Dependencies listed in `requirements.txt`.

Install dependencies with:

```bash
pip install -r requirements.txt
```

On some Windows environments, you may need to use:

```bash
py -3.12 -m pip install -r requirements.txt
```

## Running the Game

```bash
py -3.12 main.py
```

Or, if `python` points to the correct version:

```bash
python main.py
```

## Beatmaps

Place your beatmaps inside the `songs/` directory. Each beatmap should preserve its original structure, including at least:

* A `.osu` file.
* The audio file referenced by the `.osu` file.
* The main music file (`.wav` or `.mp3`).
* Optional beatmap assets, when available.

The loader scans all subdirectories inside `songs/`, detects `.osu` files, and builds the list of available difficulties.

You can download beatmaps directly from the official osu! website:

https://osu.ppy.sh/beatmapsets

## Controls

* `Z` or `X`: hit objects.
* `Left Mouse Button` or `Right Mouse Button`: hit objects.
* `Esc`: exit gameplay or go back to the previous scene.
* `F3`: toggle the performance profiler.
* `F11`: toggle fullscreen mode.
* `Alt + F4`: quit the game.

## Performance and Profiling

When testing on low-end PCs, press `F3` to enable the built-in profiler. It displays FPS, average frame time, p95 latency, worst frames, and detailed timing information for events, updates, rendering, visualizer, hit objects, sliders, UI, display flipping, and frame pacing.

The same summary is periodically printed to the terminal.

You can also start the game with the profiler enabled:

```bash
$env:PYOSU_PROFILE="1"; py -3.12 main.py
```

To enable performance auditing by default:

```bash
$env:PYOSU_DEBUG_PERFORMANCE="1"; py -3.12 main.py
```

The game targets `240 FPS` by default to reduce stuttering on lower-end hardware. To test a different frame limit:

```bash
$env:PYOSU_TARGET_FPS="360"; py -3.12 main.py
```

To test the low-latency frame pacing mode (with increased CPU usage):

```bash
$env:PYOSU_BUSY_FRAME_PACER="1"; py -3.12 main.py
```

## Skins

Default assets are located in:

```text
assets/skins/default/
```

To test a different skin while keeping the same asset filenames:

```bash
$env:PYOSU_SKIN_DIR="assets/skins/my-skin"; py -3.12 main.py
```

## Project Structure

* `main.py` – Application entry point.
* `core/` – Main loop, audio system, beatmap loader, scene manager, and gameplay calculations.
* `scenes/` – Menus, song/difficulty selection, and gameplay scenes.
* `rendering/` – Rendering systems for primitives, cursor, and sliders.
* `assets/skins/default/` – Default skin containing game images and sounds.
* `songs/` – Beatmaps used for testing.
* `ui/` – Reserved space for future UI components and themes.

## Development Notes

The project prioritizes keeping the codebase simple, maintainable, and easy to evolve.

The gameplay scene still contains a significant amount of logic, so one of the next major goals is to further split the architecture into smaller, dedicated components, especially for:

* HUD management
* Object lifecycle handling
* Hit judgment logic
* Specialized note rendering

If you encounter the warning:

```text
libpng warning: iCCP: known incorrect sRGB profile
```

it usually indicates an invalid color profile embedded in a PNG file loaded by pygame. In most cases, this does not affect gameplay.

## Disclaimer

* This project is entirely fan-made, created for educational and non-commercial purposes.
* It is not affiliated with, endorsed by, or associated with the official osu! game, its developers, or its publishers in any way.
