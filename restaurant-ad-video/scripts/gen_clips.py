#!/usr/bin/env python3
"""Animate each cropped photo into a short clip with an image-to-video model on OpenRouter.

    python gen_clips.py shots.json --src src/ --out clips_kling/ --model kwaivgi/kling-v3.0-pro
    python gen_clips.py shots.json --src src/ --out clips_seed480/ --model bytedance/seedance-2.5 --resolution 480p

shots.json: [{"id": "055", "prompt": "Slow orbit, a lemon wedge squeezes juice onto the salmon..."}, ...]
A shared suffix is appended to every prompt to keep the real dish unchanged (see FIDELITY).

Clips are generated in parallel (8 at a time), cached (re-runs skip finished ids), and the
actual billed cost is printed. Check the key's remaining budget first: a mid-run 403 "Key limit
exceeded" leaves you with half a set.
"""
import argparse, base64, concurrent.futures as cf, json, os, time, urllib.request
from common import post, key, key_status

FIDELITY = (' Keep the dish, plate and ingredients exactly as in the photo. Premium food commercial look, warm '
            'restaurant lighting, shallow depth of field, realistic physics. No text, no logos, no faces.')
ap = argparse.ArgumentParser()
ap.add_argument('shots'); ap.add_argument('--src', default='src'); ap.add_argument('--out', default='clips')
ap.add_argument('--model', default='kwaivgi/kling-v3.0-pro')
ap.add_argument('--resolution', default='720p'); ap.add_argument('--aspect', default='9:16')
ap.add_argument('--duration', type=int, default=5); ap.add_argument('--audio', action='store_true')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
shots = json.load(open(a.shots))
try:
    print('key budget:', key_status())
except Exception as e:
    print('could not read key budget:', e)

def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key()}), timeout=120))

def run(s):
    n = s['id']; out = os.path.join(a.out, f'{n}.mp4')
    if os.path.exists(out):
        return n, 'cached', 0
    img = base64.b64encode(open(os.path.join(a.src, f'{n}.jpg'), 'rb').read()).decode()
    body = {'model': a.model, 'prompt': s['prompt'] + FIDELITY, 'duration': a.duration, 'resolution': a.resolution,
            'aspect_ratio': a.aspect, 'generate_audio': a.audio,
            'frame_images': [{'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + img}, 'frame_type': 'first_frame'}]}
    try:
        j = post('/videos', body, timeout=120)
    except Exception as e:
        return n, f'submit error: {e}', 0
    for _ in range(120):
        time.sleep(10); st = get(j['polling_url'])
        if st['status'] == 'completed':
            req = urllib.request.Request(st['unsigned_urls'][0], headers={'Authorization': 'Bearer ' + key()})
            open(out, 'wb').write(urllib.request.urlopen(req, timeout=300).read())
            return n, 'ok', (st.get('usage') or {}).get('cost') or 0
        if st['status'] == 'failed':
            return n, f"failed: {st.get('error')}", 0
    return n, 'timeout', 0

with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(run, shots))
for r in res:
    print(*r)
print(f'total ${sum(r[2] for r in res):.2f} for {sum(r[1] == "ok" for r in res)} new clips -> {a.out}')
