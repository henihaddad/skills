#!/usr/bin/env python3
"""Ask an LLM (via OpenRouter) to pick the moments for an edit, and write an editable plan.json.

    python pick_moments.py work/ --mode trailer --context "Podcast 'X', host A interviews B about ..."
    python pick_moments.py work/ --mode tldr --minutes 5 --context "..."

--mode trailer : 10-14 punchy moments (2-10 s each), hook -> conflict -> climax -> sting, ~75-90 s.
--mode tldr    : 5-7 chronological chapters, clips 10-40 s, a viewer understands the whole story.

The model only proposes. Always review the printed boundary report: every clip should start and
end on a complete thought, and a host question must not end a clip without its answer
(extend end_idx in plan.json when it does). Gemini Flash reads ~80 min of transcript for ~$0.18.
"""
import argparse, json, os
from common import chat_json, load, save

ap = argparse.ArgumentParser()
ap.add_argument('work')
ap.add_argument('--mode', choices=['trailer', 'tldr'], required=True)
ap.add_argument('--context', default='', help='who is speaking, show name, what the episode is about')
ap.add_argument('--minutes', type=float, default=5, help='tldr target length')
ap.add_argument('--skip-start', type=float, default=120, help='seconds of the show\'s own teaser/intro to avoid (check transcript.txt: often 60-120 s)')
ap.add_argument('--must', default='', help='comma-separated topics the edit must cover, e.g. "Karbala, Shiism is not an accusation"')
ap.add_argument('--model', default='google/gemini-3.5-flash')
ap.add_argument('--out', default=None)
a = ap.parse_args()

T = load(os.path.join(a.work, 'transcript.json')); S = T['sents']
tx = open(os.path.join(a.work, 'transcript.txt'), encoding='utf-8').read()
lang_rule = ('Write all on-screen titles in the same language and script as the transcript. '
             'Keep them short (2-4 words).')

if a.mode == 'trailer':
    task = (f'Pick 10-14 moments for a 75-90 second dramatic trailer. Skip the first {a.skip_start:.0f} seconds '
            '(shows often open with their own teaser; prefer the original occurrence later). Each moment: 1-4 consecutive '
            'sentences, 2-10 seconds, self-contained and punchy: oaths, accusations, pushback from the interviewer, '
            'emotional or surprising lines. Order them for a trailer arc: hook (strongest line) -> setup -> conflict -> '
            'climax -> a short sting that leaves suspense. Also give a title card (name of the guest/topic + a 2-4 word '
            'tagline), one mid card before the climax (e.g. "...and the confrontation"), and an end card (show name + call to action). '
            'Return JSON: {"title":{"main":str,"tagline":str},"mid_card":str,"end_card":{"brand":str,"cta":str},'
            '"moments":[{"start_idx":int,"end_idx":int,"start_quote":str,"end_quote":str,"role":"hook|setup|conflict|climax|sting","english":str}]}')
else:
    lo, hi = a.minutes * 60 * 0.9, a.minutes * 60
    task = (f'Make a {a.minutes:g}-minute TL;DR: someone who watches only this understands the key topics, the main claims and '
            f'answers, and sees the most intense exchanges. Skip the first {a.skip_start:.0f} seconds and greetings. 5-7 chapters '
            'in chronological order, each with a short title and 1-4 clips. Each clip: consecutive sentence indices, 10-40 s, '
            "starting and ending on complete thoughts; include the interviewer's question when it gives context. "
            f'Total speech {lo:.0f}-{hi:.0f} s. Also pick ONE cold-open line (2-10 s, the strongest single moment) and give a '
            'title card and end card. Return JSON: {"cold_open":{"start_idx":int,"end_idx":int},'
            '"title":{"main":str,"tagline":str,"small":str},"end_card":{"brand":str,"cta":str},'
            '"chapters":[{"title":str,"title_en":str,"clips":[{"start_idx":int,"end_idx":int,"start_quote":str,"end_quote":str,"summary_en":str}]}]}')

must = [m.strip() for m in a.must.split(',') if m.strip()]
must_rule = (f'The edit MUST include at least one strong moment about each of these topics: {"; ".join(must)}. ' if must else '')
quote_rule = ('For every clip also copy start_quote = the first 6-8 words of sentence start_idx and end_quote = the last '
              '6-8 words of sentence end_idx, exactly as written in the transcript (they are used to verify the indices). ')
prompt = (f'You are a senior video editor. Context: {a.context or "an interview/podcast"}.\n'
          'Transcript lines are "[index] start-end text" (index = sentence number).\n'
          f'{task}\n{must_rule}Never use the same sentence twice (the cold open must not reappear inside a chapter clip). '
          'Clips must start at the beginning of a sentence/thought (not on a conjunction such as و/ثم/أن/مع/and/but) '
          f'and end on a finished sentence. {quote_rule}\n{lang_rule}\nReturn ONLY the JSON object.\n\nTRANSCRIPT:\n{tx}')
picks, cost = chat_json(a.model, prompt)
save(picks, os.path.join(a.work, f'picks_{a.mode}.json'))

# --- re-anchor indices with the quotes: models misread sentence numbers (a note about "being
# dismissed over French" pointed at a sentence saying «لا لا شوف»; the real line was 380 sentences later)
import re as _re
def _toks(t):
    return _re.sub(r'[^\w ]', ' ', _re.sub('[\u064b-\u0652]', '', t)).split()
def _score(q, k, tail=False):
    qt, st = _toks(q), _toks(S[k][2])
    if not qt or not st:
        return 0
    st = st[-len(qt) - 2:] if tail else st[:len(qt) + 2]
    return sum(1 for w in qt if w in st) / len(qt)
def anchor(c, label):
    i, j = int(c['start_idx']), int(c['end_idx'])
    if c.get('start_quote'):
        if _score(c['start_quote'], i) < 0.6:
            best = max(range(len(S)), key=lambda k: (_score(c['start_quote'], k), -abs(k - i)))
            if _score(c['start_quote'], best) >= 0.6:
                print(f'  re-anchored {label}: start {i} -> {best} (quote "{c["start_quote"][:40]}")'); j += best - i; i = best
            else:
                print(f'  !! {label}: start_quote not found anywhere - check this clip by hand'); c['unverified'] = True
    if c.get('end_quote'):
        cand = [k for k in range(i, min(len(S), i + 40))]
        if cand and _score(c['end_quote'], j, True) < 0.6:
            best = max(cand, key=lambda k: (_score(c['end_quote'], k, True), -abs(k - j)))
            if _score(c['end_quote'], best, True) >= 0.6:
                print(f'  re-anchored {label}: end {j} -> {best}'); j = best
    c['start_idx'], c['end_idx'] = i, max(i, j)
if a.mode == 'trailer':
    for n_, m_ in enumerate(picks.get('moments', [])):
        anchor(m_, f'moment {n_ + 1}')
else:
    anchor(picks['cold_open'], 'cold open')
    for ch_ in picks.get('chapters', []):
        for n_, c_ in enumerate(ch_['clips']):
            anchor(c_, f'{ch_["title"]} #{n_ + 1}')
print(f'model cost ${cost or 0:.3f}')

def clip(i, j, **kw):
    return {'type': 'clip', 'start_idx': int(i), 'end_idx': int(j), **kw}

def card(lines, dur):
    return {'type': 'card', 'lines': lines, 'dur': dur}

items = []
if a.mode == 'trailer':
    ms = picks['moments']
    t = picks.get('title', {}); e = picks.get('end_card', {})
    for k, m in enumerate(ms):
        items.append(clip(m['start_idx'], m['end_idx'], note=m.get('english', ''), role=m.get('role', '')))
        if k == 0:
            items.append(card([{'text': t.get('main', ''), 'role': 'title'}, {'text': t.get('tagline', ''), 'role': 'subtitle'}], 2.6))
        if m.get('role') == 'climax' and picks.get('mid_card') and not any(i.get('mid') for i in items):
            items.insert(len(items) - 1, {**card([{'text': picks['mid_card'], 'role': 'subtitle'}], 1.6), 'mid': True})
    if picks.get('mid_card') and not any(i.get('mid') for i in items) and len(ms) > 4:
        # no moment tagged "climax": put the mid card before the last third of the trailer
        cut = [k for k, i in enumerate(items) if i['type'] == 'clip'][-max(2, len(ms) // 3)]
        items.insert(cut, {**card([{'text': picks['mid_card'], 'role': 'subtitle'}], 1.6), 'mid': True})
    items.append(card([{'text': e.get('brand', ''), 'role': 'brand'}, {'text': e.get('cta', ''), 'role': 'cta'}], 3.6))
    plan = {'mode': 'trailer', 'format': '16:9', 'music': 'music.mp3', 'music_mode': 'bed', 'items': items}
else:
    co = picks['cold_open']; t = picks.get('title', {}); e = picks.get('end_card', {})
    items.append(clip(co['start_idx'], co['end_idx'], note='cold open'))
    items.append(card([{'text': t.get('main', ''), 'role': 'title'}, {'text': t.get('tagline', ''), 'role': 'subtitle'},
                       {'text': t.get('small', ''), 'role': 'small'}], 3.2))
    for n, ch in enumerate(picks['chapters'], 1):
        items.append(card([{'text': str(n), 'role': 'number'}, {'text': ch['title'], 'role': 'chapter'}], 1.9) | {'chapter_start': ch['title']})
        for c in ch['clips']:
            items.append(clip(c['start_idx'], c['end_idx'], chapter=ch['title'], note=c.get('summary_en', '')))
    items.append(card([{'text': e.get('brand', ''), 'role': 'brand'}, {'text': e.get('cta', ''), 'role': 'cta'}], 3.6))
    plan = {'mode': 'tldr', 'format': '16:9', 'music': 'music.mp3', 'music_mode': 'cards', 'items': items}

out = a.out or os.path.join(a.work, f'plan_{a.mode}.json')
save(plan, out)

# boundary report: the part you must eyeball. Flags are heuristics - read the text too.
import re
from common import ts, is_mixed
END_P = re.compile(r'[.!?؟。…]["»”]?$')
CONJ = re.compile(r'^(و|ف|ثم|أن|ان|إن|مع|لكن|بل|أو|او|and|but|so|or|that|then)\b', re.I)
def _norm(t):
    return re.sub(r'[^\w ]', '', re.sub('[\u064b-\u0652]', '', t)).split()
_grams = {}
for _k, _s in enumerate(S):
    _w = _norm(_s[2])
    for _g in zip(_w, _w[1:], _w[2:], _w[3:], _w[4:]):
        _grams.setdefault(_g, set()).add(_k)
def dup_of(x):
    w = _norm(S[x][2])
    for g in zip(w, w[1:], w[2:], w[3:], w[4:]):
        others = [k for k in _grams.get(g, ()) if abs(k - x) > 3]
        if others:
            return min(others, key=lambda k: abs(S[k][0] - S[x][0]))
    return None
total, used = 0, {}
for k, it in enumerate(items):
    if it['type'] != 'clip':
        print(f"\n== CARD {' / '.join(l['text'] for l in it['lines'] if l['text'])}"); continue
    i, j = it['start_idx'], it['end_idx']; d = S[j][1] - S[i][0]; total += d
    flags = []
    if i > 0 and not END_P.search(S[i - 1][2]) or CONJ.match(S[i][2]):
        flags.append('STARTS MID-THOUGHT? (previous sentence unfinished or starts with a conjunction) -> try start_idx-1')
    if not END_P.search(S[j][2]):
        flags.append('ENDS MID-SENTENCE? -> try end_idx+1')
    if S[j][2].rstrip().endswith(('?', '؟')):
        flags.append('ENDS ON A QUESTION -> include the answer (end_idx+1..)')
    for x in range(i, j + 1):
        if x in used:
            flags.append(f'DUPLICATE: sentence {x} is also in item {used[x]}')
            break
    for x in range(i, j + 1):
        used.setdefault(x, k)
    for x in range(i, j + 1):                      # same line said twice: one is usually the show's teaser
        twin = dup_of(x)
        if twin is not None:
            flags.append(f"LINE ALSO AT {ts(S[twin][0])} (sentence {twin}) - one copy is probably the teaser; use the later, original one")
            break
    if a.skip_start and S[i][0] < a.skip_start:
        flags.append("INSIDE THE SHOW'S TEASER -> use the original occurrence later in the episode")
    bad = [w[2] for w in T['words'] if S[i][0] - 0.01 <= w[0] <= S[j][1] and is_mixed(w[2])]
    if bad:
        flags.append(f'MIXED-SCRIPT TOKENS {bad} -> fix the spelling in transcript.json')
    print(f"\n[{i}-{j}] {ts(S[i][0])}-{ts(S[j][1])} ({d:.0f}s) {it.get('note', '')}")
    print(f"   START: {S[i][2][:120]}")
    print(f"   END:   ...{S[j][2][-120:]}")
    if j + 1 < len(S) and (flags and any(f.startswith(('ENDS', )) for f in flags)):
        print(f"   NEXT:  {S[j + 1][2][:100]}")
    for f in flags:
        print(f'   !! {f}')
if must:
    print(f"\nRequired topics: {', '.join(must)} - confirm each appears (grep transcript.txt if the picks missed one).")
short = [it for it in items if it['type'] == 'clip' and S[it['end_idx']][1] - S[it['start_idx']][0] < (8 if a.mode == 'tldr' else 2)]
if short:
    print(f'\n!! {len(short)} clip(s) are very short for a {a.mode} (e.g. [{short[0]["start_idx"]}-{short[0]["end_idx"]}]) - extend or replace them')
if a.mode == 'tldr' and total < a.minutes * 60 * 0.8:
    print(f'\n!! only {total:.0f}s of speech for a {a.minutes:g}-minute target - add or extend clips')
print(f'\nspeech total {total:.0f}s -> {out}')
