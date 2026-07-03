# Performance / ModernGL TODO

This checklist tracks the CPU, input-latency, and renderer work needed to move the project toward osu!lazer-like smoothness while preserving gameplay behavior.

## Transition and Cursor

- [x] Suppress cursor trail during scene factory transitions.
- [x] Remove manual display flips from blocking scene loads.
- [x] Clear gameplay overlay fully for the first frames after a scene transition.
- [ ] Manually verify menu -> song select -> gameplay transitions have no frozen trail or Ready artifacts.

## CPU and Gameplay Preprocessing

- [x] Hold gameplay start longer when critical skin/surface/slider/followpoint caches are still warming.
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
- [x] Bound spinner approach/rotation cache so smooth buckets cannot exhaust memory.
- [x] Enforce spinner scaled/rotated sub-cache limits even when the global cache is under budget.
- [x] Trim transparent spinner-circle padding at load time so large spinner visuals do not require oversized source assets.
- [x] Expand object pooling for short-lived gameplay effects.
- [x] Prewarm first visible hitobject family by type before releasing the Ready screen.
- [x] Add a startup-cache profiler row that reports the missing warmup category, not only a ready/not-ready flag.
- [x] Add a render-time guard that never builds missing slider surfaces on an active gameplay frame.
- [x] Continue scheduling upcoming slider surface/reveal caches asynchronously during active gameplay.

## Gameplay Visual Fidelity

- [x] Let players reengage a sliderball/followcircle after missing the slider head.
- [x] Make gameplay HUD fade in almost immediately, and delay it until skip intro disappears when skip is visible.
- [x] Keep high-resolution music clock aligned after skip without double-counting the start offset.
- [x] Keep high-resolution music clock aligned after pause/resume without counting paused time.
- [x] Add a longer post-skip visual lead so the first object can fade in instead of popping in.
- [x] Gate the first hitobject fade so maps that start immediately do not pop the first object at high alpha.
- [x] Parse and preserve `.osu` file format version for stacking compatibility.
- [x] Replace simplified object stacking with osu!lazer-style stack heights.
- [x] Support slider-end negative stack offsets for overlapping objects.
- [x] Enlarge approach-circle spawn radius while preserving hit-time contact.
- [x] Add lightweight score count-up and combo pop animations.
- [x] Freeze gameplay object animations on fail while preserving visible objects and slow fall motion.
- [x] Isolate approach circles from the main gameplay overlay so translucent sprites do not tint each other.
- [x] Clean transparent RGB in scaled skin copies to avoid dark/bright PNG edge halos.
- [ ] Visually compare stacked notes and approach-circle size against osu!lazer.
- [x] Support slider reengage when the hit key was already held before entering the followcircle.
- [ ] Validate slider reengage behavior against osu!lazer on missed heads, late ticks, and repeat sliders.

## Render Pipeline

- [x] Add a backend abstraction and render command batch.
- [x] Reuse render command batches per backend to avoid per-frame batch allocation.
- [x] Keep Pygame blits authoritative while ModernGL parity is incomplete.
- [x] Convert HUD/text drawing to persistent cached surfaces everywhere.
- [x] Add backend surface-token registry to prepare atlas/sprite batching diagnostics.
- [x] Cull fully offscreen batched blits before they reach the active renderer.
- [x] Cull fully offscreen direct backend blits and expose the count in profiler metrics.
- [x] Add CPU-side sprite atlas generation for cached HUD sprites.
- [x] Expose sprite atlas page/sprite counts in profiler metrics.
- [x] Expose atlas command/group counts as batching-readiness diagnostics.
- [x] Expose atlas run and batchable-command counts for GPU batching readiness.
- [x] Add GPU texture-cache plumbing for static surfaces and versioned atlas pages.
- [x] Expose GPU sprite/upload/flush/fallback counters in profiler metrics.
- [x] Cache combo pop scaled HUD surfaces instead of scaling every pop frame.
- [x] Register score, accuracy, combo, health, and hit-error HUD sprites with atlas keys.
- [x] Extend sprite atlas registration to cursor sprites.
- [x] Extend sprite atlas registration to skin assets and followpoint sprites.
- [x] Register cached slider path surfaces with stable atlas keys.
- [x] Batch sprite commands by texture/atlas behind a diagnostic ModernGL sprite path.
- [x] Promote backend-routed HUD/cursor sprites to the GPU sprite path when ModernGL is active.
- [x] Avoid per-frame command-list copying in the ModernGL sprite flush path.
- [ ] Move overlay-bound followpoints and hitobject sprites to a GPU/FBO sprite path.
- [ ] Split gameplay overlay into explicit FBO-ready layers for slider paths, hitobjects, approach circles, followpoints, and indicators.
- [ ] Move cached slider path textures to GPU-backed draw commands.
- [x] Add a read-only frame graph showing background, hitobjects, sliders, followpoints, HUD, cursor, and debug costs separately.

## ModernGL Rollout

- [x] Try ModernGL by default when available.
- [x] Fall back silently to Pygame when ModernGL is unavailable or unsupported.
- [x] Support `PYOSU_DISABLE_MODERNGL=1` for diagnostics.
- [x] Add profiler/debug metrics showing active render backend, GPU availability, display Hz, FPS target, and presentation mode.
- [x] Add profiler counters for render batch command count and backend name.
- [ ] Add visual parity screenshots comparing Pygame and ModernGL output.
- [x] Enable real ModernGL sprite drawing behind `PYOSU_ENABLE_GPU_SPRITES=1` after destination/alpha parity scaffolding.
- [x] Implement the first real ModernGL sprite path for cached/atlas sprites behind a diagnostic flag.
- [x] Promote ModernGL sprite batching from diagnostic opt-in to default-on when the backend is available.
- [ ] Promote followpoints to ModernGL after overlay/FBO parity passes.
- [x] Add a backend smoke test that verifies GPU texture upload/reuse without enabling it in gameplay.

## Presentation / Refresh

- [x] Prefer desktop borderless fullscreen by default to avoid hidden 60 Hz exclusive-mode switches.
- [x] Keep windowed mode fixed-size with native minimize/close controls and no resizable maximize path.
- [x] Restore fullscreen presentation so F11 fills the active display.
- [ ] Add in-game video setting for borderless/exclusive/windowed presentation.
- [ ] Validate detected refresh rate on 60 Hz, 80 Hz, 144 Hz, and high-refresh monitors.

## Latency and Frame-Time Validation

- [x] Track p50/p95/p99 frame time per scene.
- [x] Track frame pacer interval so refresh/pacing issues are visible in profiler output.
- [x] Track input-to-hit judgment latency in gameplay.
- [ ] Validate high polling-rate mouse behavior without event queue buildup.
- [ ] Validate tablet absolute input without sensitivity or smoothing interference.
- [ ] Add a repeatable stress beatmap/profile scenario for complex sliders and dense streams.
- [ ] Add an automated startup-stutter scenario that asserts first-object frame time stays below target budget.
