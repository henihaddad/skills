#!/usr/bin/env bash
# One-time setup for the video skills. Creates a private Python venv and fetches the official
# yt-dlp binary (checksum-verified). Safe to re-run; it only installs what is missing.
#
#   bash scripts/setup.sh            -> prints the python + yt-dlp paths to use
#
# Location can be overridden with VIDEO_SKILLS_HOME (default ~/.cache/video-skills).
set -euo pipefail
HOME_DIR="${VIDEO_SKILLS_HOME:-$HOME/.cache/video-skills}"
VENV="$HOME_DIR/venv"
mkdir -p "$HOME_DIR/bin"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip -q install --upgrade pip >/dev/null 2>&1 || true
# opencv < 5: OpenCV 5 dropped CascadeClassifier, which the face tracker uses.
"$VENV/bin/python" -m pip -q install pillow numpy imageio-ffmpeg arabic-reshaper python-bidi "opencv-python-headless<5"

# yt-dlp: the pip build pins to whatever your Python supports (3.9 gets a stale release that
# YouTube breaks), so use the official standalone binary instead.
YT="$HOME_DIR/bin/yt-dlp"
case "$(uname -s)" in
  Darwin) ASSET=yt-dlp_macos ;;
  Linux)  ASSET=yt-dlp_linux ;;
  *)      ASSET=yt-dlp ;;
esac
if [ ! -x "$YT" ] || [ "$(find "$YT" -mtime +14 2>/dev/null)" ]; then
  TMP="$(mktemp -d)"
  curl -sSL -o "$TMP/$ASSET" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/$ASSET"
  curl -sSL -o "$TMP/SHA2-256SUMS" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
  (cd "$TMP" && grep " $ASSET\$" SHA2-256SUMS | shasum -a 256 -c - >/dev/null)
  mv "$TMP/$ASSET" "$YT" && chmod +x "$YT" && rm -rf "$TMP"
fi

FFMPEG="$("$VENV/bin/python" -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
ln -sf "$FFMPEG" "$HOME_DIR/bin/ffmpeg"
echo "PYTHON=$VENV/bin/python"
echo "YTDLP=$YT"
echo "FFMPEG=$HOME_DIR/bin/ffmpeg"
