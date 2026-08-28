# cardscan

A phone scanner for Magic cards that identifies the exact printing, prices it instantly from an offline database, sorts cards into lists, and tells you out loud when it finds something worth money — or when it couldn't read a card.

Files:
- `index.html` — the phone app. Put it on GitHub Pages (steps below).
- `sw.js` — optional; upload it next to index.html and the app opens and scans with no signal (the vision library and databases are kept on the phone).
- `tesseract.min.js`, `tesseract-worker.min.js`, `tesseract-core-simd-lstm.wasm.js`, `eng.traineddata` — the on-phone text reader (about 8 MB together). Upload them next to index.html; without them the reader loads from a CDN instead.
- `opencv.js` — the vision library the app loads (card detection). Upload it next to index.html.
- `build_db.py` — laptop script that builds the offline databases the app uses: `cards.json.gz` (every printing with TCGplayer / Cardmarket prices, rarity, variant, artist, oracle text) and `hashes.json.gz` (image fingerprints for the sets you own, for instant offline identification).
- `cardscan.py` — the older laptop batch scanner (photos → xlsx). Optional.
- `detect.js` — source of the card detector that is inlined into index.html.

## Install (≈10 minutes, free)

1. **Host the app.** On github.com: **+** → New repository → name `cardscan` → Public → Create. Click *uploading an existing file*, add `index.html` **and `opencv.js`** (the vision library, 13 MB — hosting it yourself makes the load fast and reliable; without it the app falls back to a CDN), commit. Then **Settings → Pages** → Source *Deploy from a branch* → `main` / `/ (root)` → Save. Your address: `https://YOURNAME.github.io/cardscan/`
2. **Build the databases** (laptop, once, then whenever you want fresh prices):
   ```
   pip install requests pillow numpy
   python build_db.py                          # -> cards.json.gz  (downloads ~500 MB from Scryfall, writes ~6 MB)
   python build_db.py --hash-sets mh3,mid,clb  # -> hashes.json.gz (set codes you own; ~30 s per set)
   ```
   Upload both `.gz` files to the same GitHub repo, next to `index.html`.
3. **On the phone:** open your address, *Add to Home Screen* (iPhone: Share menu; Android Chrome: ⋮ menu). In **Settings**, paste an Anthropic API key (console.anthropic.com → API Keys) and tap **Update database**. The key stays on the phone and is only used for cards the fingerprints don't recognize.

Re-run step 2 and tap **Update database** when you want new prices; **Re-price inventory** then updates every card you've scanned and shows what moved.

## Scanning

**📷 Scan cards** opens the camera. Two modes, switch at the top:
- **One at a time** — hold the phone over a card and keep still for about a second: it snaps by itself (an outline locks when it can see the card edges; if it can't, it takes the guide area once the view is steady and sharp). **📸 Snap** takes one right now. On Android it uses a full-resolution photo, which makes the small bottom-left printing readable. Lift the card and place the next; the same card placed again counts as another copy (×2, ×3…), but a card that just sits there is not re-added.
- **Sweep** — move the phone slowly over a spread of cards. Every card gets an outline and a label, colour-coded:
  - **green** — identified and priced
  - **gold** — priced at or above your threshold (it beeps twice and says the name, price and where it is)
  - **orange** — identified, but the price is missing or the exact printing is unsure (tap to pick)
  - **red** — unknown (double low beep, "Unknown card, looks blue, bottom right")
  - **✓ grey** — a card you already scanned this session, shown but not re-added
  Two identical cards lying side by side count as two copies; the same card seen again after you moved away is not counted twice. Tap any outlined card to open it.
- **Cards (N)** opens a scrollable list of everything scanned this session, with − / + copy counts; **Undo** removes the last capture; **+1 same** adds a copy of the last card.
- **Photos** — the older batch mode (8–16 cards per photo) still works from the same screen, with the same colours.

**Identification is fingerprints first, then reading the card's text on the phone, and AI only when you ask.** When a fingerprint doesn't match, the phone reads the card's name (then the type line if the name is a close call, then the bottom line for the set code) and matches it against the price database — free, offline, about a second. Rows identified this way show *read*. Anything still unknown becomes a red row with its picture saved; tap it and you get: the names the reader thinks it saw (tap one), the closest fingerprint pictures (tap one), or type two letters of the name. Then, if several printings exist, **type the number from the bottom-left of the card** — the matching printing is picked the moment it's unique. **Identify with AI (about 1¢)** is there for the genuinely hard ones, and the results panel can send all unknowns at once. Nothing is sent to the API unless you press one of those buttons.

**Camera** (bottom bar) shows a live sharpness meter and, on phones that allow it (Android Chrome), sliders for focus, exposure and zoom plus **Auto-tune focus**: hold the phone at your scanning height, tap it, and it sweeps the focus range, picks the sharpest setting and locks it — no more hunting. The setting is remembered. iPhone browsers don't allow manual focus; there the fix is a fixed distance (a phone stand) and a light background.

**Settings** also has *Fingerprint matching* (strict / normal / loose) and, under *Offline database*, a coverage line that lists which of your inventory's sets still lack fingerprints, with the exact `build_db.py --hash-sets …` command to run.

## Inventory

- Every card stores the exact printing, finish, variant (retro / showcase / borderless / promo…), rarity, artist, release date, oracle text, TCGplayer market and Cardmarket prices, price at scan vs now, the Scryfall image, condition (NM/LP/MP/HP/DMG with an adjusted value), your note, list, and how it was identified.
- Tap a card for its picture and details, to change printing / foil / condition / list / copies, or delete. **Select** turns on checkboxes for moving, re-grading or deleting many cards at once; **Sort** by price, newest, name or set; rows show the card image.
- **Lists** are your piles (Box 3, Trade binder, Sell…). Pick one before scanning; the threshold auto-sort can route the hits to a different list. **Group by** list, price tier, color, type, rarity, set or condition; **search** anything.
- **Export** menu: CSV or Excel of everything (Excel: one tab for everything, one for the hits, one per list); **ManaBox**, **Moxfield** and **Deckbox** CSV files ready to import into those apps, identical cards stacked with quantities; and a **Backup file** (inventory + learned fingerprints + settings, without the API key). **Restore from a backup file** merges or replaces — do this when you change phones or clear browser data.
- **＋ Add a card by name** for sleeved, damaged or otherwise unscannable cards: type a few letters, pick the printing (or type its number), done.
- **Import a ManaBox / TCGplayer CSV** brings an existing collection in (name, set, number, foil, quantity, condition are read; anything not found becomes a red row to fix).
- **Summary** also shows set completion — how many of each set's printings you own.
- **stack copies** collapses identical cards (same printing, finish, condition) into one line with ×N. **Summary** shows totals, value by list, tier counts and your top 10. **Delete this scan** removes everything from the last scan in one tap. The 🔊 button in the camera view mutes beeps and voice.

## Prices — what they are

TCGplayer *market* (USD) and Cardmarket *trend* (EUR) as published by Scryfall, refreshed whenever you rebuild the database. ManaBox has no price feed of its own — it shows the same TCGplayer/Cardmarket numbers — so this is the ManaBox price. Buylist (what a store pays) is usually 40–60% of market.

## Limits and honest notes

- The live camera path, the API calls and the real database download could not be exercised in the environment this was built in; the logic was tested in a simulated browser with recorded card images. First real use may need tuning — the error text on screen is the thing to send back.
- Fingerprints work best for normal-frame cards on a light background; showcase/borderless printings and heavy glare fall back to Claude.
- Sweep mode reads at the camera's live resolution, so collector numbers are read less often than in a photo; the "N printings" flag and the tap-to-pick list cover that.
- Storage is the phone's browser storage — export before clearing site data or switching phones.
