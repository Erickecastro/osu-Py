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
- [ ] Remove remaining render-time geometry fallbacks after profiler confirms all slider caches are ready.
- [ ] Add profiler counters for missed slider cache and render-time surface creation.
- [ ] Expand object pooling for short-lived gameplay effects.

## Render Pipeline

- [x] Add a backend abstraction and render command batch.
- [x] Keep Pygame blits authoritative while ModernGL parity is incomplete.
- [ ] Convert HUD/text drawing to persistent cached surfaces everywhere.
- [ ] Add sprite atlas generation for skin assets and HUD sprites.
- [ ] Batch sprite commands by texture/atlas.
- [ ] Move cursor, HUD, followpoints, and hitobject sprites to a GPU sprite path.
- [ ] Move cached slider path textures to GPU-backed draw commands.

## ModernGL Rollout

- [x] Try ModernGL by default when available.
- [x] Fall back silently to Pygame when ModernGL is unavailable or unsupported.
- [x] Support `PYOSU_DISABLE_MODERNGL=1` for diagnostics.
- [ ] Add a settings/debug label showing active render backend.
- [ ] Add visual parity screenshots comparing Pygame and ModernGL output.
- [ ] Enable real ModernGL sprite drawing only after destination/alpha parity is verified.

## Latency and Frame-Time Validation

- [ ] Track p50/p95/p99 frame time per scene.
- [ ] Track input-to-hit judgment latency in gameplay.
- [ ] Validate high polling-rate mouse behavior without event queue buildup.
- [ ] Validate tablet absolute input without sensitivity or smoothing interference.
- [ ] Add a repeatable stress beatmap/profile scenario for complex sliders and dense streams.
