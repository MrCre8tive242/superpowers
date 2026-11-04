# Shirt extraction pipeline (Windows)

Drop a mockup into `Inbox/`. The script plans the layers (using `rules/extraction_rules.md`),
generates each layer in batches of 3, upscales only what needs it in Topaz Gigapixel, then waits
for your OK before uploading to Google Drive and giving you a share link.

## One-time setup

1. Install Python 3.11+ from python.org (tick "Add to PATH").
2. In this folder: `pip install -r requirements.txt`
3. Create a file named `.env` here:
   ```
   OPENAI_API_KEY=sk-...your key...
   GIGAPIXEL_EXE=C:\Program Files\Topaz Labs LLC\Topaz Gigapixel\gigapixel.exe
   ```
   (Keep this file private. It is git-ignored.)
4. Google Drive: in Google Cloud Console (signed in as Cre8tiveminds242@gmail.com) create a project,
   enable the Drive API, create an OAuth client of type "Desktop app", download it as `credentials.json`
   into this folder. The first upload opens a browser to sign in once.
5. Optional: put your pattern diagram at `rules/LONG_SLEEVE_PATTERN_REFERENCE.png` for cut-and-sew jobs.

## Daily use

```
python run.py watch                  # leave running; drop mockups in Inbox\
python run.py approve roots_shirt    # after you review Work\roots_shirt\final
```

Test the cheap parts first:
```
python run.py plan-only Inbox\roots_shirt.png   # writes Work\roots_shirt\plan.json, no images generated
python run.py probe-topaz                        # prints Gigapixel's CLI flags
```

## Upscale rules (edit in `.env` if needed)

- Background: 150 DPI at its print size (about 36 x 28 in) -> up to two 2x passes
- Elements: 200 DPI at about 10 in -> usually one 2x pass, or none if already big enough
- Model: `Wonder 3.5`. Topaz cloud rendering from the CLI is UNVERIFIED. If `probe-topaz`
  shows no way to pick that model, adjust `GIGAPIXEL_ARGS` or tell me what it prints.

## Known limits

- Each image call is independent, so a layer can drift slightly from the mockup. The review step exists for that.
- Real customer photos and client logos are placed by hand (per your rules); the planner prints notes.
- Image API refusals (e.g. look-alike mascots) are logged per asset and skipped, not fatal.
