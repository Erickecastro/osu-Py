import sys, os, time
sys.path.insert(0, os.getcwd())
from core.beatmap_loader import BeatmapLoader
loader = BeatmapLoader()
file = os.path.join('songs','1124943 The Qemists - Stompbox (Spor Remix)','The Qemists - Stompbox (Spor Remix) (nhlx) [KERNEL PANIC].osu')
print('Testing', file)
t0=time.time()
notes = loader.parse_hitobjects(file)
t1=time.time()
sliders = [n for n in notes if n['type']=='slider']
print('loaded', len(notes), 'sliders', len(sliders), 'time', t1-t0)
max_gen=0
for i,s in enumerate(sliders[:20]):
    g=len(s.get('curve_points',[]))
    if g>max_gen: max_gen=g
    print('s',i,'type', s['curve_type'],'gen_pts', g)
print('max_gen_first20', max_gen)
# overall stats
max_all=0; avg=0
for s in sliders:
    l=len(s.get('curve_points',[]))
    avg += l
    if l>max_all: max_all = l
avg = avg/len(sliders) if sliders else 0
print('max_all', max_all, 'avg', avg)
