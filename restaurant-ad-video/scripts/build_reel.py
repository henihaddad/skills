#!/usr/bin/env python3
"""Assemble generated clips into a 9:16 restaurant reel: hook text, dish captions with prices,
voiceover lines placed on their shots, music bed, and an end card with name/rating/address/phone.

    python build_reel.py reel.json

reel.json (all paths relative to the json file):
{
  "out": "reel_kling.mp4",
  "clips_dir": "clips_kling",
  "hook": {"text": "Envie d'Italie ?", "sub": "BELLA ARTISTA · KORBA"},
  "shots": [{"id": "019", "start": 0.8, "dur": 2.4, "caption": "Fruits de mer", "price": null},
            {"id": "055", "start": 2.4, "dur": 2.2, "caption": "Saumon grillé", "price": "45 DT"}],
  "endcard": {"bg": "photos/110.jpg", "name": "Bella Artista", "tagline": "CUISINE ITALIENNE",
              "rating": "4,5 sur Google", "address": "Bd de l'Environnement, Korba",
              "label": "Réservations", "phone": "+216 00 000 000", "dur": 7.6},
  "voice": [{"file": "vo/p1.mp3", "at": 0.3}, {"file": "vo/end.mp3", "at": "end+0.6", "trim": [0, 6.5]}],
  "music": {"file": "music.mp3", "volume": 0.24}
}

`start` is where in the generated clip to begin: the interesting motion (pour, squeeze, drip)
usually happens 2-4 s into a 5 s clip, so start ~2.3 s for most shots and earlier for the hook.
Swapping "clips_dir" re-renders the same edit with another model's clips (Kling vs Seedance)
so the comparison is fair. Only put a price on a caption if you read it on the menu photo.
"""
import json, math, os, sys
from PIL import Image, ImageDraw, ImageFilter
from common import ff, font, shape, is_rtl, draw_words, duration

cfg_path = sys.argv[1]; base = os.path.dirname(os.path.abspath(cfg_path))
C = json.load(open(cfg_path, encoding='utf-8')); P = lambda p: p if os.path.isabs(p) else os.path.join(base, p)
W, H, FPS = 1080, 1920, 30
GOLD = (232, 196, 120)
SEG = P('seg_' + os.path.splitext(os.path.basename(C['out']))[0]); os.makedirs(SEG, exist_ok=True)

def text(d, xy, t, size, fill='white', kind=None, anchor_right=False):
    k = kind or ('rtl' if is_rtl(t) else 'latin'); f = font(k, size); s = shape(t)
    x, y = xy
    if anchor_right:
        x -= d.textlength(s, font=f)
    for dx, dy in ((0, 4), (2, 5), (-2, 5)):
        d.text((x + dx, y + dy), s, font=f, fill=(0, 0, 0, 150))
    d.text((x, y), s, font=f, fill=fill)
    return d.textlength(s, font=f)

def ctext(d, y, t, size, fill='white', kind=None):
    k = kind or ('rtl' if is_rtl(t) else 'latin'); w = d.textlength(shape(t), font=font(k, size))
    text(d, ((W - w) / 2, y), t, size, fill, k)

def caption_png(i, cap, price, hook):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k in range(560):
        d.line([(0, H - 560 + k), (W, H - 560 + k)], fill=(0, 0, 0, int(170 * (k / 560) ** 1.5)))
    if hook:
        for k in range(420):
            d.line([(0, k), (W, k)], fill=(0, 0, 0, int(150 * (1 - k / 420) ** 1.5)))
        ctext(d, 170, hook['text'], 92); ctext(d, 295, hook.get('sub', ''), 40, GOLD)
    rtl = is_rtl(cap or '')
    if cap:
        if rtl:
            text(d, (W - 80, 1560), cap, 72, anchor_right=True); d.rectangle([W - 200, 1530, W - 80, 1536], fill=GOLD)
        else:
            text(d, (80, 1560), cap, 72); d.rectangle([80, 1530, 200, 1536], fill=GOLD)
    if price:
        f = font('latin', 54); tw = d.textlength(price, font=f)
        x0 = W - 80 - tw - 56 if rtl else 80
        d.rounded_rectangle([x0, 1665, x0 + tw + 56, 1755], radius=45, fill=GOLD); d.text((x0 + 28, 1672), price, font=f, fill=(30, 20, 10))
    p = f'{SEG}/cap{i}.png'; im.save(p); return p

def endcard_png(e):
    bg = Image.open(P(e['bg'])).convert('RGB') if e.get('bg') else Image.new('RGB', (W, H), (20, 16, 12))
    s = max(W / bg.width, H / bg.height); bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H)).filter(ImageFilter.GaussianBlur(18))
    bg = Image.blend(bg, Image.new('RGB', (W, H), 'black'), 0.62).convert('RGBA'); d = ImageDraw.Draw(bg)
    ctext(d, 560, e['name'], 170, kind=None if is_rtl(e['name']) else 'serif')
    if e.get('tagline'):
        ctext(d, 770, e['tagline'], 52, GOLD); d.line([(390, 880), (690, 880)], fill=GOLD, width=3)
    if e.get('rating'):   # draw the star as a polygon: many fonts lack the ★ glyph
        f = font('latin', 58); tw = d.textlength(e['rating'], font=f); x0 = (W - tw - 70) / 2; cx, cy = x0 + 26, 975
        d.polygon([(cx + (28 if k % 2 == 0 else 12) * math.sin(k * math.pi / 5), cy - (28 if k % 2 == 0 else 12) * math.cos(k * math.pi / 5)) for k in range(10)], fill=GOLD)
        d.text((x0 + 70, 940), e['rating'], font=f, fill='white')
    if e.get('address'):
        ctext(d, 1060, e['address'], 54)
    if e.get('phone'):
        ctext(d, 1240, e.get('label', ''), 48, GOLD); ctext(d, 1310, e['phone'], 96)
    p = f'{SEG}/endcard.png'; bg.convert('RGB').save(p); return p

segs = []; t = 0.0
for i, s in enumerate(C['shots']):
    cap = caption_png(i, s.get('caption'), s.get('price'), C.get('hook') if i == 0 else None); o = f'{SEG}/{i:02d}.mp4'
    ff('-ss', s.get('start', 2.3), '-t', s['dur'], '-i', P(os.path.join(C['clips_dir'], s['id'] + '.mp4')), '-loop', 1, '-t', s['dur'], '-i', cap,
       '-filter_complex', f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},setsar=1[v];"
       f"[1:v]format=rgba,fade=in:st=0.15:d=0.3:alpha=1[c];[v][c]overlay=0:0,format=yuv420p", '-an', '-c:v', 'libx264', '-crf', 18, o)
    segs.append(o); t += s['dur']
tE = t; e = C['endcard']; END = e.get('dur', 7.6)
ff('-loop', 1, '-i', endcard_png(e), '-vf', f"scale=2160:-1,zoompan=z='1+0.0006*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(END * FPS)}:s={W}x{H}:fps={FPS},fade=in:st=0:d=0.4,format=yuv420p",
   '-t', END, '-c:v', 'libx264', '-crf', 18, f'{SEG}/zz.mp4'); segs.append(f'{SEG}/zz.mp4'); T = tE + END
lst = f'{SEG}/list.txt'; open(lst, 'w').write(''.join(f"file '{x}'\n" for x in segs))
ff('-f', 'concat', '-safe', 0, '-i', lst, '-c', 'copy', f'{SEG}/video.mp4')

ins, fc, labels = [], '', []
for k, v in enumerate(C.get('voice', [])):
    at = v['at']; at = tE + float(at.split('+')[1]) if isinstance(at, str) and at.startswith('end') else float(at)
    ins += ['-i', P(v['file'])]; trim = v.get('trim')
    fc += f"[{k}:a]{f'atrim={trim[0]}:{trim[1]},' if trim else ''}asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo,adelay={int(at * 1000)}|{int(at * 1000)}[v{k}];"
    labels.append(f'[v{k}]')
    d_end = at + (trim[1] - trim[0] if trim else duration(P(v['file'])))
    if d_end > T:
        print(f"warning: voice {v['file']} ends at {d_end:.1f}s, after the video ({T:.1f}s) - it will be cut")
n = len(labels); mus = C.get('music')
if mus:
    ins += ['-i', P(mus['file'])]
    fc += f"[{n}:a]atrim=0:{T},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo,volume={mus.get('volume', 0.24)},afade=t=out:st={T - 2.5}:d=2.5[m];"
    labels.append('[m]')
if labels:
    fc += f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[out]"
    ff(*ins, '-filter_complex', fc, '-map', '[out]', '-t', T, '-c:a', 'aac', '-b:a', '192k', f'{SEG}/audio.m4a')
    ff('-i', f'{SEG}/video.mp4', '-i', f'{SEG}/audio.m4a', '-map', '0:v', '-map', '1:a', '-c', 'copy', '-shortest', '-movflags', '+faststart', P(C['out']))
else:
    ff('-i', f'{SEG}/video.mp4', '-c', 'copy', '-movflags', '+faststart', P(C['out']))
print(f"{P(C['out'])}: {duration(P(C['out'])):.1f}s 1080x1920, end card at {tE:.1f}s")
