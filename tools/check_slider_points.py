#!/usr/bin/env python3
import sys
sys.path.insert(0, r"c:\Users\erick\osu-Py")

from core.beatmap_loader import BeatmapLoader

b = BeatmapLoader()
notes = b.parse_hitobjects(r"c:\Users\erick\osu-Py\songs\838642 USAO - Dynamite (Camellia's MACHO TNT REMIX)\USAO - Dynamite (Camellia_s MACHO TNT REMIX) (Foxy Grandpa) [DARKNESS].osu")

sliders = [n for n in notes if n['type']=='slider']
print(f"Total sliders: {len(sliders)}")

if len(sliders) > 0:
    # Check around 9-10 seconds
    for s in sliders:
        if 9000 < s['time'] < 11000:
            print(f"\nSlider at {s['time']}ms:")
            print(f"  Start: ({s['x']}, {s['y']})")
            if s['curve_points']:
                print(f"  First curve point: ({s['curve_points'][0]['x']}, {s['curve_points'][0]['y']})")
                print(f"  Number of curve points: {len(s['curve_points'])}")
            break
