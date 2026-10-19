#!/usr/bin/env python3
"""Generate an instrumental music bed with Google Lyria 3 via OpenRouter.

    python music.py "90-second dark tense documentary trailer score ..." --out music.mp3 [--clip]

Lyria returns audio only when you ask for the audio modality AND stream; a plain non-streamed
chat call is still billed but returns placeholder text with no audio. Pro (~$0.08) makes full
tracks (~60-90 s+, ask for the length in the prompt); --clip (~$0.04) is fixed at ~30 s.
"""
import argparse, base64, json, urllib.request
from common import API, key, duration

ap = argparse.ArgumentParser()
ap.add_argument('prompt')
ap.add_argument('--out', default='music.mp3')
ap.add_argument('--clip', action='store_true')
a = ap.parse_args()
model = 'google/lyria-3-clip-preview' if a.clip else 'google/lyria-3-pro-preview'
body = {'model': model, 'modalities': ['text', 'audio'], 'audio': {'format': 'mp3'}, 'stream': True,
        'messages': [{'role': 'user', 'content': a.prompt + ' Instrumental, no vocals.'}]}
req = urllib.request.Request(API + '/chat/completions', data=json.dumps(body).encode(),
                             headers={'Authorization': 'Bearer ' + key(), 'Content-Type': 'application/json'})
chunks = []
with urllib.request.urlopen(req, timeout=900) as r:
    for line in r:
        line = line.decode(errors='replace').strip()
        if not line.startswith('data: ') or line.endswith('[DONE]'):
            continue
        try:
            j = json.loads(line[6:])
        except ValueError:
            continue
        for c in j.get('choices', []):
            d = (c.get('delta') or {}).get('audio') or {}
            if d.get('data'):
                chunks.append(d['data'])
if not chunks:
    raise SystemExit('No audio returned. Check the model name and that streaming + audio modality are set.')
open(a.out, 'wb').write(base64.b64decode(''.join(chunks)))
print(f'saved {a.out} ({duration(a.out):.1f}s)')
