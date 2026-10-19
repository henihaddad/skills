# skills

Agent skills for [Claude Code](https://claude.com/claude-code) and other agents that load
`SKILL.md` folders. Each folder is one self-contained skill: a `SKILL.md` with the workflow,
`scripts/` that do the deterministic work, and `references/` with the details and lessons learned.

| skill | what it does |
|---|---|
| [`video-highlights`](video-highlights/) | Long video or podcast (e.g. a YouTube link) -> transcript with word timestamps -> best moments -> **trailer**, **chaptered TL;DR**, and **9:16 reels** with word-by-word karaoke subtitles (RTL/Arabic aware) and a frame-exact face-tracked crop. |
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

## Keys

The scripts read keys from the environment and never store them:

- `OPENROUTER_API_KEY` for transcription, LLM picks, video, voice and music ([openrouter.ai](https://openrouter.ai))
- `APIFY_TOKEN` for Google Maps photos, restaurant skill only ([apify.com](https://apify.com))

## Costs (typical)

- 80-minute podcast -> trailer + TL;DR + 6 reels: **~$0.40**
- restaurant ad with 8 AI-animated dishes: **~$5**

## Responsible use

These tools cut other people's videos and use photos uploaded by Google Maps users. That's
fine for private tests and pitches. For anything you publish or sell, get permission from the
show or restaurant (or use their own footage and photos).

## License

MIT
