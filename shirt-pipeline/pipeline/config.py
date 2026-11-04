"""Settings. Override any of these with environment variables or a .env file."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_dotenv()


def env(name, default):
    return os.environ.get(name, default)


INBOX = Path(env("INBOX_DIR", ROOT / "Inbox"))
WORK = Path(env("WORK_DIR", ROOT / "Work"))
READY = Path(env("READY_DIR", ROOT / "Ready"))   # one folder per finished shirt, named after it
RULES_FILE = Path(env("RULES_FILE", ROOT / "rules" / "extraction_rules.md"))
# Optional: the cut-and-sew pattern diagram referenced in the rules.
PATTERN_REFERENCE = Path(env("PATTERN_REFERENCE", ROOT / "rules" / "LONG_SLEEVE_PATTERN_REFERENCE.png"))

PLANNER_MODEL = env("PLANNER_MODEL", "gpt-4.1")      # vision model that reads the mockup
IMAGE_MODEL = env("IMAGE_MODEL", "auto")           # auto = newest gpt-image model your account has
IMAGE_QUALITY = env("IMAGE_QUALITY", "high")          # low | medium | high
BATCH_SIZE = int(env("BATCH_SIZE", "3"))
# "high" makes the image model stick closer to the attached mockup. Set empty to disable.
IMAGE_INPUT_FIDELITY = env("IMAGE_INPUT_FIDELITY", "high")

# Print targets
BACKGROUND_DPI = int(env("BACKGROUND_DPI", "150"))
ELEMENT_DPI = int(env("ELEMENT_DPI", "200"))
DEFAULT_ELEMENT_INCHES = float(env("DEFAULT_ELEMENT_INCHES", "10"))
# Elements are sized at least this big (longest side) so they stay sharp if you print them larger.
MIN_ELEMENT_INCHES = float(env("MIN_ELEMENT_INCHES", "8"))
MAX_UPSCALE_PASSES = int(env("MAX_UPSCALE_PASSES", "3"))
# The ready alert only flags a file for upscaling below this share of the target (0.75 x 200 = 150 DPI).
REVIEW_OK_RATIO = float(env("REVIEW_OK_RATIO", "0.75"))

# Upscale mode:
#   off    = (default) no upscaling. Finished files go to Ready\<shirt name>\, you get an alert, you upscale
#            any file you want by hand and swap it in that folder, then run: python run.py approve "<shirt name>"
#   manual = the script sorts files into Work\<shirt>\to_upscale\2x, 4x, 6x. You drag each folder into
#            Gigapixel (Wonder 3.5, cloud render, that scale), export PNGs to Work\<shirt>\upscaled,
#            then run: python run.py finish <shirt>
#   cli    = the script runs Gigapixel itself (only if your version has a working command-line tool)
UPSCALE_MODE = env("UPSCALE_MODE", "off").lower()

# Topaz Gigapixel (Windows). The command is a template; run `python run.py probe-topaz`
# to see the real flags your version supports, then adjust GIGAPIXEL_ARGS.
GIGAPIXEL_EXE = env("GIGAPIXEL_EXE", r"C:\Program Files\Topaz Labs LLC\Topaz Gigapixel\gigapixel.exe")
GIGAPIXEL_MODEL = env("GIGAPIXEL_MODEL", "Wonder 3.5")
GIGAPIXEL_ARGS = env(
    "GIGAPIXEL_ARGS",
    '--cli -i "{input}" -o "{outdir}" --scale 2 --model "{model}"',
)

# Google Drive
GOOGLE_CREDENTIALS = Path(env("GOOGLE_CREDENTIALS", ROOT / "credentials.json"))
GOOGLE_TOKEN = Path(env("GOOGLE_TOKEN", ROOT / "token.json"))
DRIVE_PARENT_FOLDER_ID = env("DRIVE_PARENT_FOLDER_ID", "")  # optional

# Extraction style policy. "auto" = decide from what the mockup shows.
#   LONG_SLEEVE_STYLE:  "cut and sew" (default: four separate pieces) | "3d" | "auto"
#   SHORT_SLEEVE_STYLE: "auto" (default: 3D unless the mockup shows panel construction) | "3d" | "cut and sew"
# Whatever you write in the hint ("3D", "cut and sew", ...) always wins over this.
LONG_SLEEVE_STYLE = env("LONG_SLEEVE_STYLE", "cut and sew").lower()
SHORT_SLEEVE_STYLE = env("SHORT_SLEEVE_STYLE", "auto").lower()

# Alerts when a shirt is ready
OPEN_FOLDER = env("OPEN_FOLDER", "1") == "1"          # open the Ready folder in File Explorer
NOTIFY_EMAIL_TO = env("NOTIFY_EMAIL_TO", "")          # optional: email address to alert
GMAIL_ADDRESS = env("GMAIL_ADDRESS", "")              # Gmail account that sends the alert
GMAIL_APP_PASSWORD = env("GMAIL_APP_PASSWORD", "")    # a Gmail "app password", not your normal password
