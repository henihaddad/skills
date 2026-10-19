#!/usr/bin/env python3
"""Plan a face-following 9:16 crop for every clip of a plan, frame-exact, and verify it.

    python facetrack.py plan.json --source source1080.mp4 --work work/ [--verify] [--cameras 2]

Writes work/faces.json: {"<start_idx>-<end_idx>": [[first_frame, face_center_x], ...]} - one
entry per camera shot. render.py turns it into crop=...:x='if(lt(n,F1),X0,if(lt(n,F2),X1,...))'.

How it works and why (each of these fixed a visible glitch):
* Cuts are found by differencing consecutive frames of the SAME decode the renderer crops
  (same -ss/-t), so indices line up with the crop filter's frame counter n.
* That decode uses -fps_mode passthrough. Without it, the rawvideo muxer duplicates the first
  frame to keep constant frame rate, shifting every index by one -> the crop switches one frame
  after the camera cut and flashes the wrong side (mic/candles) for ~1-2 frames.
* Cuts right at a clip's first/last frames are kept: dropping "edge" cuts left the last
  ~100 ms of a clip on the wrong person.
* Each shot gets ONE crop position = median of face detections sampled inside the shot.
  Smoothing over time instead makes the crop lag behind cuts by up to ~0.8 s.
* Detections in the lower part of the frame are ignored (microphones, logos).
* A shot with no detection borrows the position of the most similar-looking shot.

--verify classifies every frame by camera angle (k-means on tiny thumbnails, k=--cameras)
and checks the crop side the real crop expression produces for each frame. It should report 0
mismatches. Works for the common fixed-camera podcast setup (one camera per person); with a
moving or wide camera, inspect a contact sheet of cut frames instead.
"""
import argparse, json, os, statistics, subprocess
import numpy as np, cv2
from common import load, save, ffmpeg_path

ap = argparse.ArgumentParser()
ap.add_argument('plan')
ap.add_argument('--source', required=True)
ap.add_argument('--work', default='work')
ap.add_argument('--verify', action='store_true')
ap.add_argument('--cameras', type=int, default=0, help='camera angles for --verify (0 = auto)')
ap.add_argument('--cut-threshold', type=float, default=20)
ap.add_argument('--prefer', choices=['closeup', 'left', 'right', 'largest', 'most'], default='closeup',
                help='which face to follow in wide shots with two people when nothing else decides it')
ap.add_argument('--angle-x', default='', help='force a crop per camera angle, e.g. "2=200,0=1100" (face-centre x in '
                'source pixels); angle numbers and previews are printed/saved by the angle pass')
a = ap.parse_args()
FF = ffmpeg_path()
S = load(os.path.join(a.work, 'transcript.json'))['sents']
P = load(a.plan)

def src_dims():
    r = subprocess.run([FF, '-hide_banner', '-i', a.source], capture_output=True, text=True).stderr
    import re
    m = re.search(r'Video:.*?(\d{3,5})x(\d{3,5})', r)
    return int(m[1]), int(m[2])
SW, SH = src_dims()
CW = int(round(SH * 9 / 16 / 2) * 2)          # crop width for 9:16 at full height

def window(it):
    if 'start' in it:
        return it['start'], it['end'] - it['start']
    i, j = it['start_idx'], it['end_idx']
    st = it.get('start_time') or max(S[i][0] - 0.12, (S[i - 1][1] + 0.02) if i > 0 else 0)
    en = it.get('end_time') or min(S[j][1] + 0.3, (S[j + 1][0] - 0.03) if j + 1 < len(S) else 1e9)
    return st, en - st

def decode(st, du, vf, w, h, pix='gray', ch=1):
    raw = subprocess.run([FF, '-v', 'error', '-ss', f'{st:.2f}', '-t', f'{du:.2f}', '-i', a.source, '-an',
                          '-fps_mode', 'passthrough', '-vf', vf, '-pix_fmt', pix, '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w * ch) if ch == 1 else np.frombuffer(raw, np.uint8).reshape(-1, h, w, ch)

cas = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
       ('haarcascade_frontalface_default.xml', 'haarcascade_frontalface_alt2.xml')]
pro = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')

def faces(bgr):                                   # bgr is 960x540
    g = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)); out = []
    for c in cas + [pro]:
        out += list(c.detectMultiScale(g, 1.08, 5, minSize=(70, 70)))
    out += [(960 - x - w, y, w, h) for x, y, w, h in pro.detectMultiScale(cv2.flip(g, 1), 1.08, 5, minSize=(70, 70))]
    return [((x + w / 2) * SW / 960, w) for x, y, w, h in out if y + h / 2 < 300]

def split_people(dets):
    """1-D clustering of face centres in a shot. Returns [(centre, n, mean_width), ...]; more than
    one cluster means a wide shot with several people (a single median would land between them)."""
    xs = sorted(dets)
    groups = [[xs[0]]]
    for d in xs[1:]:
        if d[0] - groups[-1][-1][0] > CW * 0.5:
            groups.append([d])
        else:
            groups[-1].append(d)
    return [(statistics.median(x for x, _ in g), len(g), sum(w for _, w in g) / len(g)) for g in groups]

def plan_clip(st, du, key):
    fr = decode(st, du, 'scale=960:540', 960, 540, 'bgr24', 3)
    g = fr[:, ::10, ::10].mean(axis=3)
    d = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))
    cuts = [i + 1 for i, v in enumerate(d) if v > a.cut_threshold]
    bounds = [0] + cuts + [len(fr)]; shots, wide, thumbs = [], [], []
    for s0, s1 in zip(bounds, bounds[1:]):
        idx = sorted(set(np.linspace(s0, s1 - 1, min(9, s1 - s0)).astype(int)))
        thumbs.append(np.round(np.mean([cv2.resize(fr[i], (32, 18), interpolation=cv2.INTER_AREA) for i in idx], axis=0) / 255, 3).ravel().tolist())
        dets = []
        for i in idx:
            fd = faces(fr[i])
            if fd:   # a gesturing hand or a logo is smaller than the real face(s) in the same frame
                big = max(w for _, w in fd); dets += [d for d in fd if d[1] >= big * 0.6]
        if not dets:
            shots.append([int(s0), None]); continue
        cl = [c for c in split_people(dets) if c[1] >= 2] or split_people(dets)
        if len(cl) == 1:
            shots.append([int(s0), cl[0][0]])
        else:
            shots.append([int(s0), cl]); wide.append(len(shots) - 1)
    # wide shots: choose one person
    singles = [s[1] for s in shots if isinstance(s[1], float)]
    for k in wide:
        cl = shots[k][1]
        if a.prefer == 'left':
            pick = min(cl, key=lambda c: c[0])
        elif a.prefer == 'right':
            pick = max(cl, key=lambda c: c[0])
        elif a.prefer == 'largest':
            pick = max(cl, key=lambda c: c[2])
        elif a.prefer == 'most' or not singles:
            pick = max(cl, key=lambda c: c[1])
        else:   # closeup: the person the close-up shots of this clip show (usually the guest)
            ref = statistics.median(singles)
            pick = min(cl, key=lambda c: abs(c[0] - ref))
        print(f'  WIDE SHOT in {key} at frame {shots[k][0]}: people at x={[int(c[0]) for c in cl]} -> following x={int(pick[0])} '
              f'(--prefer {a.prefer}; edit faces.json to follow someone else)')
        shots[k][1] = pick[0]
    for s in shots:
        if s[1] is None:
            cand = [(np.abs(g[s[0]] - g[o[0]]).mean(), o[1]) for o in shots if o[1] is not None]
            s[1] = min(cand)[1] if cand else SW / 2
    # keep every cut: merging "similar" shots once dropped a real cut and cropped onto the table
    return shots, len(fr), thumbs

def crop_x(cx):
    return int(min(SW - CW, max(0, cx - CW / 2)))

def crop_expr(shots):
    ex = str(crop_x(shots[-1][1]))
    for i in range(len(shots) - 2, -1, -1):
        ex = f'if(lt(n,{shots[i + 1][0]}),{crop_x(shots[i][1])},{ex})'
    return ex

def kmeans_auto(Xs, fixed=0):
    """k-means++ with restarts; k = `fixed`, or the smallest k in 2..5 after which more clusters stop helping."""
    Xs = np.asarray(Xs, float)
    def run(k, seed):
        rng = np.random.default_rng(seed); c = [Xs[rng.integers(len(Xs))]]
        for _ in range(k - 1):
            d2 = np.min(((Xs[:, None] - np.stack(c)[None]) ** 2).sum(2), axis=1) + 1e-12
            c.append(Xs[rng.choice(len(Xs), p=d2 / d2.sum())])
        c = np.stack(c)
        for _ in range(30):
            lab = ((Xs[:, None] - c[None]) ** 2).sum(2).argmin(1)
            c = np.stack([Xs[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
        return c, ((Xs - c[lab]) ** 2).sum()
    ks = [fixed] if fixed else [k for k in (2, 3, 4, 5) if k <= len(Xs)] or [1]
    fits = {k: min((run(k, sd) for sd in range(5)), key=lambda r: r[1]) for k in ks}
    K = ks[0]
    for k in ks[1:]:
        if fits[k][1] < fits[K][1] * 0.7:
            K = k
    return fits[K][0]

out_path = os.path.join(a.work, 'faces.json')
th_path = os.path.join(a.work, 'shot_thumbs.json')
TH = load(th_path) if os.path.exists(th_path) else {}
F = load(out_path) if os.path.exists(out_path) else {}
F.setdefault('_meta', {})['source'] = os.path.abspath(a.source)
F['_meta'].update({'width': SW, 'height': SH, 'crop_w': CW})
def clip_key(it):
    """Cache key. Includes end_time so trimming a clip re-plans its crop instead of reusing a stale one."""
    if 'start' in it:
        return f"t{it['start']:.2f}-{it['end']:.2f}"
    return (f"{it['start_idx']}-{it['end_idx']}" + (f"@{it['end_time']}" if it.get('end_time') else '')
            + (f"^{it['start_time']}" if it.get('start_time') else ''))

for it in P['items']:
    if it['type'] != 'clip':
        continue
    k = clip_key(it)
    if k in F:
        continue
    st, du = window(it)
    F[k], n, TH[k] = plan_clip(st, du, k)
    print(k, f'{n} frames', [(f, int(c)) for f, c, *_ in F[k]], flush=True)
save(TH, th_path)

# ---- camera-angle pass: the same camera should get the same crop in every clip. Face detection can
# miss someone (profile at the frame edge) and pick the other person in one clip only; and x positions
# from different cameras aren't comparable. Group shots by angle, report angles with mixed crops.
keys = [clip_key(it) for it in P['items'] if it['type'] == 'clip']
rows = [(k, i) for k in keys for i in range(len(F[k])) if k in TH and i < len(TH[k])]
if len(rows) >= 2:
    C = kmeans_auto([TH[k][i] for k, i in rows])
    for (k, i) in rows:
        ang = int(((np.array(TH[k][i]) - C) ** 2).sum(1).argmin())
        F[k][i] = F[k][i][:2] + [ang]
    force = {int(x.split('=')[0]): float(x.split('=')[1]) for x in a.angle_x.split(',') if '=' in x}
    for k, i in rows:
        if F[k][i][2] in force:
            F[k][i][1] = force[F[k][i][2]]
    for ang in sorted({F[k][i][2] for k, i in rows}):
        xs = [crop_x(F[k][i][1]) for k, i in rows if F[k][i][2] == ang]
        groups = []
        for x in sorted(xs):
            if groups and x - groups[-1][-1] <= CW * 0.3:
                groups[-1].append(x)
            else:
                groups.append([x])
        if len(groups) > 1 and ang not in force:
            # preview: one frame of this angle with every candidate crop drawn on it
            k0, i0 = next((k, i) for k, i in rows if F[k][i][2] == ang)
            it0 = next(it for it in P['items'] if it['type'] == 'clip' and clip_key(it) == k0)
            st0, _ = window(it0)
            img = decode(st0 + (F[k0][i0][0] + 3) / 29.97, 0.1, f'scale={SW // 4}:{SH // 4}', SW // 4, SH // 4, 'bgr24', 3)[0].copy()
            cols = [(0, 255, 255), (255, 0, 255), (0, 255, 0), (255, 128, 0)]
            for gi, g_ in enumerate(groups):
                x0 = int(statistics.median(g_)) // 4; col = cols[gi % len(cols)]
                cv2.rectangle(img, (x0 + gi * 2, gi * 2), (x0 + CW // 4 - gi * 2, SH // 4 - 1 - gi * 2), col, 2)
                lbl = f'x={int(statistics.median(g_) + CW / 2)} ({len(g_)} shots)'
                cv2.rectangle(img, (4, 6 + gi * 22), (14 + 9 * len(lbl), 26 + gi * 22), (0, 0, 0), -1)
                cv2.putText(img, lbl, (8, 22 + gi * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
            pv = os.path.join(a.work, f'angle_{ang}.jpg'); cv2.imwrite(pv, img)
            print(f'  ANGLE {ang}: {len(xs)} shots cropped at {len(groups)} different places '
                  f'{[(int(statistics.median(g_) + CW / 2), len(g_)) for g_ in groups]} -> look at {pv}; '
                  f'pick one with --angle-x {ang}=<x> (or keep it if you want to follow the speaker)')
save(F, out_path)
print('->', out_path)

if a.verify:
    thumbs, sides, keys = [], [], []
    for it in P['items']:
        if it['type'] != 'clip':
            continue
        k = clip_key(it); st, du = window(it)
        cw, ch = 19, 34
        cr = decode(st, du, f"crop={CW}:{SH}:x='{crop_expr(F[k])}':y=0,scale={cw}:{ch}", cw, ch).astype(float)
        # candidate crop centres = distinct positions used anywhere, compare the real crop to each
        cands = []
        for x in sorted(crop_x(sh[1]) for sh in F[k]):
            if not cands or x - cands[-1] > CW * 0.3:
                cands.append(x)
        if len(cands) == 1:                       # single-shot clip: compare against the far side too
            cands.append(SW - CW if cands[0] < (SW - CW) / 2 else 0)
        ref = np.stack([decode(st, du, f'crop={CW}:{SH}:x={x}:y=0,scale={cw}:{ch}', cw, ch).astype(float) for x in cands])
        side = np.abs(ref - cr[None]).mean(axis=(2, 3)).argmin(axis=0)
        th = decode(st, du, 'scale=32:18', 32, 18, 'rgb24', 3).reshape(len(cr), -1).astype(float) / 255
        thumbs.append(th); sides.append(np.array([cands[s] for s in side])); keys.append(k)
    X = np.concatenate(thumbs); side_all = np.concatenate(sides)
    c = kmeans_auto(X[::max(1, len(X) // 4000)], a.cameras); a.cameras = len(c)
    lab = ((X[:, None] - c[None]) ** 2).sum(2).argmin(1)
    # each camera angle should always be cropped at (about) the same place
    expect = {j: statistics.median(side_all[lab == j].tolist()) for j in range(a.cameras) if (lab == j).any()}
    bad = np.abs(side_all - np.array([expect[l] for l in lab])) > CW * 0.4
    o = 0
    for k, s in zip(keys, sides):
        b = np.where(bad[o:o + len(s)])[0]
        if len(b):
            print(f'  {k}: {len(b)} frames cropped differently from other shots of the same camera '
                  f'(frames {b[0]}-{b[-1]}). Fine if you chose this on purpose (e.g. following the speaker in a wide shot).')
        o += len(s)
    print(f'verify: {len(side_all)} frames through the real crop filter, {int(bad.sum())} mismatches '
          f'(camera angles found: {len(expect)})')
