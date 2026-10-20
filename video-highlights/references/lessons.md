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

- **The picker misread sentence indices** (a note about being dismissed over French pointed at «لا لا
  شوف», 380 sentences away; a 2-s cold open; 205 s of speech for a 5-min target). Picks now carry
  start/end quotes and are re-anchored by matching them; short clips and low totals are flagged.
- **Edge padding leaked the next sentence's first word**, while a tight end_time dropped the last
  word. Padding now stops at neighbouring sentences, and karaoke keeps words starting before the cut.
- **"2014،"** (Latin digits + Arabic comma) rendered as boxes: digits inside RTL tokens get their own font run.
- **Merging "similar" shots dropped a real cut** (a wide shot whose between-people median was near
  the close-up's x), cropping onto a plant. Shots are no longer merged.
- **A gesturing hand pulled the crop off-centre.** Detections much smaller than the biggest face in the frame are ignored.
- **Verify's 2-camera k-means was unstable** (0 vs 1,575 false mismatches after removing one clip).
  Now k-means++ with restarts and an automatic camera count.
- **Guest in profile at the frame edge** wasn't detected in the wide shot, so the crop followed the
  host while the guest talked, and x from different cameras was compared. Fix: the camera-angle pass
  plus `--angle-x`, one decision per camera with a preview image (0 mismatches on 8,361 frames).
- **Burned-in subtitles** in the source (the show's own captions on teaser moments) stack under ours.
  Not auto-detected yet; look for them in step 6.

## Found by the reels test runs (4 episodes in parallel, Oct 2026)
- **The picker's reels need an editor.** Every reel was reworked: questions without their answer,
  filler endings, a hook that was the reel's own punch line, 1-s hooks, and one run with no hooks at
  all. The prompt now asks for 2.5-6 s hooks from the middle of the reel; the report flags short hooks
  and hooks that repeat the ending, and counts reel length without the hook.
- **Handheld single camera** (a radio studio filmed with one zooming camera): one crop per shot cut the
  guest off (crop at x=515, face at 860). Shots where the one person moves a lot are now tracked:
  detect every 3rd frame, median filter, lazy camera (dead zone 45 px, max 14 px/frame, 6 frames ahead).
- **Hundreds of crop steps** made ffmpeg fail to parse a linear chain of nested `if()`s. The crop
  expression is now a balanced if-tree (depth ~9).
- **Burned-in captions everywhere**: one show captioned its best moments in the episode body, not only in
  the teaser. `keep_top` crops the caption band away.
- **Laptop heat**: four agents encoding 1080x1920 with libx264 kept all cores at 100% for 30 min.
  libx264 used 29 s of CPU for a 20 s clip; the Mac media engine (h264_videotoolbox) 3.7 s, same wall
  time, SSIM 0.986. Now the default on macOS, with hardware decode of the source.
- **Hyphens** (Scribe writes stutters/false starts as `م-م-م-`, `تعشقها-`) were empty boxes. clean_token drops them.
- **Latin inside an Arabic line** came out reversed ("FM Cap"). Runs of Latin words are now placed as one block.
- **fix_transcript.py** couldn't delete a token (division by zero), re-added stripped punctuation, and
  took 2+ min on a 107-min transcript (all words x all sentences). All three fixed.
- **render.py** crashed when the `--out` folder didn't exist (wasted a 2-min render). It creates it now.
- **`--angle-x` repeated** silently kept only the last value; it now accumulates.
- **240p-only sources** exist (an old TV show). download.py now prints the resolution and warns.
- **25 fps sources**: rendered segments are 30 fps, so frame indices differ by x1.2 when checking cuts.
- A Scribe chunk returned 504 once; requests are now retried on 5xx/timeouts.

## Found by the timed Safi Said run (IFM TV, Oct 2026)
- **Haar cascades were the weak link.** With glasses and a mic in front of the face they found it in 14 of
  46 frames, and fired on the station logo (IFMTV, top right), headphones on the desk and the "IFM"
  lettering on the wall. Tracking then followed those and swung across the frame; the agent needed 7
  facetrack runs and 5 hand edits. YuNet found the face in 46/46 frames at 8 ms vs 23 ms per frame; the
  same plan now needs no hand edits (0 mismatches, face off-centre in 0.3% of sampled frames) and the first
  run costs half the CPU. Tracking also keeps only the main chain of detections (stray hits dropped).
- **The tracking trigger** first used max-min of all detections (fired on stray hits), then the 10-90
  percentile (missed a handheld guest: face off-centre 11%). Now: max-min of the main chain > 0.2 crop widths.
- **verify only checked camera consistency**, so a guest drifting out of a single-camera shot passed. It now
  also reports how often the face is outside the middle 70% of the crop.
- **The faces.json cache ignored --track**; a re-run with `--track off` silently reused tracked paths.
- **Dissolves/zooms** have no hard cut, so both shots shared one crop. They're now split at the biggest change.
- **Latin in --brand** was drawn with the Arabic font (boxes), and a long end-card line was clipped at
  both edges. Tags/brand go word by word now; long card lines wrap (never inside a Latin name) or shrink.
- **One black frame** started every reel (clip fade-in). 9:16 clips are hard-cut now.

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
