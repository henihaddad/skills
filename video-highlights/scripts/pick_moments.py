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
ap.add_argument('--skip-start', type=float, default=120, help='seconds of built-in teaser/intro to avoid')
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
            '"moments":[{"start_idx":int,"end_idx":int,"role":"hook|setup|conflict|climax|sting","english":str}]}')
else:
    lo, hi = a.minutes * 60 * 0.9, a.minutes * 60
    task = (f'Make a {a.minutes:g}-minute TL;DR: someone who watches only this understands the key topics, the main claims and '
            f'answers, and sees the most intense exchanges. Skip the first {a.skip_start:.0f} seconds and greetings. 5-7 chapters '
            'in chronological order, each with a short title and 1-4 clips. Each clip: consecutive sentence indices, 10-40 s, '
            "starting and ending on complete thoughts; include the interviewer's question when it gives context. "
            f'Total speech {lo:.0f}-{hi:.0f} s. Also pick ONE cold-open line (2-10 s, the strongest single moment) and give a '
            'title card and end card. Return JSON: {"cold_open":{"start_idx":int,"end_idx":int},'
            '"title":{"main":str,"tagline":str,"small":str},"end_card":{"brand":str,"cta":str},'
            '"chapters":[{"title":str,"title_en":str,"clips":[{"start_idx":int,"end_idx":int,"summary_en":str}]}]}')

prompt = (f'You are a senior video editor. Context: {a.context or "an interview/podcast"}.\n'
          'Transcript lines are "[index] mm:ss.ss-ss.ss text" (index = sentence number).\n'
          f'{task}\n{lang_rule}\nReturn ONLY the JSON object.\n\nTRANSCRIPT:\n{tx}')
picks, cost = chat_json(a.model, prompt)
save(picks, os.path.join(a.work, f'picks_{a.mode}.json'))
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

# boundary report: the part you must eyeball
total = 0
for it in items:
    if it['type'] != 'clip':
        print(f"\n== CARD {' / '.join(l['text'] for l in it['lines'] if l['text'])}"); continue
    i, j = it['start_idx'], it['end_idx']; d = S[j][1] - S[i][0]; total += d
    print(f"\n[{i}-{j}] {int(S[i][0] // 60):02d}:{S[i][0] % 60:04.1f} ({d:.0f}s) {it.get('note', '')}")
    print(f"   START: {S[i][2][:120]}")
    print(f"   END:   ...{S[j][2][-120:]}")
    if j + 1 < len(S):
        print(f"   NEXT:  {S[j + 1][2][:100]}   <- if END is a question and NEXT answers it, extend end_idx")
print(f'\nspeech total {total:.0f}s -> {out}')
