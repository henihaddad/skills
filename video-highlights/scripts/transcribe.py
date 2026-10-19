#!/usr/bin/env python3
"""Transcribe a video with word-level timestamps via OpenRouter (default: ElevenLabs Scribe v2).

    python transcribe.py source.mp4 --out work/ [--lang ar] [--diarize]

Writes work/transcript.json ({"words": [[start, end, text(, speaker)], ...], "sents": [[start, end, text], ...]})
and work/transcript.txt (one "[idx] mm:ss.ss-mm:ss.ss text" line per sentence; with --diarize the
line also shows the speaker as "S2").

Chunking: providers time out on long requests, so audio is sent in 10-minute chunks (~3.6 MB
each, in parallel). Chunks overlap by 4 s and each word is kept only from the chunk that "owns"
its start time, so nothing is lost or duplicated at the seams.

--diarize adds speaker labels. Labels are only consistent WITHIN one request, so diarized runs
send the whole file in one request when it's <= 60 min (45 min took ~60 s); longer files fall
back to chunks and print a warning (speaker numbers then restart per chunk). Use
extract_speaker.py to turn a diarized transcript into "every moment of person X".

Cost: Scribe v2 bills ~$0.22 per hour of audio (~$0.36 for a 97-min episode).
"""
import argparse, base64, concurrent.futures as cf, glob, json, os, re, shutil
from common import ff, post, save, load, duration, ts, is_mixed

ap = argparse.ArgumentParser()
ap.add_argument('video')
ap.add_argument('--out', default='work')
ap.add_argument('--lang', default=None, help='ISO code, e.g. ar, fr, en. Omit to auto-detect.')
ap.add_argument('--model', default='elevenlabs/scribe-v2')
ap.add_argument('--chunk', type=int, default=600, help='seconds per chunk')
ap.add_argument('--diarize', action='store_true', help='speaker labels (single request up to 60 min)')
a = ap.parse_args()

OVERLAP = 4
total = duration(a.video)
single = a.diarize and total <= 3600
step = int(total) + 10 if single else a.chunk
adir = os.path.join(a.out, 'audio')
meta = {'video': os.path.abspath(a.video), 'chunk': step, 'overlap': OVERLAP, 'model': a.model, 'diarize': a.diarize, 'lang': a.lang}
mp = os.path.join(adir, 'meta.json')
if os.path.exists(mp) and load(mp) != meta:
    print('chunk settings changed since the last run -> clearing cached audio/transcripts')
    shutil.rmtree(adir)
os.makedirs(adir, exist_ok=True); save(meta, mp)
if a.diarize and not single:
    print(f'WARNING: {total / 60:.0f} min > 60 min: diarizing in chunks, speaker numbers restart in every chunk.')

starts = list(range(0, int(total) + 1, step))
for i, s in enumerate(starts):
    p = f'{adir}/chunk_{i:03d}.mp3'
    if not os.path.exists(p):
        ff('-ss', s, '-t', step + OVERLAP, '-i', a.video, '-vn', '-ac', 1, '-ar', 16000, '-b:a', '32k' if single else '48k', p)

def tx(i):
    out = f'{adir}/{i:03d}.json'
    if os.path.exists(out):
        return i, 'cached', 0
    body = {'model': a.model, 'input_audio': {'data': base64.b64encode(open(f'{adir}/chunk_{i:03d}.mp3', 'rb').read()).decode(), 'format': 'mp3'},
            'response_format': 'verbose_json', 'timestamp_granularities': ['word', 'segment']}
    if a.lang:
        body['language'] = a.lang
    if a.diarize:
        body['provider'] = {'options': {'elevenlabs': {'diarize': True}}}
    d = post('/audio/transcriptions', body, timeout=1500)
    save(d, out)
    return i, 'ok', (d.get('usage') or {}).get('cost') or 0

with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(tx, range(len(starts))))
print(f'transcribed {len(res)} request(s), cost ${sum(r[2] for r in res):.3f}')

words = []
for i, s in enumerate(starts):
    lo, hi = s, (starts[i + 1] if i + 1 < len(starts) else 1e9)
    for w in load(f'{adir}/{i:03d}.json').get('words', []):
        t = (w.get('word') or w.get('text') or '').strip()
        if not t or w.get('type', 'word') != 'word':
            continue
        st = w['start'] + s
        if lo <= st < hi:                      # the chunk that owns this start time keeps the word
            row = [round(st, 3), round(w['end'] + s, 3), t]
            if a.diarize:
                row.append(w.get('speaker', w.get('speaker_id')))
            words.append(row)
words.sort(key=lambda w: w[0])

sents, cur = [], []
for i, w in enumerate(words):
    cur.append(w)
    gap = words[i + 1][0] - w[1] if i + 1 < len(words) else 9
    spk_change = a.diarize and i + 1 < len(words) and words[i + 1][3] != w[3]
    if re.search(r'[.?!؟。！？]$', w[2]) or gap > 0.9 or len(cur) >= 28 or spk_change:
        sents.append([cur[0][0], cur[-1][1], ' '.join(x[2] for x in cur)] + ([cur[0][3]] if a.diarize else [])); cur = []
save({'words': words, 'sents': sents}, os.path.join(a.out, 'transcript.json'))
with open(os.path.join(a.out, 'transcript.txt'), 'w', encoding='utf-8') as f:
    for i, s in enumerate(sents):
        spk = f' S{s[3]}' if a.diarize else ''
        f.write(f'[{i}] {ts(s[0])}-{ts(s[1])}{spk} {s[2]}\n')
mixed = [(ts(w[0]), w[2]) for w in words if is_mixed(w[2])]
print(f'{len(words)} words, {len(sents)} sentences -> {a.out}/transcript.json, transcript.txt')
if mixed:
    print(f'{len(mixed)} mixed Arabic+Latin tokens (usually ASR errors; fix in transcript.json if they land in a clip):',
          ', '.join(f'{t} {w}' for t, w in mixed[:15]))
