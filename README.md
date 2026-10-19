# skills

Agent skills for [Claude Code](https://claude.com/claude-code) and other agents that load
`SKILL.md` folders. Each folder is one self-contained skill: a `SKILL.md` with the workflow,
`scripts/` that do the deterministic work, and `references/` with the details and lessons learned.

| skill | what it does |
|---|---|
| [`video-highlights`](video-highlights/) | Long video or podcast (e.g. a YouTube link) -> transcript with word timestamps -> best moments -> **trailer**, **chaptered TL;DR**, **9:16 reels** with word-by-word karaoke subtitles (RTL/Arabic aware) and a frame-exact face-tracked crop, or a **compilation of every moment one person speaks** (diarization + on-screen check + LLM relabel). |
| [`restaurant-ad-video`](restaurant-ad-video/) | A restaurant's Google Maps photos -> pick dishes -> animate with Kling / Seedance / HeyGen -> **9:16 ad reel** with dish captions, prices, voiceover, music and an end card. Includes a model comparison workflow. |

## Install

Claude Code picks up skills from `~/.claude/skills/`:

```bash
git clone https://github.com/henihaddad/skills.git ~/code/skills
ln -s ~/code/skills/video-highlights    ~/.claude/skills/video-highlights
ln -s ~/code/skills/restaurant-ad-video ~/.claude/skills/restaurant-ad-video
```

Then one-time setup (Python venv + verified yt-dlp + ffmpeg):

```bash
bash ~/code/skills/video-highlights/scripts/setup.sh
```

## Requirements and keys

| | `video-highlights` | `restaurant-ad-video` | where to get it |
|---|---|---|---|
| **OpenRouter API key** `OPENROUTER_API_KEY` | required (~$0.60 per 90-min episode) | required (~$5 per ad, keep ~$10 of credit) | [openrouter.ai](https://openrouter.ai) -> add credits -> Settings -> Keys |
| **Apify token** `APIFY_TOKEN` | not needed | required for Google Maps photos (free plan is enough) | [apify.com](https://apify.com) -> Settings -> API & Integrations |
| python3, curl | yes | yes | preinstalled on macOS / Linux |

Everything else (yt-dlp, ffmpeg, OpenCV, Arabic text shaping) is installed by `setup.sh`.

The scripts read keys from the environment and never store them:

```bash
export OPENROUTER_API_KEY=sk-or-...   # put it in your shell profile or a local .env, never in the repo
export APIFY_TOKEN=apify_api_...
```

Tip: set a spending limit on the OpenRouter key. If you hit it, calls fail with 403 "Key limit
exceeded"; raise the limit and re-run (finished clips are cached and skipped).

## Costs (typical)

- 90-minute podcast -> trailer + TL;DR + reels: **~$0.60**
- 45-minute talk show -> every moment of one guest: **~$0.30**
- restaurant ad with 8 AI-animated dishes: **~$5**

## Responsible use

These tools cut other people's videos and use photos uploaded by Google Maps users. That's
fine for private tests and pitches. For anything you publish or sell, get permission from the
show or restaurant (or use their own footage and photos).

## License

MIT
