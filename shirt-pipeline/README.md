# Shirt extraction pipeline (Windows)

Drop in a shirt mockup. It plans the layers with your extraction rules, makes each layer, **checks every layer
against the mockup and redoes the bad ones**, packages them in `Ready\<shirt name>\`, uploads to Google Drive,
and emails you the share link with a preview sheet. Nothing to click unless something needs a look.

Full setup steps: see **Setup-Guide.pdf**.

## Everyday use

One program does everything: **`python run.py serve`** (or let Windows start it for you:
`python run.py install-autostart`). Then use either door:

- **The web page**: http://localhost:8765 (a desktop shortcut is created). Drag a mockup in. Pick a style or leave it on Auto.
- **The Inbox folder**: drop the mockup in `Inbox\` (point `INBOX_DIR` at a Google Drive folder and you can upload from your phone).

Shirt name = the file name. Add corrections after ` -- ` in the file name: `roots shirt -- the animal on the left is a moose.jpg`.

## What happens to each shirt

1. **Style is chosen from the mockup** (3D all-over vs cut and sew). Long sleeve = cut and sew (four background pieces:
   front body, back body, left sleeve, right sleeve). The log says why. Your notes override ("3D", "cut and sew").
2. **Planning** (Claude or GPT, your choice): lists every layer, exact lettering, sizes. Scenery stays in the background.
3. **Making + checking**: each layer is generated, then a vision model compares it with the mockup (spelling, missing
   parts, stray elements, backdrop, edges). Failed layers are redone with the checker's feedback (up to 2 times).
   Lettering and the main graphic are made twice and the better one is kept. Cut and sew pieces match the front body piece.
4. **Packaging**: files go to `Ready\<shirt>`; a preview sheet is built (green = ok, amber = check edges, red = needs a look).
5. **Hands-off**: uploads to Drive, shares the link, emails you the link + preview + a list of anything that needs a look
   and which layers are below the print target and may need an upscale.

## Your part: review, upscale, swap

Upscale what you want in Gigapixel and save it into the same `Ready\<shirt>` folder (overwrite, or keep both: the newest
file per number wins). Then click **Update Drive with my changes** on the web page (or `python run.py approve "<shirt>"`).
The Drive link stays the same.

## Commands

| Command | What it does |
|---|---|
| `python run.py serve` | Inbox watcher + web page (the normal way to run it) |
| `python run.py process "Inbox\x.jpg" [notes]` | One mockup right now |
| `python run.py plan-only "Inbox\x.jpg" [notes]` | Just the plan, no images (cheap) |
| `python run.py redo "x" 3 5` | Remake layers 3 and 5 (same Drive link) |
| `python run.py approve "x"` | Upload or update Drive, email the link |
| `python run.py models` | Lists the OpenAI models your account can use |
| `python run.py test-email` | Sends yourself a test email |
| `python run.py install-autostart` | Start by itself at Windows login |

## Settings

Copy `.env.example` to `.env`. Everything has a default except the keys. The most useful ones:
`PLANNER_PROVIDER` / `PLANNER_MODEL` (claude or openai), `IMAGE_MODEL`, `AUTO_APPROVE` (0 = wait for your approval),
`BEST_OF_HARD` (1 = cheaper), `QA_MAX_RETRIES`, `LONG_SLEEVE_STYLE`, `INBOX_DIR`.
Add `--review` to the notes of one shirt to hold just that one for approval.

## Phone access

- **Easiest:** upload the mockup to the Drive folder that `INBOX_DIR` points to. Your PC must be on. The email arrives with the link.
- **The web page from your phone:** install Tailscale (free) on the PC and phone, set `WEB_HOST=0.0.0.0` and a `WEB_PASSWORD`,
  and open `http://<pc-tailscale-name>:8765`. Never expose the page to the open internet without a password.

## Where things are

`Ready\<shirt>` the print files and Drive link · `Work\<shirt>` plan, quality results, preview sheet, rejected attempts ·
`Work\log.csv` one row per shirt (date, style, images made, estimated cost, link) · `Work\pipeline.log` when it runs hidden ·
`Inbox\Done` and `Inbox\Failed` the mockups after they run.

## Known limits

- The quality check is another AI. It catches most spelling and stray-element mistakes but not everything. Glance at the preview sheet.
- Real customer photos and client logos are placed by hand, per your rules.
- The image API may refuse some look-alikes of known mascots; the layer is flagged and you can adjust it and use Redo.
- The pipeline only runs while the PC is on and the program is running.
