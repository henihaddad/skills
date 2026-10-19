---
name: video-highlights
description: Turn a long video (YouTube link, podcast, interview, talk, livestream) into short highlight edits - a dramatic trailer, a chaptered 5-minute TL;DR, or vertical 9:16 Instagram/TikTok reels with word-by-word karaoke subtitles and a face-tracked crop. Use this whenever someone wants to clip, recap, summarize, cut down, or "make reels/shorts/a trailer/a TL;DR/the best parts" from a long video or podcast episode, in any language (works well for Arabic/Tunisian derja and other right-to-left scripts), even if they only paste a YouTube URL and say "make something from this".
compatibility: Needs an OpenRouter API key with a few dollars of credit (OPENROUTER_API_KEY), python3, curl, internet. No Apify needed.
---

# Video highlights

Long video in, short edits out. The pipeline is: **download -> transcribe with word timestamps
-> let an LLM propose moments -> you check the cut points -> render**. Every step is a script in
`scripts/`; your job is to run them, review the picks like an editor, and check the output.

## Requirements (check these before starting)

| need | what for | how to get it | cost |
|---|---|---|---|
| **OpenRouter account + API key** -> `OPENROUTER_API_KEY` | transcription (Scribe v2), moment picking (Gemini), music (Lyria) | sign up at openrouter.ai, add credits, create a key under Settings -> Keys | ~$0.40 for an 80-min episode; $5 of credit is plenty |
| python3 + curl | scripts, setup | preinstalled on macOS/Linux | free |
| internet access | YouTube download, API calls | | |

**Not needed**: Apify (yt-dlp downloads for free and is much faster), a GPU, or a system
ffmpeg (setup.sh installs a bundled one).

If `OPENROUTER_API_KEY` isn't set, ask the user for it before doing anything paid. Explain
that it's a pay-as-you-go key and that a spending limit on the key is a good safety net. If a
call fails with 403 "Key limit exceeded", the key's limit is used up: ask the user to raise it
(the key itself still works). Everything else (download, render, face crop) runs locally and free.

Never write a key into a file, plan, or repo. If the user pastes one, use it via `export` in
the command only, and suggest rotating it afterwards since it's now in the chat history.

## 0. Setup (once per machine)

```bash
bash scripts/setup.sh        # venv with pillow/numpy/opencv/arabic-reshaper + checksum-verified yt-dlp
PY=~/.cache/video-skills/venv/bin/python
```

Run every script below with `$PY scripts/<name>.py` from a working folder for the project.

## 1. Download

```bash
$PY scripts/download.py "<url>" --out source.mp4 --height 1080
```

Use 1080p if reels (9:16) are in scope; a vertical crop keeps only ~32% of the width. yt-dlp
is free and takes ~1 minute for an 80-minute episode. Apify-style paid downloaders are slower
and charge per MB; only use one if the user insists.

## 2. Transcribe

```bash
$PY scripts/transcribe.py source.mp4 --out work --lang ar     # omit --lang to auto-detect
```

ElevenLabs Scribe v2 via OpenRouter: ~$0.11 per hour, word-level timestamps, handles
dialect and code-switching. Produces `work/transcript.json` (words + sentences) and
`work/transcript.txt` (`[idx] mm:ss.ss-ss.ss text`). Sentence indices are how plans refer to clips.

## 3. Pick moments

Give a one-line `--context` (show, host, guest, topic): it makes titles and picks much better.

```bash
$PY scripts/pick_moments.py work --mode trailer --context "..."   # ~75-90 s, 10-14 punchy moments
$PY scripts/pick_moments.py work --mode tldr --minutes 5 --context "..."   # chapters, 10-40 s clips
```

Gemini 3.5 Flash reads the whole transcript (~$0.15 for 80 min) and writes
`work/plan_<mode>.json` plus a **boundary report**. Read that report yourself - this is the
editorial step the model gets wrong most often:

- A clip that ends on the interviewer's question (`لماذا؟`, "why?") without the answer: extend `end_idx`.
- A clip that starts mid-thought: move `start_idx` back one sentence.
- The episode's own teaser in the first ~2 minutes repeats the best lines; prefer the original later occurrence.
- For a trailer, the hook (first clip) should be the single strongest line; end on a short sting.

Edit the plan JSON directly (`start_idx`, `end_idx`, card `lines`, `chapter`); `end_time`
(absolute seconds) trims a clip mid-sentence when needed. Show the user the storyline
(one line per clip, translated if the content isn't in their language) before rendering a long edit.

## 4. Music (optional)

```bash
$PY scripts/music.py "90-second dark tense documentary trailer score, pulsing bass, impact hits, builds to a climax, final boom" --out music.mp3
```

Lyria 3 Pro, ~$0.08. Trailers use `music_mode: "bed"` (low under dialogue, loud on cards,
ending aligned to the end card). Long TL;DRs read better with `"cards"` (music only on title
cards, clean dialogue). Set `"music": null` to skip.

## 5. Render

```bash
# 16:9 trailer or TL;DR
$PY scripts/render.py work/plan_trailer.json --source source.mp4 --work work --out trailer.mp4

# 9:16 reels: plan the crop first, verify it, then render + split per chapter
$PY scripts/facetrack.py work/plan_tldr.json --source source.mp4 --work work --verify
$PY scripts/render.py work/plan_tldr.json --source source.mp4 --work work --format 9:16 \
    --brand "<guest> on <show>" --out tldr_vertical.mp4 --split-chapters reels/
```

`facetrack.py --verify` must print **0 mismatches**. It checks every frame through the exact
crop expression the renderer uses. If it doesn't, read `references/lessons.md` (face crop section).

Instagram reels max out at 3 minutes, so a 5-minute TL;DR goes out as the full vertical file
(for TikTok/Shorts) **plus** one reel per chapter.

## 6. Check before you hand it over

Don't claim it's done from logs alone. Extract a handful of frames and look at them:

```bash
FF=~/.cache/video-skills/bin/ffmpeg
for t in 2 10 30 60; do $FF -v error -y -ss $t -i trailer.mp4 -frames:v 1 -vf scale=480:-2 f$t.jpg; done
```

Check: subtitles render (no empty boxes, RTL text joined and in the right order), the
highlighted word matches speech (compare a frame's time with `transcript.json` words), and in
9:16 the speaker's face is centred, especially in frames right after camera cuts. You can't
hear the audio, so tell the user to listen for clipped words and music level.

Report: file paths, durations, the storyline, cost per step, and anything you couldn't verify.
Mention rights: clips of someone else's show are fine as a private test or pitch, but publishing
needs the owner's permission.

## Costs seen in practice (80-minute episode)

| step | tool | cost |
|---|---|---|
| download | yt-dlp | free |
| transcript | Scribe v2 | ~$0.15 |
| moment picking | Gemini 3.5 Flash | ~$0.15-0.18 per mode |
| music | Lyria 3 Pro | ~$0.08 |
| render, face crop | local ffmpeg/OpenCV | free |

## Variations users ask for

- **"Make the subtitles nicer"** - karaoke is the default; tweak colours/size in `render.py` (`SUB_SIZE`, `hl` colour in `common.draw_words`).
- **Shorter reels** - drop clips from a chapter in the plan, or `--mode trailer` and render 9:16.
- **English subtitles under Arabic** - translate sentence text with a chat model and add a second overlay line; keep the karaoke line on top.

Read `references/lessons.md` when something looks wrong. It lists every bug hit while building
this (font boxes, off-by-one crop flashes, timeouts, music silently missing) with the fix.
