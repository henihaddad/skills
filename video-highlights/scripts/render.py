#!/usr/bin/env python3
"""Render a plan.json into a finished edit: 16:9 trailer/TL;DR or 9:16 reels.

    python render.py plan.json --source source.mp4 --work work/ --out trailer.mp4
    python render.py plan.json --source source1080.mp4 --work work/ --format 9:16 --out tldr_vertical.mp4 --split-chapters reels/

plan.json (written by pick_moments.py, edit freely):
  {"format": "16:9" | "9:16", "music": "music.mp3" | null, "music_mode": "bed" | "cards",
   "items": [
     {"type": "clip", "start_idx": 346, "end_idx": 346, "chapter": "optional chapter title",
      "end_time": optional absolute seconds to cut earlier/later than the sentence end},
     {"type": "card", "dur": 2.6, "lines": [{"text": "...", "role": "title|subtitle|small|number|chapter|brand|cta"}]}
   ]}

What you get:
* karaoke subtitles: one line of ~4-5 words, the word being spoken in yellow, from the
  transcript's word timestamps; RTL scripts are laid out right-to-left with per-word shaping.
* 16:9: subtle punch-in on alternate clips, grade + vignette.
* 9:16: face-tracked crop from faces.json (run facetrack.py first), bigger subtitles placed
  above Instagram/TikTok's bottom UI, chapter title pinned at the top below the top bar.
* music: "bed" = low under everything and louder on cards, aligned so the track's ending hits
  the end card; "cards" = music only on title cards, dialogue stays clean (better for long TL;DRs).
* --split-chapters DIR: one reel per chapter (starts straight on speech, ends on the end card),
  so a 5-minute TL;DR becomes reels under Instagram's 3-minute limit.
"""
import argparse, os, re
from PIL import Image, ImageDraw
from common import ff, load, clean_token, draw_words, centred, font, shape, is_rtl, duration, last_loud

ap = argparse.ArgumentParser()
ap.add_argument('plan')
ap.add_argument('--source', required=True)
ap.add_argument('--work', default='work')
ap.add_argument('--out', required=True)
ap.add_argument('--format', choices=['16:9', '9:16'], default=None)
ap.add_argument('--split-chapters', default=None, metavar='DIR')
ap.add_argument('--brand', default=None, help='small line under the chapter tag in 9:16, e.g. "Guest on Show"')
a = ap.parse_args()

P = load(a.plan); FMT = a.format or P.get('format', '16:9'); V = FMT == '9:16'
T = load(os.path.join(a.work, 'transcript.json')); S, WD = T['sents'], T['words']
W, H, FPS = (1080, 1920, 30) if V else (1280, 720, 30)
SEG = os.path.join(a.work, 'seg_' + FMT.replace(':', 'x')); os.makedirs(SEG, exist_ok=True)
GOLD, GRAY = (214, 175, 96), (170, 170, 170)
ROLE = {  # role: (size 16:9, size 9:16, colour)
    'title': (84, 110, 'white'), 'subtitle': (44, 62, GOLD), 'small': (32, 46, GRAY), 'number': (64, 96, GOLD),
    'chapter': (60, 76, 'white'), 'brand': (96, 130, 'white'), 'cta': (40, 54, GOLD)}
SUB_SIZE, SUB_Y = (74, 1330) if V else (54, H - 130)
MAXW, MAXC = (4, 18) if V else (5, 24)
EASTERN = '٠١٢٣٤٥٦٧٨٩'

FACES = None
if V:
    fp = os.path.join(a.work, 'faces.json')
    if not os.path.exists(fp):
        raise SystemExit('9:16 needs faces.json - run facetrack.py first.')
    FACES = load(fp); SW, SH, CW = FACES['_meta']['width'], FACES['_meta']['height'], FACES['_meta']['crop_w']

def window(it):
    """Clip window in source seconds: sentence indices (+ optional end_time) or absolute start/end."""
    if 'start' in it:
        return it['start'], it['end'] - it['start']
    st = it.get('start_time') or S[it['start_idx']][0] - 0.12
    en = it.get('end_time') or S[it['end_idx']][1] + 0.3
    return st, en - st

def clip_key(it):
    if 'start' in it:
        return f"t{it['start']:.2f}-{it['end']:.2f}"
    return (f"{it['start_idx']}-{it['end_idx']}" + (f"@{it['end_time']}" if it.get('end_time') else '')
            + (f"^{it['start_time']}" if it.get('start_time') else ''))

def card_png(lines, path):
    im = Image.new('RGB', (W, H), 'black'); d = ImageDraw.Draw(im)
    sizes = [ROLE[l.get('role', 'title')][1 if V else 0] for l in lines if l.get('text')]
    y = H / 2 - sum(sizes) * (0.9 if V else 0.75)
    rtl_doc = any(is_rtl(l.get('text', '')) for l in lines)
    for l in lines:
        t = l.get('text', '')
        if not t:
            continue
        role = l.get('role', 'title'); size = ROLE[role][1 if V else 0]; col = l.get('color') or ROLE[role][2]
        if role == 'number' and rtl_doc and t.isdigit():
            t = ''.join(EASTERN[int(c)] for c in t)
        # RTL lines go word by word (kind=None) so digits/Latin/"·" get a font that has them;
        # rendering a whole Arabic line in the Arabic font turns "4" or "·" into empty boxes.
        kind = 'serif' if (role == 'brand' and not is_rtl(t)) else (None if is_rtl(t) else 'latin')
        centred(d, y, t, size, W, fill=col, kind=kind)
        y += size * 1.5
    im.save(path)

def tag_png(chapter, path):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if not chapter:
        im.save(path); return
    kind = 'rtl' if is_rtl(chapter) else 'latin'; s = shape(chapter)
    if V:
        f = font(kind, 52); w = d.textlength(s, font=f)
        d.rounded_rectangle([(W - w) / 2 - 36, 230, (W + w) / 2 + 36, 322], radius=24, fill=(0, 0, 0, 170))
        d.text(((W - w) / 2, 238), s, font=f, fill=GOLD)
        if a.brand:
            centred(d, 340, a.brand, 34, W, fill='white', kind='rtl' if is_rtl(a.brand) else 'latin', stroke=3)
    else:
        f = font(kind, 28); w = d.textlength(s, font=f)
        d.rounded_rectangle([W - w - 70, 26, W - 30, 74], radius=12, fill=(0, 0, 0, 150))
        d.text((W - w - 50, 32), s, font=f, fill=GOLD)
    im.save(path)

def karaoke(st, du, k):
    words = [[w[0], w[1], clean_token(w[2])] for w in WD if st - 0.01 <= w[0] < st + du - 0.2]
    words = [w for w in words if w[2]]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= MAXW or sum(len(x[2]) for x in cur) > MAXC or re.search(r'[.?!؟،,]$', w[2]):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    frames, n, t = [], 0, 0.0
    def png(ch, active):
        nonlocal n
        p = f'{SEG}/k{k:03d}_{n:04d}.png'; n += 1
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        draw_words(ImageDraw.Draw(im), [x[2] for x in ch], SUB_Y, W, SUB_SIZE, active=active, stroke=7 if V else 5)
        im.save(p); return p
    if not chunks:
        frames.append((png([], -1), du))
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0][0] - st if ci + 1 < len(chunks) else du
        for wi, w in enumerate(ch):
            s0 = max(0, w[0] - st); s1 = (ch[wi + 1][0] - st) if wi + 1 < len(ch) else nxt
            if s0 > t:   # silence before this word: keep the previous highlight (or none at chunk start)
                frames.append((png(ch, wi - 1), s0 - t)); t = s0
            frames.append((png(ch, wi), max(0.04, s1 - t))); t = max(t, s1)
    lst = f'{SEG}/k{k:03d}.txt'
    with open(lst, 'w') as f:
        f.write('ffconcat version 1.0\n')
        for p, d in frames:
            f.write(f"file '{os.path.abspath(p)}'\nduration {d:.3f}\n")
        f.write(f"file '{os.path.abspath(frames[-1][0])}'\n")
    return lst

def crop_filter(it, k):
    if V:
        shots = FACES.get(clip_key(it))
        if not shots:
            raise SystemExit(f"faces.json has no entry for clip {clip_key(it)}; re-run facetrack.py")
        X = lambda c: int(min(SW - CW, max(0, c - CW / 2)))
        ex = str(X(shots[-1][1]))
        for i in range(len(shots) - 2, -1, -1):
            ex = f'if(lt(n,{shots[i + 1][0]}),{X(shots[i][1])},{ex})'
        # crop must come first in the chain so n counts source frames exactly like facetrack.py
        return f"crop={CW}:{SH}:x='{ex}':y=0,scale={W}:{H}:flags=lanczos,"
    return f'scale={int(W * 1.1)}:{int(H * 1.1)},crop={W}:{H},' if k % 2 == 0 else f'scale={W}:{H},'

music = P.get('music') and os.path.join(os.path.dirname(os.path.abspath(a.plan)), P['music'])
if music and not os.path.exists(music):
    music = P['music'] if os.path.exists(P['music']) else None
mode = P.get('music_mode', 'bed')
mlen = duration(music) if music else 0
mpos = max(0, mlen * 0.45)

segs, spans, t = [], [], 0.0
for k, it in enumerate(P['items']):
    o = f'{SEG}/{k:03d}.mp4'
    if it['type'] == 'card':
        du = float(it['dur']); card_png(it['lines'], f'{SEG}/{k:03d}.png')
        vf = f'fade=in:st=0:d=0.3,fade=out:st={du - 0.3:.2f}:d=0.3,fps={FPS},format=yuv420p'
        if music and mode == 'cards':
            ff('-loop', 1, '-t', du, '-i', f'{SEG}/{k:03d}.png', '-ss', f'{mpos:.1f}', '-t', du, '-i', music, '-filter_complex',
               f'[0:v]{vf}[v];[1:a]aresample=44100,volume=0.75,afade=t=in:d=0.25,afade=t=out:st={du - 0.5:.2f}:d=0.5,aformat=channel_layouts=stereo[a]',
               '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', 18, '-c:a', 'aac', '-ar', 44100, '-t', du, o)
            mpos = mlen * 0.45 + ((mpos - mlen * 0.45 + du + 6) % max(1, mlen * 0.45))
        else:
            ff('-loop', 1, '-t', du, '-i', f'{SEG}/{k:03d}.png', '-f', 'lavfi', '-t', du, '-i', 'anullsrc=r=44100:cl=stereo',
               '-vf', vf, '-c:v', 'libx264', '-crf', 18, '-c:a', 'aac', '-shortest', o)
        spans.append((t, t + du)); t += du
    else:
        st, du = window(it); lst = karaoke(st, du, k)
        tg = f'{SEG}/tag{k:03d}.png'; tag_png(it.get('chapter'), tg)
        ff('-ss', f'{st:.2f}', '-t', f'{du:.2f}', '-i', a.source, '-f', 'concat', '-safe', 0, '-i', lst,
           '-loop', 1, '-t', f'{du:.2f}', '-i', tg, '-filter_complex',
           f"[0:v]{crop_filter(it, k)}eq=contrast=1.1:saturation=0.88,vignette=PI/5,fps={FPS},"
           f"fade=in:st=0:d=0.12,fade=out:st={du - 0.18:.2f}:d=0.18[v];"
           f"[1:v]format=rgba,setpts=PTS-STARTPTS[s];[v][s]overlay=0:0:eof_action=repeat[v2];[v2][2:v]overlay=0:0,format=yuv420p[vo];"
           f"[0:a]aresample=44100,aformat=channel_layouts=stereo,volume=1.15,afade=t=in:d=0.08,afade=t=out:st={du - 0.18:.2f}:d=0.18[ao]",
           '-map', '[vo]', '-map', '[ao]', '-c:v', 'libx264', '-crf', 20 if V else 19, '-c:a', 'aac', '-ar', 44100, o)
        t += du
    segs.append(o); print(f'{k:3d} {it["type"]:5s} -> {t:6.1f}s', flush=True)

def join(seglist, out, bed=False, total=None):
    lst = out + '.list.txt'
    with open(lst, 'w') as f:
        f.write(''.join(f"file '{os.path.abspath(s)}'\n" for s in seglist))
    tmp = out + '.tmp.mp4'
    ff('-f', 'concat', '-safe', 0, '-i', lst, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', tmp)
    if bed and music:
        # line the track's last LOUD moment up with the end of the video: generated tracks end with
        # seconds of silent fade, and aligning the file end left the end card with no music
        audible = last_loud(music)
        loop = []
        if audible < total:
            print(f'WARNING: music is audible for {audible:.1f}s but the video is {total:.1f}s - looping it '
                  '(generate a longer track for a clean ending)')
            loop, off = ['-stream_loop', '-1'], 0
        else:
            off = audible - total
        loud = '+'.join(f'between(t,{s0:.2f},{s1:.2f})' for s0, s1 in spans) or '0'
        ff('-i', tmp, *loop, '-ss', f'{off:.2f}', '-i', music, '-filter_complex',
           f"[1:a]aresample=44100,volume='if({loud},0.9,0.22)':eval=frame,afade=t=in:d=1[m];[0:a]volume=1.0[d];"
           f"[d][m]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]",
           '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out)
    else:
        ff('-i', tmp, '-c:v', 'copy', '-af', 'alimiter=limit=0.95', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out)
    os.remove(tmp); os.remove(lst)

join(segs, a.out, bed=(mode == 'bed'), total=t)
print(f'{a.out}: {duration(a.out):.1f}s {W}x{H}')

if a.split_chapters:
    os.makedirs(a.split_chapters, exist_ok=True)
    end_seg = segs[-1] if P['items'][-1]['type'] == 'card' else None
    groups, cur = [], None
    for it, sg in zip(P['items'], segs):
        if it['type'] == 'card' and it.get('chapter_start'):
            cur = []; groups.append(cur); continue
        if cur is not None and it['type'] == 'clip':
            cur.append(sg)
    for i, g in enumerate(groups, 1):
        out = os.path.join(a.split_chapters, f'reel_{i}.mp4'); join(g + ([end_seg] if end_seg else []), out)
        d = duration(out)
        print(f'{out}: {d:.1f}s' + ('  (over Instagram 3-min reel limit!)' if d > 180 else ''))
