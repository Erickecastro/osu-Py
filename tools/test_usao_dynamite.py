import time
import os
import sys

# garante que o diretório do projeto esteja no path para importações locais
sys.path.insert(0, os.getcwd())

from core.beatmap_loader import BeatmapLoader

loader = BeatmapLoader()
root = os.path.join(os.getcwd(), 'songs')

candidates = []
for dirpath, dirnames, filenames in os.walk(root):
    for f in filenames:
        if f.lower().endswith('.osu') and ('dynamite' in f.lower() or 'usao' in f.lower()):
            candidates.append(os.path.join(dirpath, f))

if not candidates:
    print('No matching .osu files found for USAO Dynamite.')
    # if nothing matched, fallback to any file containing 'dynamite' in folder
    for d in os.listdir(root):
        if 'dynamite' in d.lower() or 'usao' in d.lower():
            path = os.path.join(root, d)
            for file in os.listdir(path):
                if file.endswith('.osu'):
                    candidates.append(os.path.join(path, file))

if not candidates:
    print('Still no candidates. Exiting.')
    raise SystemExit(1)

for osu_file in candidates:
    print('\n== Testing:', osu_file)
    t0 = time.time()
    notes = loader.parse_hitobjects(osu_file)
    t1 = time.time()
    sliders = [n for n in notes if n['type'] == 'slider']
    print('Loaded notes:', len(notes), ' sliders:', len(sliders), ' load_time: %.3fs' % (t1 - t0))

    max_ctrl = 0
    max_generated = 0
    problematic = 0
    total_generated = 0
    for idx, s in enumerate(sliders[:200]):
        # find original control points by parsing the osu file lines (quick hack)
        # loader already used generate_slider_path when parsing, so we can derive stats from stored curve_points
        gen = s.get('curve_points', [])
        cp = gen  # we no longer have original control count here; approximate
        total_generated += len(gen)
        if len(gen) > max_generated:
            max_generated = len(gen)
        # check for extreme values
        for p in gen:
            x = p.get('x', 0)
            y = p.get('y', 0)
            if abs(x) > 10000 or abs(y) > 10000:
                problematic += 1
        if idx < 5:
            print('  slider', idx, 'type', s.get('curve_type'), 'generated pts', len(gen))
            print('    sample pts:', gen[:5], '...', gen[-3:])

    avg = total_generated / (len(sliders) or 1)
    print('max_generated_pts:', max_generated, 'avg_generated_pts:', '%.2f' % avg, 'problematic_points:', problematic)

print('\nDone.')
