---
name: restaurant-ad-video
description: Make a short vertical video ad (Instagram/TikTok reel, "spot publicitaire") for a restaurant, café or food business from its real Google Maps photos - scrape the photos, pick the dishes, animate each photo with an AI video model (Kling, Seedance, HeyGen via OpenRouter), and cut a 9:16 reel with dish captions and prices, voiceover, music and an end card. Use this whenever someone shares a Google Maps link to a restaurant or food place and wants an ad, promo video, reel, or "something to pitch the owner", or asks to compare AI video models (Kling vs Seedance) on food shots.
compatibility: Needs an OpenRouter API key with ~$10 of credit (OPENROUTER_API_KEY) and an Apify account token (APIFY_TOKEN, free tier is enough), python3, curl, internet.
---

# Restaurant ad video

Real food photos in, a 20-30 s 9:16 ad out. The pipeline: **scrape photos -> pick and crop
dishes -> animate each photo -> voiceover + music -> assemble with captions and an end card.**

## Requirements (check these before starting)

| need | what for | how to get it | cost |
|---|---|---|---|
| **OpenRouter account + API key** -> `OPENROUTER_API_KEY` | AI video clips (Kling/Seedance/HeyGen), voiceover (ElevenLabs), music (Lyria) | openrouter.ai -> add credits -> Settings -> Keys | ~$5 per ad with Kling; keep **~$10** available so a batch can finish, plus a re-roll |
| **Apify account + API token** -> `APIFY_TOKEN` | scraping all of the restaurant's Google Maps photos | apify.com -> sign up -> Settings -> API & Integrations -> copy the token | ~$0.15 per restaurant; the **free plan ($5/month credit)** covers it |
| python3 + curl | scripts, setup | preinstalled on macOS/Linux | free |

**Why Apify:** Google shows logged-out browsers a "limited view" with ~6 photos and no gallery.
Apify's scraper gets the full gallery (~120 of 136 photos in testing). Without an Apify token,
fall back to photos the user or restaurant provides (better for a paid ad anyway): put them in
`photos/` as `001.jpg`, `002.jpg`… and continue from step 2.

If a key is missing, ask the user for it before any paid step and say what it's for and what
it'll cost. Check the OpenRouter key's remaining budget before generating (`gen_clips.py`
prints it): a 403 "Key limit exceeded" mid-batch leaves half a set, and the fix is for the user
to raise the key's limit. Never write keys into files or a repo; if the user pastes one, use it
only in the command and suggest rotating it afterwards.

## 0. Setup
```bash
bash scripts/setup.sh; PY=~/.cache/video-skills/venv/bin/python
```

## 1. Photos
```bash
APIFY_TOKEN=... $PY scripts/scrape_photos.py "<maps link>" --out photos
```
Then **look at every `photos/sheet_*.jpg`** and sort the numbers into: dishes, desserts/drinks,
interior, storefront, menu pages. Read the menu pages at full size for **exact prices**.
Typical yield: ~75% food photos. A logged-out browser only sees ~6 photos, which is why this uses Apify.

Check the restaurant's **name** across sources: storefront sign, menu, Google listing, logos on
glasses/plates. They can disagree (a renamed place). Ask the user which name goes in the ad.

## 2. Choose and crop the shots
Pick 6-8 hero dishes (more becomes a slideshow), strongest/most dramatic first (that's the hook),
desserts and drinks near the end. Prefer portrait photos; they survive a 9:16 crop.
```bash
$PY scripts/crop_916.py photos 019 055 069 085 082:0.35 012 025 097 --out src
```
Look at `src/strip.jpg` before paying for generation.

## 3. Animate
Write `shots.json` with **one specific motion per dish**. Variety is what makes it feel like a
commercial rather than a slideshow: lemon squeezed on fish, dressing drizzled, cheese bubbling,
a fork lifting pasta, sauce dripping down a glass, steam, slow orbit, fast push-in for the hook.
```bash
$PY scripts/gen_clips.py shots.json --src src --out clips_kling --model kwaivgi/kling-v3.0-pro
```
Model choice (details and prices in `references/models.md`):
- **Kling 3.0 Pro** (default, $0.56/5 s clip): most faithful to the real dish, calm motion, native 1080x1920.
- **Seedance 2.5** (~$1.16/5 s at 720p): more dynamic, actually performs pours and lifts; slightly softer and drifts more from the photo.
- **HeyGen Video 1** (~$0.09/5 s): cheapest, fine for a rough draft; ignores 9:16 when given a first frame.
- To try Seedance cheaply, run all shots at `--resolution 480p` (~$0.52 each), compare, then
  re-run only the winners at 720p. 480p previews motion; detail is softer.
```bash
$PY scripts/compare.py --dirs clips_kling clips_seed480 --labels KLING SEED --ids 019 055 069 085 --out compare.jpg
```

## 4. Voice and music
```bash
$PY scripts/voiceover.py vo.json --out vo --voice daniel      # one file per line, ~cents
$PY scripts/music.py "30-second warm upbeat Italian acoustic restaurant commercial, mandolin, guitar" --out music.mp3
```
Write the voiceover as short lines that each match a section (hook / dishes / desserts /
call to action), in the language of the audience (French, Tunisian derja, Arabic, English…),
with the phone number spelled out in words. Name the dishes that are on screen.

## 5. Assemble
Fill `reel.json` (schema in the docstring of `scripts/build_reel.py`): shots with `start`
(the motion usually happens 2-4 s into a 5 s clip), captions, prices **only where you read
them on the menu**, voice lines with `at` times, end card (name, tagline, rating, address,
phone, blurred interior photo).
```bash
$PY scripts/build_reel.py reel.json
```
Changing only `clips_dir` re-renders an identical edit with another model's clips, for a fair comparison.

## 6. Check and report
Extract frames (hook, a captioned dish, the end card) and look at them. Check for empty-box
glyphs, text over faces or food, and that each crop fills the frame. You can't hear the
result, so ask the user to check voice pronunciation (especially the phone number) and music level.

Tell the user, plainly:
- files, length, cost per step;
- which dishes are on screen and which prices you showed;
- **photo rights**: Google Maps photos are mostly user uploads. They're fine for a free pitch to
  the owner; for a paid or published ad, use the restaurant's own photos or get permission;
- the AI motion is generated; the dishes come from real photos but the motion isn't real footage.

## Selling it (when the user asks)
Show a free demo first (it costs ~$2-6 to make), then offer a monthly package (e.g. 4 reels a
month: new dishes, offers, seasonal specials). Each reel costs a few dollars to make. What
improves a paid version: the restaurant's own photos or 5 dishes filmed on a phone, a
voiceover written for the cut, captions with offers, ~15-20 s for Stories.
