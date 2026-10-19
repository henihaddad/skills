#!/usr/bin/env python3
"""Fix ASR mistakes in work/transcript.json once, keeping words[] and sents[] in sync.

    python fix_transcript.py work "الوسلati=الوسلاتي"                      # every occurrence
    python fix_transcript.py work "هالشالة بكا لوجي=هالشهادة البكالوريا"    # multi-token phrase (merge/split)
    python fix_transcript.py work "يتولد=يورّدو" --at 779.5                   # only the occurrence nearest 12:59.5

The left side is matched against consecutive word tokens (punctuation ignored). The right side
replaces them; when the token count changes, the original time span is shared out evenly, so
karaoke timing stays right. Sentence texts are rebuilt from the words, and transcript.txt is
rewritten. A backup of the first version is kept as transcript.orig.json.
Check names (people, places) before putting them on cards - ASR spells them roughly.
"""
import argparse, os, re, shutil
from common import load, save, ts

ap = argparse.ArgumentParser()
ap.add_argument('work'); ap.add_argument('fixes', nargs='+', help='"old=new" pairs')
ap.add_argument('--at', type=float, default=None, help='only fix the occurrence nearest this time (seconds)')
a = ap.parse_args()
p = os.path.join(a.work, 'transcript.json')
if not os.path.exists(os.path.join(a.work, 'transcript.orig.json')):
    shutil.copy(p, os.path.join(a.work, 'transcript.orig.json'))
T = load(p); W = T['words']
key = lambda t: re.sub(r'[^\w]', '', t)

for fx in a.fixes:
    old, _, new = fx.partition('=')
    ot, nt = old.split(), new.split()
    hits = [i for i in range(len(W) - len(ot) + 1) if all(key(W[i + k][2]) == key(ot[k]) for k in range(len(ot)))]
    if a.at is not None and hits:
        hits = [min(hits, key=lambda i: abs(W[i][0] - a.at))]
    if not hits:
        print(f'not found: {old!r}'); continue
    for i in reversed(hits):
        span = W[i:i + len(ot)]; s0, s1 = span[0][0], span[-1][1]
        tail = re.search(r'[^\w]+$', span[-1][2]); tail = tail.group(0) if tail else ''
        extra = span[0][3:]                                   # keep speaker label if present
        step = (s1 - s0) / len(nt)
        rows = [[round(s0 + k * step, 3), round(s0 + (k + 1) * step, 3), w + (tail if k == len(nt) - 1 else '')] + extra
                for k, w in enumerate(nt)]
        if len(nt) == len(ot):                               # same token count: keep original word times
            rows = [[o[0], o[1], w + (tail if k == len(nt) - 1 else '')] + o[3:] for k, (o, w) in enumerate(zip(span, nt))]
        W[i:i + len(ot)] = rows
    print(f'{old!r} -> {new!r}: {len(hits)} fixed at ' + ', '.join(ts(W[i][0]) for i in hits[:8]))

for s in T['sents']:                                          # rebuild sentence texts from the words
    s[2] = ' '.join(w[2] for w in W if s[0] - 0.001 <= w[0] <= s[1] + 0.001) or s[2]
save(T, p)
with open(os.path.join(a.work, 'transcript.txt'), 'w', encoding='utf-8') as f:
    for i, s in enumerate(T['sents']):
        f.write(f'[{i}] {ts(s[0])}-{ts(s[1])}' + (f' S{s[3]}' if len(s) > 3 else '') + f' {s[2]}\n')
print('saved', p)
