#!/usr/bin/env python3
"""Download a video (YouTube or anything yt-dlp supports) as mp4.

    python download.py URL --out source.mp4 [--height 1080]

Use 1080p when vertical reels are planned: a 9:16 crop of a 16:9 frame keeps only ~32% of the
width, so 720p sources look soft after cropping. 720p is enough for 16:9-only edits.
Expect ~2-4 min and ~1.2-2 GB for a 70-100 min episode at 1080p. yt-dlp may warn "No supported
JavaScript runtime could be found"; downloads still work (installing deno silences it).
"""
import argparse, os, subprocess, sys
from common import ffmpeg_path

ap = argparse.ArgumentParser()
ap.add_argument('url')
ap.add_argument('--out', default='source.mp4')
ap.add_argument('--height', type=int, default=1080)
a = ap.parse_args()

home = os.environ.get('VIDEO_SKILLS_HOME', os.path.expanduser('~/.cache/video-skills'))
yt = os.environ.get('YTDLP') or os.path.join(home, 'bin', 'yt-dlp')
if not os.path.exists(yt):
    sys.exit(f'yt-dlp not found at {yt}. Run scripts/setup.sh first.')
# Prefer H.264 (avc1): VP9-in-mp4 works for ffmpeg but QuickTime/Finder can't preview it.
fmt = (f'bv*[height<={a.height}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={a.height}][ext=mp4]+ba[ext=m4a]/'
       f'b[height<={a.height}]')
cmd = [yt, '--ffmpeg-location', ffmpeg_path(), '-f', fmt, '--merge-output-format', 'mp4', '-o', a.out,
       '--no-playlist', '--concurrent-fragments', '8', '--no-progress', a.url]
r = subprocess.run(cmd)
if r.returncode or not os.path.exists(a.out):
    sys.exit('yt-dlp failed. If YouTube says "page needs to be reloaded", re-run setup.sh to refresh yt-dlp.')
print('saved', a.out)
