# Shirt Pipeline: the Complete Workflow

This document explains the finished workflow from end to end: what you do, what the system does, what comes
out, and what stays in your hands. It describes the system as built and pushed on branch
`ccr-b7e053bd-hk7g02`.

> **Setup steps** (keys, email, Drive) are in `Setup-Guide.pdf`. **Command reference** is in `README.md`.
> This file is the "how it all fits together" explanation.

---

## 1. The idea in one paragraph

You give the system a shirt mockup. It works out what kind of shirt it is, breaks the design into separate
print-ready layers following your Cre8tive Minds extraction rules, draws each layer, checks every layer against
your mockup (and redraws the bad ones), packages everything into a named folder, uploads that folder to Google
Drive, makes the link shareable, and emails you the link with a preview sheet. You then only do the human parts:
glance at the preview, upscale what needs it, and send the link to the customer.

```
 YOU                                 THE SYSTEM
 ---                                 ----------
 drop a mockup  ───────────────►  1. Decide the style (3D vs cut and sew)
 (web page, Inbox folder,         2. Plan the layers (Claude or GPT, using your rules)
  or phone → Google Drive)        3. Draw each layer (OpenAI image model)
                                  4. Check each layer, redo bad ones (up to 2x)
                                  5. Package into  Ready\<shirt name>\
                                  6. Upload to Drive + share link
 read the email  ◄───────────────  7. Email: link + preview sheet + "needs a look" list
 upscale what needs it
 click "Update Drive"  ─────────►  8. Sync changed files, SAME link
 send the link to the customer
```

---

## 2. Ways to start a shirt

All three doors feed the same queue. Shirts are processed one at a time, in order.

| Door | How | Best for |
|---|---|---|
| **Web page** | Open `http://localhost:8765` (desktop shortcut). Drag the mockup in, optionally pick a style and type corrections. | Working at your PC |
| **Inbox folder** | Drop the image in `Inbox\`. | Batch dropping, automation |
| **Phone** | Upload the image to the Google Drive folder that `INBOX_DIR` points to. It syncs to your PC and starts by itself. | Away from your desk (PC must be on) |

**The shirt's name is the file name.** `roots shirt.jpg` becomes the shirt `roots shirt`, the folder
`Ready\roots shirt\`, and the Drive folder `roots shirt`.

**Corrections go after ` -- ` in the file name**, handy from a phone:
`roots shirt -- the animal on the left is a moose.jpg`. On the web page, use the Corrections box instead.

**One-shirt switches** (in the corrections): `3D`, `cut and sew`, `long sleeve`, `short sleeve`, `--review`
(hold this shirt for my approval) or `--auto`.

---

## 3. Step 1: Deciding the extraction style

Your rules define two styles that produce different **background** files. The system picks one automatically,
in this order of authority:

1. **What you wrote.** "3D", "all-over" or "sublimation" means 3D. "Cut and sew", "panels" or "pattern pieces"
   means cut and sew. "Long sleeve" / "short sleeve" overrides the sleeve length it sees.
2. **Your standing policy** (`.env`):
   - `LONG_SLEEVE_STYLE=cut and sew`: every long-sleeve shirt becomes cut and sew.
   - `SHORT_SLEEVE_STYLE=auto`: short sleeve is 3D, unless the mockup visibly shows panel construction
     (seams, a contrasting collar, side panels), then it becomes cut and sew.
3. **What the mockup shows.** A vision model describes the sleeve length and construction. If the sleeve length
   is unclear, short sleeve is assumed and the log says so.

The log always states the choice and the reason, for example:
`Mode: cut and sew long sleeve <- long sleeves seen in the mockup; your policy for long sleeves is cut and sew`.

### What each style produces

| | **3D all-over** | **Cut and sew** |
|---|---|---|
| Background files | **One** flat shirt-shaped file per printed side shown, sleeves attached | **Four** separate files |
| Pieces | Single piece with the required "one continuous design, no sleeve patterns, no seam lines" wording | Front body, back body, left sleeve, right sleeve |
| Sizes | about 44 x 36 in | Body 22 x 28 in. Sleeves 17 x 25 in (long) or 17 x 9 in (short) |
| Pattern diagram | Not used | Your `LONG_SLEEVE_PATTERN_REFERENCE.png` is sent with every piece |

Sleeves are named by the **wearer's** side. In 3D mode there is never a separate sleeve background. In cut and
sew mode there are always exactly four, built by the program (not left to the AI's judgement).

---

## 4. Step 2: Planning the layers

The planner reads the mockup together with your full extraction rules file and decides what the layers are.
It runs in three stages so layers cannot be merged by accident:

1. **Survey.** List every distinct object on the shirt, then group them into numbered assets in your rules' order
   (lettering first, main graphic, supporting elements, sleeve elements, edge decorations, backgrounds last).
2. **Review.** A second look that can only *split* bundled items (for example "owl, moose and snowman" becomes
   three assets). It never merges.
3. **Prompts.** One separate call per asset writes that asset's finished image prompt, following your rules'
   prompt structure. Words your rules ban inside image prompts (extract, isolate, mask, verify, and so on) are
   automatically replaced.

**What stays inside the background (never its own layer):** sky, aurora, stars, clouds, mountains, forests and
trees, waterfalls, snow ground, textures, patterns, splatter and scattered snowflakes. A distinct object placed on
top of the design (a badge, crest, logo) is still its own asset.

Each layer records its **exact text** (letter for letter), its **printed size in inches** (elements are planned
at 8 in or larger on the long side so they stay sharp), and whether it is a **hard layer** (lettering and the main
graphic).

The planner can be **Claude or GPT**, chosen in `.env` (`PLANNER_PROVIDER`, `PLANNER_MODEL`).

---

## 5. Step 3: Drawing and checking every layer

This is where most of the quality comes from. Each layer goes through:

```
generate ─► quality check ─► passed? ─ yes ─► keep
   ▲              │
   │              no
   └── redraw with the checker's feedback (up to 2 more tries)
```

### Drawing
- The image model is OpenAI's (default `gpt-image-2.5-sunburst`), with the mockup attached as the reference and
  a transparent background requested.
- Layers are drawn in batches of 3, like typing "continue" in your old process.
- **Hard layers (lettering and the main graphic) are drawn twice**, and the better one is kept
  (`BEST_OF_HARD=2`).
- **Cut and sew continuity:** the front body piece is drawn first. The back and both sleeves are then drawn with
  the finished front piece attached as a reference, so the art, colors and flow match across all four.

### The quality check
Every drawn layer is shown to a vision model next to the mockup, with transparent areas shown as flat gray so
leftover backdrops and fringes are visible. The checker scores it 0 to 10 and looks for:

- **Text.** It transcribes what it sees and the program compares that to the exact expected text. A single wrong
  letter fails the layer.
- **Completeness.** Nothing cut off; parts hidden in the mockup were rebuilt.
- **Only this layer.** No other elements, shirt, model, mannequin, collar, seams, wrinkles, shadows, collage or
  duplicates. For backgrounds: no lettering, animals or props left in them.
- **Faithfulness.** Colors, shapes, style and proportions match the mockup.
- **Edges.** Clean cut, no leftover backdrop.

The program also checks pixels directly: no transparent area, a solid backdrop behind the artwork, or a light
halo around the edges. A solid white or black backdrop is **removed automatically**; a halo is flagged for your eye.

**Passing** means a score of 7 or higher with no hard problems (`QA_MIN_SCORE`). A failed layer is redrawn with
the checker's one-sentence fix added to the prompt, up to `QA_MAX_RETRIES=2` more times. If it still fails, the
best attempt is kept and the layer is **flagged red** instead of silently passed.

If the checker itself cannot run (network trouble), the layer is marked "not checked" and the job continues.

### Status colors you will see
| Color | Meaning |
|---|---|
| Green | Passed the check |
| Amber | Passed, but check the edges (possible halo) |
| Red | Still failing after retries, or missing. Needs your eye or a Redo |
| Gray | Not checked |

---

## 6. Step 4: Packaging

Finished layers are copied into **`Ready\<shirt name>\`** with numbered names that follow your rules' order:

```
Ready\roots shirt\
    01_winter_is_coming_lettering.png
    02_snow_leopards.png
    03_moose.png
    04_snowy_owl.png
    05_snowman.png
    06_crusaders_sleeve_lettering.png
    07_front_body_background.png      (cut and sew: four pieces, last)
    08_back_body_background.png
    09_left_sleeve_background.png
    10_right_sleeve_background.png
    DRIVE LINK.txt                    (added after upload)
```

A **preview sheet** is also made: one image with every layer on a checkerboard, labeled, with a colored status
bar per layer (and "upscale ~2.1x" where a layer is below the print target). It is saved in `Work\<shirt>\`
and attached to the email.

**Upscale guidance, not upscaling.** The system does **not** upscale. For each layer it works out the real pixel
size of the artwork against its printed size, and flags layers under about 150 DPI (printing targets: 150 DPI for
backgrounds, 200 DPI for elements). Elements usually need one 2x pass; a 44-inch 3D background needs about 4 to 5x.

---

## 7. Step 5: Hands-off finish

With the default `AUTO_APPROVE=1`, nothing waits for you:

1. **Upload.** The folder is created in Google Drive under the shirt's name.
2. **Share.** The folder is set to "anyone with the link can view".
3. **Alert.** You get:
   - a **Windows pop-up**,
   - an **email** to Cre8tiveminds242@gmail.com with the **share link** (at the top), a one-glance summary,
     the **preview sheet attached**, and a list of anything that needs attention,
   - the **web page** updated with the link and a Copy button.
4. **Log.** A row is added to `Work\log.csv` with the date, shirt, style, layers, images made, estimated cost and link.

The email subject tells you the state at a glance: **"Shirt ready: roots shirt"** or
**"CHECK NEEDED: roots shirt"** (some layer is red).

The link goes only to you. **Nothing reaches the customer until you send it.**

### Review mode (optional)
Set `AUTO_APPROVE=0`, or tick **Hold this shirt for my review** on the web page, or add `--review` to one shirt's
corrections. The system packages the files and emails you but does **not** upload. When you are happy, click
**Approve and upload to Drive** or run `python run.py approve "roots shirt"`.

---

## 8. Your part: review, upscale, swap

This is the human part, and it is deliberately light.

1. **Read the email** (or open the web page). Look at the preview sheet.
2. **Fix anything red or amber.** Click **Redo** under that layer on the web page (or
   `python run.py redo "roots shirt" 4`). Only that layer is remade; the Drive link does not change.
3. **Upscale what the list says.** Open the file from `Ready\<shirt>\` in Gigapixel (Wonder 3.5, cloud render,
   your usual settings) and save the result **into the same folder**. You can overwrite the original or keep both.
   When two files share a number, for example `02_snow_leopards.png` and
   `02_snow_leopards-gigapixel-wonder-2x.png`, **the newest one wins**.
4. **Click "Update Drive with my changes"** (or `python run.py approve "roots shirt"`). Only changed files are
   uploaded; the old copy is moved to Drive's trash; **the share link stays exactly the same**, so a link you
   already sent keeps working.
5. **Send the link to the customer.**

---

## 9. Working away from your computer

The pipeline runs on your PC, so **the PC must be on** with the program running (it starts by itself at login
once you run `python run.py install-autostart`).

| Need | How |
|---|---|
| Start a shirt from your phone | Upload the photo to the Google Drive folder set as `INBOX_DIR`. Add corrections in the file name after ` -- `. |
| Know it finished | The email arrives on your phone with the link and the preview sheet. |
| Open the web page from your phone | Install Tailscale (free) on PC and phone, set `WEB_HOST=0.0.0.0` and a `WEB_PASSWORD`, then open `http://<pc-name>:8765`. |
| Fix a layer or sync your upscale from the phone | Only through the web page over Tailscale. Upscaling itself needs Gigapixel on the PC. |
| Run with the PC off | Not supported. It would need the program moved to a small cloud server (a possible later step). |

---

## 10. When something goes wrong

- **A layer fails the check repeatedly:** it is kept and flagged red. Use Redo, or add a correction naming the
  problem and run the shirt again.
- **The image API refuses a layer** (for example a look-alike of a known mascot): that layer is marked failed with
  the reason; the others continue. Adjust and Redo.
- **The image model is wrong or unavailable, a key is missing, or billing stops:** the run stops immediately with a
  plain message instead of failing every layer, and you get a **"FAILED"** pop-up and email.
- **Drive upload fails:** the shirt is still packaged and emailed; the email says the upload failed and how to retry
  (`python run.py approve "<shirt>"`).
- **Wrong style chosen:** add `3D` or `cut and sew` to the corrections and run it again. Never write "3D" for a
  shirt that should be cut and sew.
- **Mockups that fail** are moved to `Inbox\Failed`; finished ones to `Inbox\Done`, so nothing is processed twice.
- **Typing mistakes** (a wrong file name) just print a message; they do not send failure emails.

---

## 11. Where everything lives

| Path | What |
|---|---|
| `Inbox\` | Drop mockups here (or point `INBOX_DIR` at a Google Drive folder) |
| `Inbox\Done`, `Inbox\Failed` | Mockups after they have run |
| `Ready\<shirt>\` | **The print files** and `DRIVE LINK.txt`. This is the folder you review and upscale in |
| `Work\<shirt>\plan.json` | The plan: style and why, every layer, exact text, sizes, prompts |
| `Work\<shirt>\qa.json` | The quality result per layer |
| `Work\<shirt>\preview.jpg` | The preview sheet |
| `Work\<shirt>\raw\` | First-draft images and, in `_attempts\`, every rejected try |
| `Work\log.csv` | One row per shirt: style, images made, estimated cost, link |
| `Work\pipeline.log` | Activity log when the program runs hidden at login |
| `rules\extraction_rules.md` | Your extraction rules, read for every shirt |
| `rules\LONG_SLEEVE_PATTERN_REFERENCE.png` | Your cut and sew pattern diagram |
| `.env` | Your keys and settings. **Private; never share it** |

---

## 12. Settings that matter (`.env`)

| Setting | Default | What it does |
|---|---|---|
| `PLANNER_PROVIDER` / `PLANNER_MODEL` | `openai` / `gpt-4.1` (`.env.example` suggests `claude` / `claude-sonnet-5-5`) | Who plans and checks |
| `IMAGE_MODEL` | `auto` (set to `gpt-image-2.5-sunburst`) | Which OpenAI model draws |
| `IMAGE_QUALITY` | `high` | `low`, `medium`, `high` |
| `AUTO_APPROVE` | `1` | `1` hands-off, `0` always wait for approval |
| `LONG_SLEEVE_STYLE` / `SHORT_SLEEVE_STYLE` | `cut and sew` / `auto` | Standing style policy |
| `BEST_OF_HARD` | `2` | Draw lettering and main graphic this many times, keep the best (`1` saves money) |
| `QA_MIN_SCORE` / `QA_MAX_RETRIES` | `7` / `2` | How strict, and how many redraws |
| `BACKGROUND_DPI` / `ELEMENT_DPI` | `150` / `200` | Print targets used for the upscale guidance |
| `INBOX_DIR` | `Inbox\` | Set to a Google Drive folder for phone uploads |
| `NOTIFY_EMAIL_TO`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | empty | Email alerts |
| `WEB_HOST` / `WEB_PASSWORD` / `WEB_PORT` | `127.0.0.1` / empty / `8765` | Web page access |

---

## 13. What it costs

| Item | Roughly |
|---|---|
| Image generation | Dominant cost. With best-of-two on hard layers and occasional redraws, expect about 12 to 18 images per shirt instead of 9. `Work\log.csv` records an estimate per shirt (`IMAGE_COST_ESTIMATE`, default $0.20 per image, adjust to your model's real price) |
| Planning and quality check | A few cents to well under a dollar per shirt, depending on the model |
| Google Drive | Free to 15 GB (shared with Gmail). Print files are large, so a small paid plan may eventually be needed |
| Web page, Tailscale, Windows auto-start | Free |

To spend less: set `BEST_OF_HARD=1`, use `IMAGE_QUALITY=medium` for simple designs, or lower `QA_MAX_RETRIES`.

---

## 14. What it does not do (by design)

- **It does not upscale.** You do that, in Gigapixel, only on the layers that need it.
- **It does not send anything to the customer.** The link comes to you first.
- **It does not place real photos, client logos or official crests.** Your rules say to place those by hand. The
  planner notes them.
- **It is not a guarantee.** The quality check is another AI. It catches most spelling mistakes, stray elements
  and backdrop problems, but not everything. The preview sheet exists so a human glance takes seconds.
- **It does not run with the PC off.**

---

## 15. The workflow at a glance

```
Mockup in (web page / Inbox / phone → Drive)
   │
   ▼
Decide style ── your words > your policy > what the mockup shows
   │
   ▼
Plan layers ── survey → split review → one prompt per layer (Claude or GPT)
   │
   ▼
Draw layers ── 3 at a time; hard layers x2; cut and sew pieces match the front body
   │
   ▼
Check each layer ── text, completeness, stray items, backdrop, edges
   │      └─ fail → redraw with feedback (max 2) → still failing = flagged red
   ▼
Package ── Ready\<shirt>\  +  preview sheet  +  upscale guidance
   │
   ▼
Upload + share link ── Google Drive, anyone with the link
   │
   ▼
Email + pop-up ── link, preview, "needs a look" list
   │
   ▼
YOU: glance → Redo any red layer → upscale what's listed → "Update Drive" (same link) → send the link
```
