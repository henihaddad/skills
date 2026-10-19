#!/usr/bin/env python3
"""Every moment of ONE person: turn a diarized transcript into a compilation plan.

    python transcribe.py source.mp4 --out work --lang ar --diarize          # speaker labels first
    python extract_speaker.py work --source source.mp4 --sheet              # who is who? -> work/speakers.jpg
    python extract_speaker.py work --who "Ahmed Salman (أحمد سلمان), the guest, white turban" \
        --context "TV talk show 'Bellamara' ..." [--speaker 2] [--lead 20]
    python render.py work/plan_speaker.json --source source.mp4 --work work --out person.mp4

What it does and why (from the first real run):
1. Builds speaker turns from the word-level speaker labels.
2. --sheet grabs one frame from the middle of several long turns per speaker into a numbered
   contact sheet, so you can SEE who each speaker number is. Look at it.
3. Diarization merges similar voices (a co-host's lines came back labelled as the guest). So an
   LLM re-reads every turn with its neighbours and decides, per turn of the target's speaker
   number, whether it's really them (cues: who was just addressed by name, content, style),
   and groups the show into interaction blocks with short titles (used as chapters).
4. Segments = the target's real turns, merged across short interjections (<=15 s each, gaps
   <=15 s, so quick back-and-forths stay whole even when replies are 1 s long), each with the
   question/challenge that leads into it (its last --lead seconds). Long monologues by others
   are left out.
Writes work/speaker_turns.json, work/speaker_labels.json and work/plan_speaker.json.
Then: watch a few minutes where the LLM relabelled turns - that's where errors hide.
"""
import argparse, json, os, statistics, subprocess
from collections import defaultdict
from common import chat_json, load, save, ts, ffmpeg_path

ap = argparse.ArgumentParser()
ap.add_argument('work')
ap.add_argument('--who', default='', help='target person: name + anything that identifies them (role, look)')
ap.add_argument('--context', default='')
ap.add_argument('--speaker', type=int, default=None, help='speaker number of the target if you already know it')
ap.add_argument('--source', default=None)
ap.add_argument('--sheet', action='store_true', help='only make the who-is-who contact sheet (frames per speaker number) and exit')
ap.add_argument('--shots', action='store_true', help='only make the camera-shot sheet (work/shots.jpg) and exit')
ap.add_argument('--target-shots', default='', help='comma-separated shot numbers from shots.jpg that show the target')
ap.add_argument('--lead', type=float, default=20, help='seconds of the lead-in question to keep')
ap.add_argument('--model', default='google/gemini-3.5-flash')
a = ap.parse_args()

T = load(os.path.join(a.work, 'transcript.json'))
W = T['words']
if not W or len(W[0]) < 4:
    raise SystemExit('transcript.json has no speaker labels - run transcribe.py with --diarize')
turns = []
for s, e, t, spk in W:
    if turns and turns[-1]['spk'] == spk and s - turns[-1]['end'] < 2.0:
        turns[-1]['end'] = e; turns[-1]['words'].append(t)
    else:
        turns.append({'spk': spk, 'start': s, 'end': e, 'words': [t]})
save(turns, os.path.join(a.work, 'speaker_turns.json'))
talk = defaultdict(float)
for t in turns:
    talk[t['spk']] += t['end'] - t['start']
print('speaker  talk   turns  first')
for s in sorted(talk, key=lambda s: -talk[s]):
    n = sum(1 for t in turns if t['spk'] == s)
    print(f'  S{s}  {talk[s] / 60:5.1f}m  {n:4d}  {ts(next(t["start"] for t in turns if t["spk"] == s))}')

if a.sheet:
    from PIL import Image, ImageDraw
    from common import font
    if not a.source:
        raise SystemExit('--sheet needs --source')
    FF = ffmpeg_path(); spks = sorted(talk, key=lambda s: -talk[s]); rows = []
    for s in spks:
        long = sorted([t for t in turns if t['spk'] == s], key=lambda t: t['start'] - t['end'])[:5]
        rows.append((s, sorted(long, key=lambda t: t['start'])))
    w, h = 320, 180; sheet = Image.new('RGB', (5 * w, len(rows) * h)); d = ImageDraw.Draw(sheet)
    tmp = os.path.join(a.work, '_f.jpg')
    for r, (s, tl) in enumerate(rows):
        for c, t in enumerate(tl):
            subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{(t["start"] + t["end"]) / 2:.2f}', '-i', a.source, '-frames:v', '1', '-vf', f'scale={w}:{h}', tmp])
            sheet.paste(Image.open(tmp), (c * w, r * h))
            d.rectangle([c * w, r * h, c * w + 140, r * h + 24], fill='black')
            d.text((c * w + 4, r * h + 2), f'S{s} {ts(t["start"])}', fill='yellow', font=font('latin', 18))
    os.remove(tmp); out = os.path.join(a.work, 'speakers.jpg'); sheet.save(out)
    print(out, '- each row is one speaker number; frames come from the middle of their longest turns.')
    print('Cutaways happen, so judge by the majority of a row. Then run again with --who (and --speaker).')
    raise SystemExit



def shot_clusters():
    """Group frames sampled from every turn into camera shots (k-means on 32x18 thumbnails). Cached in
    work/shots.json. Diarization errors can't be fixed from statistics alone (a merged co-host's
    close-ups look 'tied to the target' too), so a person/agent looks at shots.jpg and names the
    shots that show the target."""
    import numpy as np
    cp = os.path.join(a.work, 'shots.json')
    if os.path.exists(cp):
        return load(cp)
    FF = ffmpeg_path(); X, meta = [], []
    for i, t in enumerate(turns):
        d = t['end'] - t['start']; n = 3 if d > 3 else 1
        for k in range(n):
            tt = t['start'] + d * (k + 0.5) / n
            raw = subprocess.run([FF, '-v', 'error', '-ss', f'{tt:.2f}', '-i', a.source, '-frames:v', '1', '-vf', 'scale=32:18',
                                  '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True).stdout
            if len(raw) == 32 * 18 * 3:
                X.append(np.frombuffer(raw, np.uint8).astype(float) / 255); meta.append((i, round(tt, 2)))
    X = np.stack(X); K = min(12, len(X)); rng = np.random.default_rng(0); c = X[rng.choice(len(X), K, replace=False)]
    for _ in range(40):
        lab = ((X[:, None] - c[None]) ** 2).sum(2).argmin(1)
        c = np.stack([X[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(K)])
    out = {'samples': [[i, t, int(l)] for (i, t), l in zip(meta, lab)]}
    save(out, cp); return out

if a.source and (a.shots or a.target_shots):
    SH = shot_clusters()
if a.shots:
    from PIL import Image, ImageDraw
    from common import font
    FF = ffmpeg_path(); by = defaultdict(list)
    for i, t, l in SH['samples']:
        by[l].append(t)
    ids = sorted(by, key=lambda l: -len(by[l])); w, h = 320, 180
    sheet = Image.new('RGB', (3 * w, len(ids) * h)); d = ImageDraw.Draw(sheet); tmp = os.path.join(a.work, '_f.jpg')
    for r, l in enumerate(ids):
        pick = [by[l][int(x)] for x in (len(by[l]) * 0.2, len(by[l]) * 0.5, len(by[l]) * 0.8)]
        for c_, t in enumerate(pick):
            subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', a.source, '-frames:v', '1', '-vf', f'scale={w}:{h}', tmp])
            sheet.paste(Image.open(tmp), (c_ * w, r * h))
        d.rectangle([0, r * h, 190, r * h + 26], fill='black'); d.text((4, r * h + 2), f'shot {l} ({len(by[l])} frames)', fill='yellow', font=font('latin', 18))
    os.remove(tmp); out = os.path.join(a.work, 'shots.jpg'); sheet.save(out)
    print(out, '- look at it, then pass --target-shots with the shot numbers that show the TARGET in close-up')
    raise SystemExit

if not a.who:
    raise SystemExit('give --who "name + description" (run with --sheet / --shots first to see who is who)')

def screen_hints(target):
    tshots = {int(x) for x in a.target_shots.split(',') if x.strip()}
    per = defaultdict(list)
    for i, t, l in SH['samples']:
        per[i].append(l)
    hints = {}
    for i, t in enumerate(turns):
        if t['spk'] != target or i not in per:
            continue
        ls = per[i]
        if any(l in tshots for l in ls):
            hints[i] = 'target on screen'
        elif len(ls) >= 3 and t['end'] - t['start'] > 6:
            hints[i] = 'target NOT on screen for the whole turn (someone else talking, or a cutaway)'
    return hints

guess = a.speaker if a.speaker is not None else sorted(talk, key=lambda s: -talk[s])[1]
hints = screen_hints(guess) if (a.source and a.target_shots) else {}
if hints:
    print(f'screen check for S{guess}: {sum("NOT" in h for h in hints.values())} long turns without the target on screen')
lines = [f"[{i}] S{t['spk']} {ts(t['start'])}-{ts(t['end'])}" + (f" ({hints[i]})" if i in hints else '') + f" {' '.join(t['words'])}"
         for i, t in enumerate(turns)]
hint = f'The target is probably speaker S{a.speaker}. ' if a.speaker is not None else ''
prompt = (f'Diarized transcript of a show. Context: {a.context or "talk show / interview"}.\nTarget person: {a.who}. {hint}'
          'Speaker numbers come from automatic diarization and can be wrong: similar voices get merged, so some turns '
          "under the target's number belong to someone else (e.g. a co-host). Each line: [turn] Sn start-end (optional screen "
          "hint from the video) text. 'target NOT on screen for the whole turn' on a long turn is evidence (not proof: "
          "shows cut to listeners) that someone else is talking - weigh it with who was just addressed.\n"
          'Tasks:\n1. target_speaker: the speaker number that is mostly the target.\n'
          '2. labels: for EVERY turn under that number, "target" or "other" (use who was just addressed by name, content, style, '
          'and continuity with neighbouring turns).\n'
          '3. blocks: interaction blocks with the target (the question/challenge that leads in, the target answering, short '
          'back-and-forth), in order, each with a 2-5 word title in the transcript language and a one-line English summary.\n'
          'Return ONLY JSON: {"target_speaker":int,"labels":{"<turn>":"target|other"},'
          '"blocks":[{"first_turn":int,"last_turn":int,"title":str,"summary_en":str}]}\n\n' + '\n'.join(lines))
R, cost = chat_json(a.model, prompt, temperature=0.2)
save(R, os.path.join(a.work, 'speaker_labels.json'))
tgt = a.speaker if a.speaker is not None else int(R['target_speaker'])
lab = R.get('labels', {})
is_t = [t['spk'] == tgt and lab.get(str(i), 'target') == 'target' for i, t in enumerate(turns)]
moved = [i for i, t in enumerate(turns) if t['spk'] == tgt and not is_t[i]]
print(f'\nLLM cost ${cost or 0:.3f}; target = S{tgt}; {len(moved)} of its turns relabelled as someone else:',
      ', '.join(ts(turns[i]['start']) for i in moved[:20]))

segs = []
for i, t in enumerate(turns):
    if not is_t[i]:
        continue
    between = range(segs[-1]['last'] + 1, i) if segs else []
    if segs and t['start'] - segs[-1]['end'] <= 15 and all(turns[j]['end'] - turns[j]['start'] <= 15 for j in between):
        segs[-1].update(end=t['end'], last=i); segs[-1]['talk'] += t['end'] - t['start']
    else:
        segs.append({'first': i, 'last': i, 'start': t['start'], 'end': t['end'], 'talk': t['end'] - t['start']})
for s in segs:                                   # lead-in question / challenge
    j = s['first'] - 1
    if j >= 0 and not is_t[j] and s['start'] - turns[j]['end'] < 4:
        s['start'] = max(turns[j]['start'], turns[j]['end'] - a.lead)
segs = [s for s in segs if s['talk'] >= 2.5]
merged = []
for s in segs:
    if merged and s['start'] - merged[-1]['end'] < 1.5:
        merged[-1].update(end=max(merged[-1]['end'], s['end']), last=s['last']); merged[-1]['talk'] += s['talk']
    else:
        merged.append(dict(s))
B = R.get('blocks', [])
def title(s):
    b = next((b for b in B if b['first_turn'] <= s['first'] <= b['last_turn'] or b['first_turn'] <= s['last'] <= b['last_turn']), None)
    if not b:   # not inside any block: use the latest block that starts before this segment
        prev = [b for b in B if b['first_turn'] <= s['first']]
        b = max(prev, key=lambda b: b['first_turn']) if prev else (B[0] if B else None)
    return b['title'] if b else ''
name = a.who.split('(')[0].split(',')[0].strip()
items = [{'type': 'card', 'dur': 3.4, 'lines': [{'text': name, 'role': 'title'}, {'text': '', 'role': 'subtitle'}]}]
cur, n = None, 0
for s in merged:
    t = title(s)
    if t and t != cur:
        cur = t; n += 1
        items.append({'type': 'card', 'dur': 1.9, 'chapter_start': t, 'lines': [{'text': str(n), 'role': 'number'}, {'text': t, 'role': 'chapter'}]})
    items.append({'type': 'clip', 'start': round(s['start'] - 0.12, 2), 'end': round(s['end'] + 0.3, 2), 'chapter': cur or ''})
items.append({'type': 'card', 'dur': 3.4, 'lines': [{'text': '', 'role': 'brand'}, {'text': '', 'role': 'cta'}]})
save({'mode': 'speaker', 'format': '16:9', 'music': None, 'music_mode': 'cards', 'items': items}, os.path.join(a.work, 'plan_speaker.json'))
tot = sum(s['end'] - s['start'] for s in merged); talk_t = sum(s['talk'] for s in merged)
print(f'\n{len(merged)} segments, {tot / 60:.1f} min ({talk_t / 60:.1f} min of the target speaking), {n} chapters')
for s in merged:
    print(f"  {ts(s['start'])}-{ts(s['end'])} ({s['end'] - s['start']:5.1f}s) {title(s)}")
print(f"-> {os.path.join(a.work, 'plan_speaker.json')}  (fill in the title card subtitle and end card text, "
      'set "music" if you want it on cards)')
