# Lessons learned (read when something looks off)

Each item is a real problem hit while making these edits, with the cause and the fix that's
already in the scripts. If you change the scripts, don't reintroduce these.

## Downloading
- **pip yt-dlp on Python 3.9 is stale** and fails with "The page needs to be reloaded". Use the
  official standalone binary (setup.sh fetches it and checks its SHA-256). Re-run setup.sh if
  YouTube breaks it again; the binary is refreshed when older than 14 days.
- yt-dlp warns about a missing JS runtime; downloads still work. Ignore the warning.
- Paid downloaders (Apify `streamers/youtube-video-downloader`) ran at ~0.3 MB/s and bill per
  MB. 720p of an 80-min video would exceed a $5 free tier. yt-dlp did it in under a minute.

## Transcription
- Send audio as base64 `input_audio` JSON in chunks of ~10 minutes; one big request times out.
- Scribe occasionally emits stray Cyrillic/CJK characters inside Arabic words. `clean_token`
  strips them, and tokens that become empty are dropped from subtitles.

## Subtitles / fonts
- PIL can't shape Arabic without libraqm. Use arabic-reshaper + python-bidi **per word**, then
  lay the words out right-to-left yourself. That's also what makes per-word highlight possible.
- **Empty boxes**: Arabic fonts (Geeza Pro) have no Latin letters and no `! ? , :` glyphs.
  Latin words (French/English in derja: "distance", "fridge") need a Latin font; punctuation
  maps to Arabic forms (؟ ،) or is dropped. Both handled in `common.py`.
- Karaoke timing: each word stays highlighted until the next word starts. Long silences keep
  the previous word lit. Overlapping speakers can make it look slightly early/late.

## Face-tracked 9:16 crop (the hard part)
1. **Smoothing lag**: sampling faces every 0.25 s + median smoothing made the crop switch up to
   ~0.8 s after a camera cut -> the viewer sees the mic and candles. Fix: detect cuts, use one
   fixed crop per shot.
2. **Edge cuts**: ignoring cuts within 0.15 s of a clip's start/end left the last ~100 ms of a
   clip on the wrong person. Fix: keep every cut.
3. **Off-by-one flash**: decoding to `-f rawvideo` without `-fps_mode passthrough` duplicates
   the first frame (CFR padding), so every analysed frame index is +1 vs the crop filter's `n`.
   The crop switched one frame late -> 1-2 frame flash of the wrong side. Fix: passthrough in
   every analysis decode, and the crop must be the first filter so `n` counts source frames.
4. **Mic detected as a face**: ignore detections whose centre is in the lower ~45% of the frame.
5. **Verifying**: per-frame face detection is too noisy (gestures, blur) to validate with.
   Classify frames by camera angle instead (k-means on 32x18 thumbnails) and check the crop
   side through the real crop expression. `facetrack.py --verify` does this; expect 0 mismatches.
   A naive pixel comparison of rendered output vs source fails because of the grade/vignette.
- OpenCV 5 removed `CascadeClassifier`; setup.sh pins `opencv-python-headless<5`.

## Music
- Lyria via chat completions returns audio **only** with `modalities: ["text","audio"]` and
  `stream: true`. Without them you're billed (~$0.08) and get placeholder text.
- Lyria Clip is ~30 s; use Pro for anything longer.
- When cycling through the track for many title cards, keep the seek position inside the track
  (seeking past the end makes ffmpeg fail).

## Found by test runs on new episodes (Oct 2026)
- **Real costs**: Scribe v2 is ~$0.22/hour, not $0.11. Downloads at 1080p took 3-4 min for 70-100 min (HLS, ~1,000 fragments), 1.2-2 GB.
- **Chunk seams**: hard 10-min cuts split sentences and dropped a word at 10:00. Chunks now overlap
  by 4 s and each word is kept by the chunk that owns its start time. Changing `--chunk` used to
  silently reuse old chunks with wrong offsets; a meta file now clears the cache.
- **transcript.txt end times** used to be seconds-mod-60 (`00:57.40-04.94`); both ends are now mm:ss.
- **Mixed-script tokens**: Scribe glued Latin letters to an Arabic name ("الوسلati"). Drawn with one
  font, half of it became boxes. Now each script run gets its own font, transcribe.py lists such
  tokens, and the boundary report flags them inside clips. Still fix the spelling.
- **Digits and "·" on cards** were boxes: a whole Arabic line was drawn with the Arabic font. Cards
  now go word by word like subtitles.
- **Music bed with a silent tail**: Lyria tracks fade to silence over the last 3-5 s. Aligning the
  file end with the trailer end left the end card at -45 dB. render.py now aligns the last audible
  moment (`common.last_loud`).
- **Two people in a wide shot**: the median of all faces put the crop between them, on the
  bookshelf (465 verify mismatches). Faces are now clustered per shot and one person is chosen
  (`--prefer`, default: whoever the clip's close-ups show) with a WIDE SHOT warning.
- **Stale crop cache**: faces.json was keyed by start-end only, so changing `end_time` reused an old plan. The key includes end_time now.
- **The picker ignored topics named in --context** (e.g. Karbala). Use `--must`, and check anyway.
- **The picker started clips mid-sentence** (on أن / مع / نرى) and reused the cold-open line inside
  a chapter. The prompt now forbids both and the report flags them.
- **Codec**: `[ext=mp4]` picked VP9-in-mp4, which QuickTime can't preview. download.py prefers avc1.
- **Parallel agents**: give each editor its own work folder (renders write numbered files into
  `work/seg_*`), and don't run setup.sh twice at once.

- **Teasers in pieces**: one show repeated highlight lines at 0-75 s AND 2-5 min. The report flags lines said twice.
- **Music shorter than the edit** used to stop before the end card silently. It now loops with a warning.
- **No way to trim the start of a clip** inside a sentence (leading «ثم»): `start_time` now exists.
- **Fixing ASR words by hand** meant editing words[] and sents[] separately. Use fix_transcript.py.
- **Diacritics**: arabic-reshaper deletes harakat by default (لمّا showed as لما). They're kept now.

## Extracting one person (diarization)
- Speaker labels are only consistent within one request. Send up to 60 min in one diarized request (45 min took 60 s, $0.16).
- Diarization merged a co-host's voice into the guest's label. Text alone didn't reliably catch it.
  An LLM pass without visual cues missed it on one run and caught it on another.
- Pure statistics on camera shots failed. When voices are merged, the wrong person's close-ups also
  look "tied to the target". What worked: a numbered sheet of camera shots, a human/agent naming
  the target's shots, then turns where none of them is on screen are hinted to the LLM.
- One-second replies ("مركز أهل البيت") are part of exchanges. Merge across gaps up to 15 s instead of dropping short turns.

## Editing judgement
- Shows often open with their own teaser of the best lines. Skip the first ~2 minutes when
  picking and use the original occurrence (better context, cleaner audio).
- A trailer works best: hook line -> title card -> setup -> escalating conflict -> mid card
  ("...and the confrontation") -> climax -> short sting -> end card. ~75-90 s.
- A TL;DR needs longer clips (10-40 s) so arguments make sense. 5-7 chapters with numbered
  cards. Music only on cards keeps 5 minutes of dialogue listenable.
- Reels: start on speech, not a black card (the first second decides retention). Chapter title
  pinned at the top. Subtitles above the bottom ~25% (platform UI).
- The interviewer's pushback ("now you're accusing", "show your proof") is what makes moments
  feel like a confrontation. Keep those lines in the clip.
