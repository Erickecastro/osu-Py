import os
from collections import defaultdict

root = 'songs'
summary = []
for folder in os.listdir(root):
    path = os.path.join(root, folder)
    if not os.path.isdir(path):
        continue
    for file in os.listdir(path):
        if not file.endswith('.osu'):
            continue
        osu_file = os.path.join(path, file)
        max_ctrl = 0
        total_sliders = 0
        with open(osu_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        hit_section = False
        for line in lines:
            line = line.strip()
            if line == '[HitObjects]':
                hit_section = True
                continue
            if not hit_section:
                continue
            if line == '':
                continue
            parts = line.split(',')
            if len(parts) < 5:
                continue
            try:
                obj_type = int(parts[3])
            except:
                continue
            if obj_type & 2:
                total_sliders += 1
                if len(parts) > 5:
                    curve_data = parts[5]
                    cp = curve_data.split('|')
                    # exclude first char (curve type)
                    count = max(0, len(cp) - 1)
                    if count > max_ctrl:
                        max_ctrl = count
        summary.append((osu_file, total_sliders, max_ctrl))

summary.sort(key=lambda x: x[2], reverse=True)
for s in summary[:20]:
    print(s[1], 'sliders | max_control_points =', s[2], '\t', s[0])
