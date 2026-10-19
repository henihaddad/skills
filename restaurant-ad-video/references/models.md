# Models, prices and behaviour (observed via OpenRouter, Oct 2026)

Check live options with `curl https://openrouter.ai/api/v1/videos/models`. It lists durations,
resolutions, aspect ratios, frame-image support and pricing SKUs per model.

## Image-to-video (first frame = cropped 9:16 photo, 5 s)

| model | billed | output | behaviour on food |
|---|---|---|---|
| `kwaivgi/kling-v3.0-pro` | $0.56 (720p, no audio) | 1080x1920 native | most faithful to the photo; motion calmer; did the lemon squeeze; dressing barely poured |
| `kwaivgi/kling-v3.0-std` | ~$0.42 | 720p | cheaper Kling |
| `bytedance/seedance-2.5` | $0.52 at 480p, ~$1.16 at 720p (est.) | 480x854 / 720x1280 | most dynamic: dressing really pours, fork lifts a shrimp, closer push-ins; less faithful, softer at 480p; max 720p on OpenRouter |
| `bytedance/seedance-2.0` | ~$0.34 480p / ~$0.76 720p / ~$1.87 1080p (est.) | up to 4K | older Seedance, higher resolutions |
| `heygen/heygen-video-1` | ~$0.09 at 768p | keeps the input photo's shape | cheap drafts; **ignores aspect_ratio when a first frame is given**, which caused mixed shapes in a reel |

Seedance bills per video token. Rough estimate: tokens ≈ width × height × 24 × seconds / 1024.
Kling bills per second.

Resolution affects detail, not the kind of motion: same model and prompt give the same style
at 480p, but steam/drips/textures get mushy, and upscaling 480p to 1080x1920 looks soft on a
phone. Use 480p to preview motion, not for delivery.

## Voice, music, transcription
- TTS `elevenlabs/eleven-v4-turbo` via `/audio/speech`: multilingual voices (`daniel` sounded
  good in French), `[warmly]`/`[excited]` audio tags work. A few cents per reel.
- Music `google/lyria-3-pro-preview` $0.08 per track (~60+ s), `lyria-3-clip-preview` $0.04 (~30 s).
  Must stream with `modalities: ["text","audio"]`, otherwise you pay and get no audio.

## Typical budget for one ad
| | |
|---|---|
| photos (Apify, ~120 photos) | ~$0.15 |
| 8 Kling clips | ~$4.50 |
| or 8 Seedance 2.5 480p previews | ~$4.15 |
| voice + music | ~$0.10 |
| **total** | **~$5** |

## Pitfalls hit in practice
- **Key limit**: an OpenRouter key with a $10 cap ran out mid-project. Every call then fails
  with 403 "Key limit exceeded". Ask the user to raise it before a batch.
- **Wrong name**: the listing said "Bella Artista" but the storefront sign, menu and map label said
  "Bella Vista", while glass logos said "Bella Artista". Confirm the name with the user/client.
- **Mixed aspect ratios** look broken in a reel. Pre-crop to 9:16 rather than blurred-background fill.
- **Too many dishes** (20 at 1 s each) reads as a slideshow. 6-8 hero dishes at ~2.2 s with varied motion read as an ad.
- **Hook**: open on the most striking dish with a 2-3 word question, not on the interior.
- Fonts: draw the ★ as a polygon (many fonts lack the glyph). Arabic captions need RTL shaping (handled in `common.py`).
