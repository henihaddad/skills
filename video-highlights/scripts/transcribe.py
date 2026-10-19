#!/usr/bin/env python3
"""Transcribe a video with word-level timestamps via OpenRouter (default: ElevenLabs Scribe v2).

    python transcribe.py source.mp4 --out work/ [--lang ar] [--model elevenlabs/scribe-v2]

Writes work/transcript.json ({"words": [[start, end, text], ...], "sents": [[start, end, text], ...]})
and work/transcript.txt (one "[idx] mm:ss.ss-ss.ss text" line per sentence, the format the
moment-picker and you read).

Why chunks: providers time out on long requests, and OpenRouter caps uploads. 10-minute mono
48 kbps mp3 chunks are ~3.6 MB and transcribe in parallel. Scribe v2 costs ~$0.11/hour of audio
and handles dialects (Tunisian derja, code-switching with French) well.
"""
import argparse, base64, concurrent.futures as cf, glob, json, os, re
from common import ff, post, save

ap = argparse.ArgumentParser()
ap.add_argument('video')
ap.add_argument('--out', default='work')
ap.add_argument('--lang', default=None, help='ISO code, e.g. ar, fr, en. Omit to auto-detect.')
ap.add_argument('--model', default='elevenlabs/scribe-v2')
ap.add_argument('--chunk', type=int, default=600, help='seconds per chunk')
a = ap.parse_args()

adir = os.path.join(a.out, 'audio'); os.makedirs(adir, exist_ok=True)
if not glob.glob(f'{adir}/chunk_*.mp3'):
    ff('-i', a.video, '-vn', '-ac', 1, '-ar', 16000, '-b:a', '48k', '-f', 'segment',
       '-segment_time', a.chunk, '-reset_timestamps', 1, f'{adir}/chunk_%03d.mp3')

def tx(path):
    i = int(re.search(r'chunk_(\d+)', path)[1]); out = f'{adir}/{i:03d}.json'
    if os.path.exists(out):
        return i, 'cached', 0
    body = {'model': a.model, 'input_audio': {'data': base64.b64encode(open(path, 'rb').read()).decode(), 'format': 'mp3'},
            'response_format': 'verbose_json', 'timestamp_granularities': ['word', 'segment']}
    if a.lang:
        body['language'] = a.lang
    d = post('/audio/transcriptions', body, timeout=900)
    save(d, out)
    return i, 'ok', (d.get('usage') or {}).get('cost') or 0

chunks = sorted(glob.glob(f'{adir}/chunk_*.mp3'))
with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(tx, chunks))
print('transcribed', len(res), 'chunks, cost $%.3f' % sum(r[2] for r in res))

words = []
for p in sorted(glob.glob(f'{adir}/[0-9][0-9][0-9].json')):
    off = int(os.path.basename(p)[:3]) * a.chunk
    for w in json.load(open(p, encoding='utf-8')).get('words', []):
        t = (w.get('word') or w.get('text') or '').strip()
        if t and w.get('type', 'word') == 'word':
            words.append([round(w['start'] + off, 3), round(w['end'] + off, 3), t])

# sentences: split on terminal punctuation, a pause > 0.9 s, or 28 words
sents, cur = [], []
for i, w in enumerate(words):
    cur.append(w)
    gap = words[i + 1][0] - w[1] if i + 1 < len(words) else 9
    if re.search(r'[.?!؟。！？]$', w[2]) or gap > 0.9 or len(cur) >= 28:
        sents.append([cur[0][0], cur[-1][1], ' '.join(x[2] for x in cur)]); cur = []
save({'words': words, 'sents': sents}, os.path.join(a.out, 'transcript.json'))
with open(os.path.join(a.out, 'transcript.txt'), 'w', encoding='utf-8') as f:
    for i, (s, e, t) in enumerate(sents):
        f.write(f'[{i}] {int(s // 60):02d}:{s % 60:05.2f}-{e % 60:05.2f} {t}\n')
print(f'{len(words)} words, {len(sents)} sentences -> {a.out}/transcript.json, transcript.txt')
