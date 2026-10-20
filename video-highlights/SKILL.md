---
name: video-highlights
description: Turn a long video (YouTube link, podcast, interview, talk show, livestream) into short edits - a dramatic trailer, a chaptered 5-minute TL;DR, vertical 9:16 Instagram/TikTok reels with word-by-word karaoke subtitles and a face-tracked crop, or a compilation of every moment one specific person speaks. Use this whenever someone wants to clip, recap, summarize, cut down, "make reels/shorts/a trailer/a TL;DR/the best parts", or "extract all of X's interventions" from a long video or podcast episode, in any language (works well for Arabic/Tunisian derja and other right-to-left scripts), even if they only paste a YouTube URL and say "make something from this".
compatibility: Needs an OpenRouter API key with a few dollars of credit (OPENROUTER_API_KEY), python3, curl, internet, ~2 GB free disk per episode. No Apify needed.
---

# Video highlights

Long video in, short edits out: **download -> transcribe with word timestamps -> an LLM
proposes moments -> you review cut points like an editor -> render -> look at the result.**
Each step is a script; your job is the judgement in between.

```bash
SK=<this skill's folder>/scripts          # e.g. ~/.claude/skills/video-highlights/scripts
PY=~/.cache/video-skills/venv/bin/python
FF=~/.cache/video-skills/bin/ffmpeg      # the same ffmpeg the scripts use
```
Run every script as `$PY $SK/<name>.py ...` from a project folder (scripts live in the skill
folder, outputs go wherever you run them).

## Requirements (check before starting)

| need | for | how | cost |
|---|---|---|---|
| **OpenRouter key** `OPENROUTER_API_KEY` | transcription (Scribe v2), moment picking (Gemini), music (Lyria) | openrouter.ai -> credits -> Settings -> Keys | ~$0.60 for a 90-min episode, trailer + TL;DR; $5 of credit is plenty |
| python3, curl, ~2 GB disk | scripts, 1080p source | preinstalled on macOS/Linux | free |

Not needed: Apify, a GPU, a system ffmpeg. If the key is missing, ask for it before any paid
step and say what it costs. A 403 "Key limit exceeded" means the key's spending limit is used
up: ask the user to raise it (finished steps are cached). Never write a key into a file, plan or
repo; if the user pastes one, use it inline (`export` in the command) and suggest rotating it later.

## 0. Setup (once per machine)
```bash
$PY -c "import cv2, arabic_reshaper, PIL" 2>/dev/null && [ -f ~/.cache/video-skills/models/yunet.onnx ] && echo ready || bash $SK/setup.sh
```
Don't run two setup.sh at once (parallel pip installs collide); if another agent is setting up, wait for the check above to pass.

## 1. Download
```bash
$PY $SK/download.py "<url>" --out source.mp4 --height 1080
```
1080p if any 9:16 reel is planned (a vertical crop keeps ~32% of the width); 720p is enough for
16:9 only. The script prints the resolution and fps it got: some videos only exist at 240-480p
(it warns) - say so up front, those reels are for testing the edit, not for publishing. ~2-4 min and 1.2-2 GB for 70-100 min. It prefers H.264 so the source previews in
QuickTime. Ignore the yt-dlp "No supported JavaScript runtime" warning.

## 2. Transcribe
```bash
$PY $SK/transcribe.py source.mp4 --out work --lang ar            # add --diarize for speaker labels
```
Scribe v2, **~$0.22 per hour**, word timestamps. 10-min chunks with a 4 s overlap (no lost words at
seams); changing settings clears the cache automatically. Output: `work/transcript.json` and
`work/transcript.txt` (`[idx] mm:ss.ss-mm:ss.ss text`; line N is sentence index N, 0-based).
What to expect: Scribe leans toward standard spelling. Derja is understood but often written more
formally, French words may come out in Latin letters, names are spelled roughly. **Check names
before putting them on cards.** The script lists mixed Arabic+Latin tokens (e.g. "الوسلati") - ASR
errors that render badly. Fix words with one command (keeps words and sentences in sync,
handles split/merged tokens, keeps a backup):
```bash
$PY $SK/fix_transcript.py work "الوسلati=الوسلاتي" "هالشالة بكا لوجي=هالشهادة البكالوريا"   # --at <sec> for one occurrence
$PY $SK/fix_transcript.py work "آآآ="                                  # empty right side deletes (fillers)
```

## 3. Pick moments
Look at the first lines of transcript.txt: shows often open with their own teaser of the best
lines (sometimes in several pieces, e.g. 0-75 s and again at 2-5 min). Set `--skip-start` to the
first block; the report also flags any clip line that is said twice (`LINE ALSO AT ...`) so you
can keep the later, original occurrence.
```bash
$PY $SK/pick_moments.py work --mode trailer --context "<show, host, guest, topic>" --skip-start 70 --must "topic A, topic B"
$PY $SK/pick_moments.py work --mode tldr --minutes 5 --context "..." --skip-start 70 --must "..."
$PY $SK/pick_moments.py work --mode reels --context "..." --skip-start 70     # standalone vertical reels
```
(The work folder is a positional argument here.) Gemini 3.5 Flash reads the whole transcript
(~$0.13-0.19) and writes `work/plan_<mode>.json` plus a **boundary report** with `!!` flags:
starts mid-thought, ends mid-sentence, ends on a question without the answer, duplicate
sentences (e.g. the cold open reappearing in a chapter), clips inside the teaser, mixed-script
tokens. Treat every flag as a decision to make, then also read the clips themselves:

- `--must` topics are requested, not guaranteed. If one is missing, grep transcript.txt and add it.
- A clip that ends on the interviewer's question: extend to include the answer.
- The interviewer's pushback ("now you're accusing", "show your proof") is what makes moments feel like a confrontation. Keep it.
- Trailer arc: hook (strongest line) -> title card -> setup -> escalating conflict -> mid card -> climax -> short sting -> end card, 75-90 s.
- TL;DR: 10-40 s clips so arguments make sense, 5-7 chapters, cold open not repeated later.
- Reels (`--mode reels`, preferred over splitting a TL;DR): 5-8 reels of 20-45 s, each one exchange that
  makes sense to a stranger, ending on the punch. A `hook` clip (a striking line from the middle of the
  reel, 2.5-6 s) plays first as a flash-forward when the reel doesn't already open on a question,
  accusation or verdict. In four test episodes the picker's draft always needed an editor: every reel
  was reworked to join a question to its answer, end on the punch instead of a filler or rhetorical
  question, and fix hooks that were 1 s long or gave the ending away (the report flags these).
  Check each reel's first 2 seconds and last sentence: those decide watch time.

Edit the plan JSON directly: `start_idx`/`end_idx`, `start_time`/`end_time` (absolute seconds, to
trim inside the first/last sentence, e.g. drop a leading «ثم» or a trailing «سامحني»), card `lines`, `chapter`. Clips can also be absolute: `{"type":"clip","start":812.4,"end":840.1}`.
For a long edit, show the user the storyline (one line per clip, translated) before rendering.

## 4. Music (optional)
```bash
$PY $SK/music.py "90-second dark tense documentary trailer score, pulsing bass, impact hits, builds to a climax, final boom" --out work/music.mp3
```
Lyria 3 Pro, ~$0.08 (printed). The file must sit next to the plan (`"music": "music.mp3"` is
relative to the plan's folder). Trailers: `music_mode: "bed"` (low under dialogue, loud on cards;
the track's last *audible* moment is aligned with the end, so the end card has music). TL;DRs:
`"cards"` (music only on title cards). `"music": null` to skip. Ask for a track at least as long as
the edit; a shorter one is looped (with a warning).

## 5. Render
```bash
$PY $SK/render.py work/plan_trailer.json --source source.mp4 --work work --out trailer.mp4

# 9:16: plan the crop, verify, then render + split per chapter (one reel each)
$PY $SK/facetrack.py work/plan_tldr.json --source source.mp4 --work work --verify
$PY $SK/render.py work/plan_tldr.json --source source.mp4 --work work --format 9:16 \
    --brand "<guest> on <show>" --out reels/tldr_vertical.mp4 --split-chapters reels/
```
facetrack finds every camera cut frame-exactly and gives each shot one crop, then groups shots by
**camera angle** so the same camera gets the same crop in every clip. When an angle was cropped at
different places (typically a wide two-shot where the detector missed a face in profile at the
frame edge), it prints `ANGLE n: ... cropped at k different places` and saves `work/angle_n.jpg`
with the candidate crops drawn. **Look at it** and re-run with `--angle-x n=<x>` (face-centre x
of the person to follow; usually the guest). Choosing to follow whoever is speaking in a wide shot
is a valid editorial choice, but verify will then list those frames, which is expected.
`--angle-x` can be repeated (`--angle-x 2=420 --angle-x 3=447`).

Faces are found with YuNet (OpenCV's small neural detector, installed by setup.sh): on a TV set with
glasses and a mic in front of the face it found the face in every frame where Haar cascades found a
third, and it ignores logos, headphones and wall lettering that Haar took for faces. Dissolves and
zooms are split into separate shots (`DISSOLVE/ZOOM` in the log). faces.json is re-planned when
`--track`/`--prefer` change; `--fresh` forces it (hand edits in faces.json survive plain re-runs).

**Moving faces**: when the one person in a shot moves across the frame (handheld or zooming camera,
a guest leaning in and out), facetrack prints `TRACKING ...` and that shot gets a crop that follows
the face like a lazy camera operator (no jitter; fixed studio cameras stay fixed). It reports how
many sampled frames still have the face near the crop edge; look at those. `--track on|off` forces it.

**Burned-in subtitles** in the source: add `"keep_top": 0.83` to the plan (or to one clip). The 9:16
crop then zooms to the top 83% of the frame, cutting off the caption band (a bit softer: ~2x upscale
from 1080p). `--verify`
must print **0 mismatches** otherwise, and its second line (face outside the middle 70% of the
crop) should stay under ~3%; it checks every frame through the exact crop expression the
renderer uses (camera count is automatic). Instagram reels
max out at 3 min, so long TL;DRs ship as the full vertical file plus one reel per chapter. For a
reels plan, the same render command with `--split-chapters reels/` writes one file per reel.

**Laptop heat**: on a Mac the encode and the source decode run on the media engine
(`h264_videotoolbox`, ~8x less CPU than libx264 at the same speed and visually equal quality), so
a render of 8 reels takes ~1 min without maxing the CPU. Face detection is the remaining CPU work
(~1-2 min per episode). Run at most 2 episodes at the same time; four in parallel kept every core
busy for half an hour. `VIDEO_ENCODER=libx264` forces the software encoder.

## 6. Look before you hand it over
Logs aren't proof. Extract frames and look at them:
```bash
for t in 2 10 30 60; do $FF -v error -y -ss $t -i trailer.mp4 -frames:v 1 -vf scale=480:-2 f$t.jpg; done
# a strip of one segment, every 45th frame:
$FF -v error -y -i work/seg_9x16/018.mp4 -vf "select='not(mod(n\,45))',scale=216:384,tile=8x1" -frames:v 1 -fps_mode passthrough strip.jpg
```
Check: subtitles render (no empty boxes, RTL text joined and in order); the yellow word matches the
speech (compare with `transcript.json` word times, measuring durations from the real per-clip files
in `work/seg_*/NNN.mp4`, which are a few hundredths longer than planned); cards readable; music
present on cards/end card (`$FF -i out.mp4 -af volumedetect -f null -`). For 9:16, pull frames **by index
right after cuts from the per-clip files** in `work/seg_9x16/` (times on the joined file drift by a
few frames). Segments are 30 fps: for a 25 fps source, source frame n is segment frame n*1.2. Watch for **subtitles burned into the source** (shows often caption the moments they reuse in
their teaser): ours would stack on top of them. Pick another clip or another occurrence. You can't
hear audio, so tell the user to listen for clipped words and music level.

Report: files and durations, the storyline, plan changes you made, cost per step, what you
verified and what you couldn't. Mention rights: clips of someone else's show are fine as a private
test or pitch; publishing needs the owner's permission.

## Mode: every moment of one person
"Extract all of X's interventions/interactions" needs speaker labels, and diarization alone
isn't enough: it merges similar voices (a co-host came back labelled as the guest).
```bash
$PY $SK/transcribe.py source.mp4 --out work --lang ar --diarize     # one request up to 60 min keeps labels consistent
$PY $SK/extract_speaker.py work --source source.mp4 --sheet         # work/speakers.jpg: frames per speaker number
$PY $SK/extract_speaker.py work --source source.mp4 --shots         # work/shots.jpg: numbered camera shots
#   -> LOOK at both images: which speaker number is X, which shot numbers show X's close-up
$PY $SK/extract_speaker.py work --source source.mp4 --speaker 2 --target-shots 2,10 \
    --who "Name (الاسم), role, how they look" --context "<show, other people>"
$PY $SK/render.py work/plan_speaker.json --source source.mp4 --work work --out x_compilation.mp4
```
The LLM re-labels each of X's turns using who was just addressed, content, and the screen hint
(long turns where none of X's shots is on screen), and groups chapters. The compilation keeps X's
turns, the question leading into each (last 20 s), and short back-and-forths; long monologues by
others are left out. Fill in the title/end card text in plan_speaker.json. **Watch the
stretches where turns were relabelled** (printed) - that's where mistakes hide. ~$0.30 for 45 min.

## Costs seen in practice
| step | tool | cost |
|---|---|---|
| download | yt-dlp | free |
| transcript | Scribe v2 | ~$0.22/hour (+ diarization: same) |
| moment picking / speaker relabel | Gemini 3.5 Flash | ~$0.13-0.19 per run |
| music | Lyria 3 Pro | ~$0.08 |
| render, face crop | local | free |

Read `references/lessons.md` when something looks wrong. It lists every bug hit so far (font boxes,
crop flashes, wide shots, music tails, diarization merges) and the fix.
