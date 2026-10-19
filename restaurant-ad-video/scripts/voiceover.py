#!/usr/bin/env python3
"""Generate voiceover phrases with a TTS model on OpenRouter (default ElevenLabs Eleven v4 Turbo).

    python voiceover.py vo.json --out vo/ [--voice daniel] [--model elevenlabs/eleven-v4-turbo]

vo.json: {"p1": "[excited] Envie d'Italie, à Korba ?", "p2": "...", "end": "[warmly] Réservez au ..."}
One file per phrase lets build_reel.py place each line on the shot it describes. Audio tags in
[brackets] set delivery (Eleven v4 performs them instead of reading them). Write phone numbers
out in words in the target language; digits get read inconsistently.
Voices (eleven-v4-turbo): george sarah adam alice bella bill brian callum charlie chris daniel
eric harry jessica laura liam lily matilda river roger will. All are multilingual.
"""
import argparse, json, os
from common import post, duration

ap = argparse.ArgumentParser()
ap.add_argument('phrases'); ap.add_argument('--out', default='vo')
ap.add_argument('--voice', default='daniel'); ap.add_argument('--model', default='elevenlabs/eleven-v4-turbo')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
for k, t in json.load(open(a.phrases, encoding='utf-8')).items():
    p = os.path.join(a.out, f'{k}.mp3')
    data = post('/audio/speech', {'model': a.model, 'input': t, 'voice': a.voice, 'response_format': 'mp3'}, raw=True)
    if data[:1] == b'{':
        raise SystemExit(f'TTS error for {k}: {data[:300]!r}')
    open(p, 'wb').write(data); print(f'{p}: {duration(p):.2f}s')
