#!/usr/bin/env python3
"""
build_db.py — builds the offline databases the cardscan phone app uses.

  python build_db.py                      -> cards.json.gz   every paper printing: prices (TCGplayer market USD, Cardmarket EUR),
                                                              rarity, variant (retro/showcase/borderless/...), artist, release,
                                                              oracle text, type, colors.  ~5 MB. Re-run whenever you want fresh prices.
  python build_db.py --hash-sets all      -> hashes.json.gz  fingerprints for EVERY set since 2010 (--since 2015 for fewer); a few hours,
                                                              safe to stop and re-run — it continues where it left off.
  python build_db.py --hash-sets mh3,mid  -> hashes.json.gz  image fingerprints for those sets, so the app identifies their cards
                                                              instantly and offline (no API call). Downloads ~40 KB per card from
                                                              Scryfall at their polite rate (about 30 s per 300-card set). Merges into
                                                              an existing hashes.json.gz.
  python build_db.py --langs en,ja,de     -> include other languages in cards.json.gz (default: English only). Foreign printings carry
                                             their printed name so the phone's text reader can match them (with the matching language
                                             pack uploaded: jpn.traineddata for ja, deu for de, fra, spa, ita, por, rus, kor, chi_sim).

Put the resulting .gz files next to index.html in the GitHub repo (commit them), then tap "Update database" in the app.

Setup:  pip install requests pillow numpy   (ijson only needed for pre-July-2026 JSON-array files)
Data:   Scryfall bulk data (https://scryfall.com/docs/api/bulk-data) and card images. Not affiliated; please respect their rate limits.
"""
import argparse
import gzip
import io
import json
import os
import sys
import time
import tempfile
from pathlib import Path

import requests

UA = {"User-Agent": "cardscan-build/1.0 (personal collection tool)", "Accept": "application/json"}
BULK = "https://api.scryfall.com/bulk-data/default-cards"

RARITY = {"common": "c", "uncommon": "u", "rare": "r", "mythic": "m", "special": "s", "bonus": "b"}


def variant_flags(c):
    """Short human labels for the things that change a card's value beyond set + number."""
    v = []
    fe = set(c.get("frame_effects") or [])
    if c.get("frame") == "1997" or "retro" in fe: v.append("retro")
    if "showcase" in fe: v.append("showcase")
    if "extendedart" in fe: v.append("extended art")
    if c.get("border_color") == "borderless": v.append("borderless")
    if c.get("full_art"): v.append("full art")
    if c.get("textless"): v.append("textless")
    if "etched" in fe: v.append("etched")
    if "inverted" in fe: v.append("inverted")
    if c.get("promo"): v.append("promo")
    for pt in c.get("promo_types") or []:
        if pt in ("prerelease", "buyabox", "judgegift", "serialized", "ripplefoil", "surgefoil", "galaxyfoil", "confettifoil",
                  "textured", "halofoil", "fracturefoil", "stepandcompleat", "oilslick", "gilded", "neonink", "doublerainbow",
                  "rainbowfoil", "raisedfoil", "silverfoil", "embossed", "startercollection", "boosterfun", "playpromo"):
            v.append(pt)
    if c.get("set_type") == "token" or c.get("layout") in ("token", "double_faced_token"): v.append("token")
    if c.get("layout") == "art_series": v.append("art series")
    if c.get("lang", "en") != "en": v.append(c["lang"])
    return ",".join(dict.fromkeys(v))


def price(p, k):
    v = (p or {}).get(k)
    return float(v) if v not in (None, "") else None


def iter_bulk_cards(path):
    """Yield card objects from a downloaded bulk file: gzipped JSONL (Scryfall since July 2026), plain JSONL, or the old JSON array."""
    with open(path, "rb") as f:
        head = f.read(2)
    if head == b"\x1f\x8b":                                   # gzip -> JSONL inside
        with gzip.open(path, "rt", encoding="utf-8") as g:
            for line in g:
                line = line.strip().rstrip(",")
                if line and line not in ("[", "]"):
                    yield json.loads(line)
        return
    with open(path, "rb") as f:
        first = f.read(1)
    if first == b"[":                                         # old-style JSON array
        import ijson
        with open(path, "rb") as f:
            for c in ijson.items(f, "item"):
                yield c
        return
    with open(path, "r", encoding="utf-8") as f:              # plain JSONL
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_cards(langs, out_path):
    print("fetching bulk-data index…")
    r = requests.get(BULK, headers=UA, timeout=30)
    meta = r.json()
    url = meta.get("jsonl_download_uri") or meta.get("download_uri")
    if not url:
        sys.exit(f"Scryfall bulk-data reply had no download link (HTTP {r.status_code}): {str(meta)[:300]}")
    print(f"downloading {url}…")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bulk")
    with requests.get(url, headers={"User-Agent": UA["User-Agent"], "Accept": "*/*"}, stream=True, timeout=120) as dl:
        dl.raise_for_status()
        done = 0
        for chunk in dl.raw.stream(1 << 20, decode_content=False):   # keep the file exactly as served (gz stays gz)
            tmp.write(chunk); done += len(chunk)
            if done % (20 << 20) < (1 << 20): print(f"  {done / 1e6:.0f} MB", end="\r", flush=True)
    tmp.close()
    print(f"\ndownloaded {os.path.getsize(tmp.name) / 1e6:.0f} MB, parsing…")
    cards, oracle, oracle_idx, sets = [], [], {}, {}
    n = 0
    for c in iter_bulk_cards(tmp.name):
        n += 1
        if n % 50000 == 0: print(f"  {n:,} cards read", end="\r", flush=True)
        if "paper" not in (c.get("games") or []): continue
        if c.get("lang", "en") not in langs: continue
        if c.get("layout") in ("art_series",) or c.get("oversized"): continue
        oid = c.get("oracle_id") or (c.get("card_faces") or [{}])[0].get("oracle_id") or c["id"]
        if oid not in oracle_idx:
            face = (c.get("card_faces") or [c])[0]
            oracle_idx[oid] = len(oracle)
            oracle.append([c.get("name", ""), face.get("type_line") or c.get("type_line", ""), face.get("mana_cost") or c.get("mana_cost", ""),
                           float(c.get("cmc", face.get("cmc", 0)) or 0), "".join(face.get("colors") or c.get("colors") or []),
                           face.get("oracle_text") or c.get("oracle_text", ""), c.get("layout", "")])
        sets.setdefault(c["set"], c.get("set_name", c["set"]))
        p = c.get("prices") or {}
        cards.append([c["id"], c["name"], c["set"], c["collector_number"], RARITY.get(c.get("rarity"), "?"), c.get("lang", "en"),
                      price(p, "usd"), price(p, "usd_foil"), price(p, "usd_etched"), price(p, "eur"), price(p, "eur_foil"),
                      variant_flags(c), c.get("artist", ""), c.get("released_at", ""), oracle_idx[oid],
                      "".join(x[0] for x in (c.get("finishes") or [])),
                      (c.get("printed_name") or (c.get("card_faces") or [{}])[0].get("printed_name") or "") if c.get("lang", "en") != "en" else ""])
    os.unlink(tmp.name)
    if not cards:
        sys.exit("no cards were read — the download may have failed; try again")
    db = {"built": time.strftime("%Y-%m-%d"), "source": "Scryfall default_cards (prices: TCGplayer market USD, Cardmarket EUR)",
          "langs": sorted(langs), "sets": sets, "fields": ["id", "name", "set", "cn", "rarity", "lang", "usd", "usd_foil", "usd_etched",
          "eur", "eur_foil", "variant", "artist", "released", "oracle", "finishes", "printed_name"],
          "oracle_fields": ["name", "type_line", "mana_cost", "cmc", "colors", "oracle_text", "layout"],
          "cards": cards, "oracle": oracle}
    raw = json.dumps(db, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    with gzip.open(out_path, "wb", compresslevel=9) as g:
        g.write(raw)
    print(f"{len(cards):,} printings of {len(oracle):,} cards from {len(sets):,} sets ({n:,} scanned) -> {out_path} "
          f"({os.path.getsize(out_path) / 1e6:.1f} MB gz, {len(raw) / 1e6:.1f} MB raw)")


# ----------------------------------------------------------------------------- image hashes

CROP_W, CROP_H = 700, 977   # the app's canonical card crop; hashes are defined on this geometry


def card_hash_from_image(im):
    """512-bit dHash of a full card image: 16x16 horizontal + 16x16 vertical gradient signs over box-averaged cells.
    Must match hashCard() in index.html exactly."""
    import numpy as np
    g = np.asarray(im.convert("L").resize((CROP_W, CROP_H), resample=3), dtype=np.float64)   # 3 = BICUBIC
    def cells(nx, ny):
        out = np.zeros((ny, nx))
        xs = [int(i * CROP_W / nx) for i in range(nx + 1)]; ys = [int(j * CROP_H / ny) for j in range(ny + 1)]
        for j in range(ny):
            for i in range(nx):
                out[j, i] = g[ys[j]:ys[j + 1], xs[i]:xs[i + 1]].mean()
        return out
    h = cells(17, 16); v = cells(16, 17)
    bits = []
    for j in range(16):
        for i in range(16): bits.append(1 if h[j, i + 1] > h[j, i] else 0)
    for j in range(16):
        for i in range(16): bits.append(1 if v[j + 1, i] > v[j, i] else 0)
    return "".join(f"{int(''.join(map(str, bits[k:k + 4])), 2):x}" for k in range(0, 512, 4))


class _Limiter:
    """Global request pacing shared by the download threads: never more than ~8 requests per second to Scryfall."""
    def __init__(self, per_second=8.0):
        import threading
        self.gap = 1.0 / per_second; self.lock = threading.Lock(); self.next_t = 0.0
    def wait(self):
        with self.lock:
            now = time.time(); t = max(now, self.next_t); self.next_t = t + self.gap
        d = t - time.time()
        if d > 0: time.sleep(d)


def build_hashes(sets, out_path, cards_path, since=2010, workers=6):
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    if not Path(cards_path).exists():
        sys.exit(f"{cards_path} not found — run without --hash-sets first")
    with gzip.open(cards_path, "rb") as g:
        db = json.load(g)
    existing = {}
    if Path(out_path).exists():
        with gzip.open(out_path, "rb") as g:
            existing = json.load(g).get("h", {})
    log_path = Path(str(out_path) + ".log")                    # append-only progress log: survives Ctrl+C and crashes
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            p = line.strip().split(" ")
            if len(p) == 2 and len(p[1]) == 128: existing[p[0]] = p[1]
    if sets == ["all"]:
        sets = sorted({c[2] for c in db["cards"] if c[5] == "en" and (c[13] or "0000") >= f"{since}-01-01" and c[11].find("token") < 0})
        print(f"all {len(sets)} sets released since {since}")
    want = [c for c in db["cards"] if c[2] in sets and c[5] == "en" and c[0] not in existing]
    print(f"{len(want):,} images to fetch for {', '.join(sets[:12])}{'…' if len(sets) > 12 else ''} ({len(existing):,} already hashed) — about {len(want) / 7.5 / 60:.0f} min with {workers} connections; safe to stop and re-run")
    sess = requests.Session(); sess.headers.update({"User-Agent": UA["User-Agent"]})
    limiter = _Limiter(8.0)

    def one(c):
        cid = c[0]; url = f"https://cards.scryfall.io/normal/front/{cid[0]}/{cid[1]}/{cid}.jpg"
        for attempt in range(3):
            limiter.wait()
            try:
                r = sess.get(url, timeout=30)
                if r.status_code == 429: time.sleep(2 + attempt * 2); continue
                if r.status_code != 200: return cid, None
                return cid, card_hash_from_image(Image.open(io.BytesIO(r.content)))
            except Exception:
                time.sleep(1)
        return cid, None

    def save():
        with gzip.open(out_path, "wb") as g:
            g.write(json.dumps({"built": time.strftime("%Y-%m-%d"), "bits": 512, "h": existing}).encode())

    done = fails = 0; t0 = time.time()
    try:
        with open(log_path, "a") as log, ThreadPoolExecutor(max_workers=workers) as ex:
            for cid, h in ex.map(one, want):
                done += 1
                if h: existing[cid] = h; log.write(f"{cid} {h}\n")
                else: fails += 1
                if done % 100 == 0:
                    log.flush(); rate = done / max(1e-6, time.time() - t0); left = (len(want) - done) / max(rate, 1e-6)
                    print(f"  {done}/{len(want)}  {rate:.1f}/s  ~{left / 60:.0f} min left", end="\r", flush=True)
                if done % 5000 == 0: save()
    except KeyboardInterrupt:
        print("\nstopped — saving what we have; run the same command again to continue")
    save()
    try: log_path.unlink()
    except OSError: pass
    print(f"\n{len(existing):,} hashes -> {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB); {fails} failed")


def main():
    ap = argparse.ArgumentParser(description="build cardscan offline databases")
    ap.add_argument("--langs", default="en", help="comma-separated languages for cards.json.gz (default en)")
    ap.add_argument("--hash-sets", default="", help='comma-separated set codes to fingerprint (e.g. mh3,mid,clb), or "all"')
    ap.add_argument("--since", type=int, default=2010, help='with --hash-sets all: only sets released this year or later (default 2010)')
    ap.add_argument("--workers", type=int, default=6, help="parallel image downloads (default 6; total rate is capped at ~8 per second)")
    ap.add_argument("--out", default=".", help="output folder (put next to index.html)")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.hash_sets:
        build_hashes([s.strip().lower() for s in a.hash_sets.split(",") if s.strip()], out / "hashes.json.gz", out / "cards.json.gz", a.since, a.workers)
    else:
        build_cards({s.strip().lower() for s in a.langs.split(",") if s.strip()}, out / "cards.json.gz")


if __name__ == "__main__":
    main()
