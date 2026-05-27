#!/usr/bin/env python3
"""Debug tool to export slider curve points for visualization."""

import sys
import json
import csv
import math
sys.path.insert(0, r"c:\Users\erick\osu-Py")

try:
    from core.beatmap_loader import BeatmapLoader

    # Load beatmap
    loader = BeatmapLoader()
    beatmap_file = r"c:\Users\erick\osu-Py\songs\838642 USAO - Dynamite (Camellia's MACHO TNT REMIX)\USAO - Dynamite (Camellia_s MACHO TNT REMIX) (Foxy Grandpa) [DARKNESS].osu"

    notes = loader.parse_hitobjects(beatmap_file)
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Filter sliders and export with debug info
sliders = [n for n in notes if n["type"] == "slider"]
print(f"Total sliders: {len(sliders)}")

# Export sliders around 9-10 seconds (when the problem appears)
problem_times = [9402, 9673, 9943]

for problem_time in problem_times:
    # Find sliders near this time
    for slider in sliders:
        time_diff = abs(slider["time"] - problem_time)
        if time_diff < 100:
            print(f"\n=== Slider at {slider['time']}ms (target: {problem_time}ms) ===")
            print(f"Type: {slider['curve_type']}")
            print(f"Start: ({slider['x']}, {slider['y']})")
            print(f"Slider distance: {slider['slider_distance']}")
            print(f"Generated points: {len(slider['curve_points'])}")
            
            # Export to CSV
            filename = f"slider_debug_{slider['time']}.csv"
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['index', 'x', 'y', 'distance_from_start'])
                
                # Calculate distance from start for each point
                total_dist = 0
                prev_point = None
                for i, pt in enumerate(slider['curve_points']):
                    if prev_point:
                        dx = pt['x'] - prev_point['x']
                        dy = pt['y'] - prev_point['y']
                        total_dist += math.hypot(dx, dy)
                    writer.writerow([i, pt['x'], pt['y'], f"{total_dist:.2f}"])
                    prev_point = pt
            
            print(f"Exported to {filename}")
            
            # Print first 20 points
            print("First 20 points:")
            for i in range(min(20, len(slider['curve_points']))):
                pt = slider['curve_points'][i]
                print(f"  {i}: ({pt['x']:.1f}, {pt['y']:.1f})")
