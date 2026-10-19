"""Shared helpers for the video-highlights scripts: ffmpeg, OpenRouter, and text rendering.

Everything here is deliberately dependency-light. Text rendering handles right-to-left
scripts (Arabic, Hebrew, Persian, Urdu) word by word so karaoke highlighting works in both
directions, and falls back to a Latin font for embedded Latin words (e.g. French/English
words inside Tunisian derja), because most Arabic system fonts have no Latin glyphs.
"""
import json, os, re, shutil, subprocess, sys, urllib.request, urllib.error

# ---------------------------------------------------------------- ffmpeg
def ffmpeg_path():
    """ffmpeg from $FFMPEG, PATH, or the imageio-ffmpeg wheel installed by setup.sh."""
    p = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit('ffmpeg not found. Run scripts/setup.sh or install ffmpeg.')

FF = None
def ff(*args, quiet=True):
    """Run ffmpeg; raise with stderr on failure."""
    global FF
    FF = FF or ffmpeg_path()
    cmd = [FF, '-hide_banner', '-y'] + (['-v', 'error'] if quiet else []) + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'ffmpeg failed: {" ".join(cmd)}\n{r.stderr[-2000:]}')
    return r

def ff_stderr(*args):
    """Run ffmpeg and return stderr (for showinfo / volumedetect / duration parsing)."""
    global FF
    FF = FF or ffmpeg_path()
    return subprocess.run([FF, '-hide_banner', *map(str, args)], capture_output=True, text=True).stderr

def duration(path):
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', ff_stderr('-i', path))
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0

# ---------------------------------------------------------------- OpenRouter
API = 'https://openrouter.ai/api/v1'

def key():
    k = os.environ.get('OPENROUTER_API_KEY')
    if not k:
        sys.exit('Set OPENROUTER_API_KEY (never hard-code it in scripts or commit it).')
    return k

def post(path, body, timeout=600, raw=False):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + key(), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors='replace')
        if e.code == 403 and 'limit' in msg.lower():
            sys.exit('OpenRouter key spending limit reached. Raise it in OpenRouter settings and retry.\n' + msg[:400])
        raise RuntimeError(f'OpenRouter {e.code}: {msg[:800]}')
    return data if raw else json.loads(data)

def chat_json(model, prompt, temperature=0.3):
    """One chat call that must return a JSON object. Returns (obj, cost)."""
    d = post('/chat/completions', {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                                   'response_format': {'type': 'json_object'}, 'temperature': temperature})
    c = d['choices'][0]['message']['content'].strip()
    c = re.sub(r'^```(?:json)?|```$', '', c).strip()
    return json.loads(c), (d.get('usage') or {}).get('cost')

def key_status():
    req = urllib.request.Request(API + '/key', headers={'Authorization': 'Bearer ' + key()})
    d = json.load(urllib.request.urlopen(req, timeout=30)).get('data', {})
    return {k: d.get(k) for k in ('limit', 'usage', 'limit_remaining')}

# ---------------------------------------------------------------- text
RTL_RE = re.compile('[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]')
LATIN_RE = re.compile('[A-Za-z\u00c0-\u024f]')

def is_rtl(text):
    return bool(RTL_RE.search(text))

def clean_token(t):
    """Drop stray scripts that ASR sometimes hallucinates (Cyrillic/CJK inside Arabic) and map
    Latin/full-width punctuation to Arabic punctuation for RTL words: Arabic system fonts such as
    Geeza Pro have no glyph for ! ? , : and render them as empty boxes."""
    t = re.sub('[\u0400-\u04ff\u3040-\u30ff\u4e00-\u9fff]', '', t)
    if is_rtl(t) and not LATIN_RE.search(t):
        for a, b in (('！', ''), ('!', ''), ('？', '؟'), ('?', '؟'), ('，', '،'), (',', '،'), ('：', ''), (':', ''), ('；', '؛'), (';', '؛')):
            t = t.replace(a, b)
    return t.strip()

def shape(t):
    """Visual form of one word/line for PIL (which has no complex-script shaping without raqm)."""
    if not is_rtl(t):
        return t
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(t))

FONT_CANDIDATES = {
    'rtl':   [('/System/Library/Fonts/GeezaPro.ttc', 1), ('/System/Library/Fonts/Supplemental/Damascus.ttc', 0),
              ('/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf', 0), ('/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf', 0),
              ('C:/Windows/Fonts/arialbd.ttf', 0)],
    'latin': [('/System/Library/Fonts/Avenir Next.ttc', 1), ('/System/Library/Fonts/Helvetica.ttc', 1),
              ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 0), ('C:/Windows/Fonts/arialbd.ttf', 0)],
    'serif': [('/System/Library/Fonts/Supplemental/Didot.ttc', 1), ('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 0)],
}
_font_cache = {}
def font(kind, size):
    from PIL import ImageFont
    k = (kind, size)
    if k not in _font_cache:
        for path, idx in FONT_CANDIDATES[kind]:
            if os.path.exists(path):
                _font_cache[k] = ImageFont.truetype(path, size, index=idx)
                break
        else:
            _font_cache[k] = ImageFont.load_default(size=size)
    return _font_cache[k]

def font_for(word, size):
    """Arabic font for RTL words, Latin font for words containing Latin letters."""
    return font('latin', size) if (LATIN_RE.search(word) or not is_rtl(word)) else font('rtl', size)

def draw_words(draw, words, y, width, size, active=-1, color='white', hl=(255, 210, 60), stroke=5):
    """Draw a single line of words centred at y, highlighting words[active]. Handles RTL order."""
    rtl = any(is_rtl(w) for w in words)
    shaped = [shape(w) for w in words]
    fonts = [font_for(w, size) for w in words]
    sp = draw.textlength(' ', font=font('rtl' if rtl else 'latin', size)) * 1.4
    widths = [draw.textlength(s, font=f) for s, f in zip(shaped, fonts)]
    total = sum(widths) + sp * (len(words) - 1)
    x = (width + total) / 2 if rtl else (width - total) / 2
    for i, (s, f, w) in enumerate(zip(shaped, fonts, widths)):
        if rtl:
            x -= w
        # Latin fonts sit higher on the line than Arabic ones; nudge them down to share a baseline
        dy = int(size * 0.1) if (rtl and f is not fonts[0] and LATIN_RE.search(words[i])) else 0
        draw.text((x, y + dy), s, font=f, fill=hl if i == active else color, stroke_width=stroke, stroke_fill='black')
        x = x - sp if rtl else x + w + sp

def centred(draw, y, text, size, width, fill='white', kind=None, stroke=0):
    words = [w for w in text.split() if w]
    f = font(kind, size) if kind else None
    if f is None:
        draw_words(draw, words, y, width, size, color=fill, hl=fill, stroke=stroke)
        return
    s = shape(text)
    draw.text(((width - draw.textlength(s, font=f)) / 2, y), s, font=f, fill=fill, stroke_width=stroke, stroke_fill='black')

def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
