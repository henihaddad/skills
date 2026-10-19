#!/usr/bin/env python3
"""Pull a place's Google Maps photos via Apify and make numbered contact sheets to choose from.

    APIFY_TOKEN=... python scrape_photos.py "<google maps url or maps.app.goo.gl link>" --out photos/ [--max 200]

Why Apify: logged-out browsers get Google's "limited view" and see only ~6 photos; the gallery
won't open. The `webdata_labs/google-maps-photos-scraper` actor sweeps every photo tab
(117 of 136 photos for a test restaurant, ~$0.0012/photo). `fetch_cat/google-maps-photos-scraper`
returned only 12 for the same place. Pass the full place URL (the actor accepts share links too).

Writes photos/NNN.jpg, photos/metadata.json, photos/sheet_K.jpg (6x4 grids with the number on each).
Look at the sheets, pick the dish photos, and note which ones are menus (prices!) or storefronts.
"""
import argparse, concurrent.futures as cf, glob, json, os, sys, urllib.request
from PIL import Image, ImageDraw
from common import font, save

ap = argparse.ArgumentParser()
ap.add_argument('url')
ap.add_argument('--out', default='photos')
ap.add_argument('--max', type=int, default=200)
ap.add_argument('--actor', default='webdata_labs~google-maps-photos-scraper')
a = ap.parse_args()
tok = os.environ.get('APIFY_TOKEN') or sys.exit('Set APIFY_TOKEN (never hard-code it).')
os.makedirs(a.out, exist_ok=True)

body = {'placeUrls': [a.url], 'maxPhotosPerPlace': a.max, 'imageSize': 'large', 'outputMode': 'photo'}
req = urllib.request.Request(f'https://api.apify.com/v2/acts/{a.actor}/run-sync-get-dataset-items?token={tok}&timeout=290',
                             data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
items = json.load(urllib.request.urlopen(req, timeout=320))
if isinstance(items, dict):
    sys.exit(f'Apify error: {items}')
photos = [x for x in items if x.get('mediaType', 'photo') == 'photo' and x.get('imageUrl')]
print(f'{len(items)} items, {len(photos)} photos')
save(items, os.path.join(a.out, 'metadata.json'))

def get(t):
    i, x = t; p = os.path.join(a.out, f'{i:03d}.jpg')
    if not os.path.exists(p):
        urllib.request.urlretrieve(x['imageUrl'], p)
    return p
with cf.ThreadPoolExecutor(12) as ex:
    files = list(ex.map(get, enumerate(photos, 1)))

C, R, W = 6, 4, 260
for s in range(0, len(files), C * R):
    sheet = Image.new('RGB', (C * W, R * W), 'white'); d = ImageDraw.Draw(sheet)
    for k, p in enumerate(files[s:s + C * R]):
        im = Image.open(p).convert('RGB'); im.thumbnail((W - 6, W - 6))
        x, y = (k % C) * W, (k // C) * W; sheet.paste(im, (x + 3, y + 3))
        d.rectangle([x + 3, y + 3, x + 66, y + 38], fill='black')
        d.text((x + 7, y + 4), os.path.basename(p)[:3], fill='yellow', font=font('latin', 28))
    out = os.path.join(a.out, f'sheet_{s // (C * R) + 1}.jpg'); sheet.save(out, quality=80); print(out)
