# Shirt extraction pipeline (Windows)

Drop a mockup into `Inbox\`. The script plans the layers using `rules\extraction_rules.md`,
generates each layer as a transparent PNG (3 at a time), upscales only what needs it in Topaz
Gigapixel, then waits for your OK before uploading to Google Drive and giving you a share link.

## Commands (run in Command Prompt inside the shirt-pipeline folder)

| Command | What it does |
|---|---|
| `python run.py plan-only "Inbox\shirt.jpg"` | Plans the layers only (a few cents). Check the list first. |
| `python run.py process "Inbox\shirt.jpg"` | Plan, generate, upscale. Stops for your review. |
| `python run.py redo shirt 3 5` | Regenerates assets 3 and 5 only (after a bad or refused image). |
| `python run.py approve shirt` | Uploads `Work\shirt\final` to Drive, prints the share link. |
| `python run.py watch` | Leave running: every mockup dropped in `Inbox\` gets processed. |
| `python run.py probe-topaz` | Shows Gigapixel's command-line options (or lists the .exe files it finds). |

Put the file name in quotes when it has spaces. The shirt name used by `redo`/`approve` is the
file name in lowercase with spaces turned into `_` (e.g. `roots shirt.jpg` -> `roots_shirt`).

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

## Upscale rules (change in `.env`)

- Background: `BACKGROUND_DPI=150` at its print size. Elements: `ELEMENT_DPI=200`.
- Passes of 2x until the visible artwork (transparent margins ignored) reaches the target, then any
  overshoot is trimmed back down so files stay a sensible size. `MAX_UPSCALE_PASSES=3`.
- Gigapixel command: `GIGAPIXEL_ARGS` (default `--cli -i "{input}" -o "{outdir}" --scale 2 --model "{model}"`)
  is UNVERIFIED until we see `probe-topaz` output.

## Other settings (`.env`)

```
OPENAI_API_KEY=sk-...
GIGAPIXEL_EXE=C:\Program Files\Topaz Labs LLC\Topaz Gigapixel\gigapixel.exe
PLANNER_MODEL=gpt-4.1        # try a stronger vision model if splitting is still weak
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
