# Performance / ModernGL TODO

This checklist tracks the CPU, input-latency, and renderer work needed to move the project toward osu!lazer-like smoothness while preserving gameplay behavior.

## Transition and Cursor

- [x] Suppress cursor trail during scene factory transitions.
- [x] Remove manual display flips from blocking scene loads.
- [x] Clear gameplay overlay fully for the first frames after a scene transition.
- [ ] Manually verify menu -> song select -> gameplay transitions have no frozen trail or Ready artifacts.

## CPU and Gameplay Preprocessing

- [x] Precompute initial slider geometry before active gameplay.
- [x] Queue critical slider surfaces before music start.
- [x] Queue critical slider reveal surfaces during the Ready/loading window.
- [x] Increase critical slider reveal warmup budget before music start.
- [x] Keep heavy cache warmup out of active/near-visible gameplay frames.
- [x] Keep background warmup out of active gameplay frames.
- [x] Warm only the active gameplay background size during scene startup.
- [ ] Remove remaining render-time geometry fallbacks after profiler confirms all slider caches are ready.
- [x] Expose render-time slider geometry fallback in profiler output.
- [x] Expose render-time slider surface fallback in profiler output.
- [x] Add per-frame counters for missed slider cache and render-time surface creation.
- [x] Prewarm spinner approach/rotation textures before active spinner frames.
- [x] Smooth spinner approach-circle scale buckets without reintroducing render-time scale spikes.
- [x] Make spinner approach-circle start larger and shrink immediately from spawn.
- [ ] Expand object pooling for short-lived gameplay effects.

## Gameplay Visual Fidelity

- [x] Parse and preserve `.osu` file format version for stacking compatibility.
- [x] Replace simplified object stacking with osu!lazer-style stack heights.
- [x] Support slider-end negative stack offsets for overlapping objects.
- [x] Enlarge approach-circle spawn radius while preserving hit-time contact.
- [x] Add lightweight score count-up and combo pop animations.
- [ ] Visually compare stacked notes and approach-circle size against osu!lazer.

## Render Pipeline

- [x] Add a backend abstraction and render command batch.
- [x] Reuse render command batches per backend to avoid per-frame batch allocation.
- [x] Keep Pygame blits authoritative while ModernGL parity is incomplete.
- [ ] Convert HUD/text drawing to persistent cached surfaces everywhere.
- [x] Add backend surface-token registry to prepare atlas/sprite batching diagnostics.
- [x] Cull fully offscreen batched blits before they reach the active renderer.
- [x] Cull fully offscreen direct backend blits and expose the count in profiler metrics.
- [x] Add CPU-side sprite atlas generation for cached HUD sprites.
- [x] Expose sprite atlas page/sprite counts in profiler metrics.
- [x] Expose atlas command/group counts as batching-readiness diagnostics.
- [x] Cache combo pop scaled HUD surfaces instead of scaling every pop frame.
- [ ] Extend sprite atlas registration to skin assets and followpoint/cursor sprites.
- [ ] Batch sprite commands by texture/atlas.
- [ ] Move cursor, HUD, followpoints, and hitobject sprites to a GPU sprite path.
- [ ] Move cached slider path textures to GPU-backed draw commands.

## ModernGL Rollout

- [x] Try ModernGL by default when available.
- [x] Fall back silently to Pygame when ModernGL is unavailable or unsupported.
- [x] Support `PYOSU_DISABLE_MODERNGL=1` for diagnostics.
- [x] Add profiler/debug metrics showing active render backend, GPU availability, display Hz, FPS target, and presentation mode.
- [x] Add profiler counters for render batch command count and backend name.
- [ ] Add visual parity screenshots comparing Pygame and ModernGL output.
- [ ] Enable real ModernGL sprite drawing only after destination/alpha parity is verified.

## Presentation / Refresh

- [x] Prefer desktop borderless fullscreen by default to avoid hidden 60 Hz exclusive-mode switches.
- [ ] Add in-game video setting for borderless/exclusive/windowed presentation.
- [ ] Validate detected refresh rate on 60 Hz, 80 Hz, 144 Hz, and high-refresh monitors.

## Latency and Frame-Time Validation

- [x] Track p50/p95/p99 frame time per scene.
- [x] Track frame pacer interval so refresh/pacing issues are visible in profiler output.
- [x] Track input-to-hit judgment latency in gameplay.
- [ ] Validate high polling-rate mouse behavior without event queue buildup.
- [ ] Validate tablet absolute input without sensitivity or smoothing interference.
- [ ] Add a repeatable stress beatmap/profile scenario for complex sliders and dense streams.
