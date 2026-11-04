# Shirt extraction pipeline (Windows)

Drop a mockup into `Inbox\`. The script plans the layers using `rules\extraction_rules.md`,
generates each layer as a transparent PNG (3 at a time), upscales only what needs it in Topaz
Gigapixel, then waits for your OK before uploading to Google Drive and giving you a share link.

## Daily flow

1. `python run.py process "Inbox\roots shirt.jpg"` (or leave `python run.py watch` running and drop mockups in `Inbox\`).
2. The script plans the layers, generates them, and puts them in **`Ready\roots shirt\`**.
   You get a Windows pop-up, the folder opens, and (optionally) an email. The alert lists which files
   are below about 150 DPI at print size, so you know what to upscale.
3. Upscale what you want in Gigapixel and save it into the same folder. Overwrite the original, or keep both:
   when two files share the same number (e.g. `02_...png` and `02_...-gigapixel-2x.png`), the newest one is uploaded.
4. `python run.py approve "roots shirt"` uploads the folder to Google Drive as "roots shirt", sets it to
   "anyone with the link", prints the link, saves it as `DRIVE LINK.txt` in the folder and in `Work\links.csv`.

## Commands (run in Command Prompt inside the shirt-pipeline folder)

| Command | What it does |
|---|---|
| `python run.py plan-only "Inbox\shirt.jpg" "hint"` | Plans the layers only (a few cents). |
| `python run.py process "Inbox\shirt.jpg" "hint"` | Plan, generate, package into `Ready\shirt`, alert you. |
| `python run.py redo "shirt" 3 5` | Regenerates assets 3 and 5 only and replaces them in the Ready folder. |
| `python run.py approve "shirt"` | Uploads `Ready\shirt` to Drive, prints the share link. |
| `python run.py watch` | Leave running: every mockup dropped in `Inbox\` gets processed. |
| `python run.py models` | Lists the OpenAI models your account can use. |

## Email alert (optional)

Add to `.env`:
```
NOTIFY_EMAIL_TO=Cre8tiveminds242@gmail.com
GMAIL_ADDRESS=Cre8tiveminds242@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```
The app password comes from myaccount.google.com > Security > 2-Step Verification > App passwords
(2-Step Verification must be on). Never use your normal Gmail password here.

## Corrections (hints)

If the planner misreads something, add a correction after the file name:
```
python run.py plan-only "Inbox\winter.jpg" "The animal on the left is a moose. CRUSADERS is on the wearer's left sleeve."
```
For `watch` mode, save the correction as a text file with the same name as the mockup (`Inbox\winter.txt`).

## How planning works

1. **Survey**: lists every object on the shirt, then groups them into numbered assets.
2. **Review**: a second look that splits anything still bundled (e.g. "owl, moose and snowman").
3. **Prompts**: one call per asset, so each prompt describes only that asset. Words your rules ban
   (extract, isolate, mask, verify...) are replaced automatically.

## Automatic upscaling (optional, off by default)

`UPSCALE_MODE=off` (default) skips upscaling; you do it during review. `UPSCALE_MODE=manual` sorts files into
`Work\<shirt>\to_upscale\2x/4x/6x` for a Gigapixel drag-and-drop and `python run.py finish <shirt>`
collects them. `UPSCALE_MODE=cli` only works with a Gigapixel version that has a command-line tool.

## Other settings (`.env`)

```
OPENAI_API_KEY=sk-...
GIGAPIXEL_EXE=C:\Program Files\Topaz Labs LLC\Topaz Gigapixel\gigapixel.exe
PLANNER_MODEL=gpt-5.6-terra  # vision model that plans the layers
IMAGE_MODEL=gpt-image-2.5-sunburst
IMAGE_QUALITY=high           # low | medium | high
IMAGE_INPUT_FIDELITY=high    # sticks closer to the mockup; leave empty to turn off
DRIVE_PARENT_FOLDER_ID=      # optional: Drive folder ID to put every shirt folder inside
```

## Google Drive

`credentials.json` (Desktop app OAuth client) goes in this folder. The first `approve` opens a
browser to sign in. In Testing mode Google expires the sign-in after 7 days: if upload fails with
an auth error, delete `token.json` and approve again.

## Known limits

- Each layer is generated separately, so it can drift slightly from the mockup. That is what the review step is for.
- Image API refusals (e.g. look-alikes of known mascots) are reported per asset; fix the prompt in
  `Work\<shirt>\plan.json` and use `redo`.
- Real customer photos and client logos are placed by hand, per your rules.
