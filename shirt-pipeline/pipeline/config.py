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

# Who reads the mockup and writes the prompts: "claude" or "openai". Images are always made by OpenAI.
PLANNER_PROVIDER = env("PLANNER_PROVIDER", "openai").lower()
PLANNER_MODEL = env("PLANNER_MODEL", "gpt-4.1")      # e.g. claude-sonnet-5-5 / claude-opus-5-5 / gpt-5.6-terra
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
# Quality check (looks at every generated layer next to the mockup). Defaults to the planner's provider/model.
QA_ENABLED = env("QA_ENABLED", "1") == "1"
QA_PROVIDER = env("QA_PROVIDER", "").lower() or PLANNER_PROVIDER
QA_MODEL = env("QA_MODEL", "") or PLANNER_MODEL
QA_MIN_SCORE = float(env("QA_MIN_SCORE", "7"))        # 0-10: a layer below this is regenerated
QA_MAX_RETRIES = int(env("QA_MAX_RETRIES", "2"))      # extra attempts per layer after a failed check
BEST_OF_HARD = int(env("BEST_OF_HARD", "2"))          # lettering + main graphic: make this many, keep the best
IMAGE_COST_ESTIMATE = float(env("IMAGE_COST_ESTIMATE", "0.20"))  # $ per image, only used for the run log
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

# Topaz Gigapixel: not used by the pipeline (you upscale by hand). Kept only for the optional upscaler module.
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

# Hands-off: after the layers pass the check, upload to Drive and email the link without waiting for approval.
# Set AUTO_APPROVE=0 to hold every shirt for your review. Per shirt you can add --review or --auto in the hint.
AUTO_APPROVE = env("AUTO_APPROVE", "1") == "1"

# Web page
WEB_HOST = env("WEB_HOST", "127.0.0.1")               # 0.0.0.0 lets other devices (your phone over Tailscale) in
WEB_PORT = int(env("WEB_PORT", "8765"))
WEB_PASSWORD = env("WEB_PASSWORD", "")                # set this whenever WEB_HOST is not 127.0.0.1

# Alerts when a shirt is ready
OPEN_FOLDER = env("OPEN_FOLDER", "1") == "1"          # open the Ready folder in File Explorer
NOTIFY_EMAIL_TO = env("NOTIFY_EMAIL_TO", "")          # optional: email address to alert
GMAIL_ADDRESS = env("GMAIL_ADDRESS", "")              # Gmail account that sends the alert
GMAIL_APP_PASSWORD = env("GMAIL_APP_PASSWORD", "").replace(" ", "")  # a Gmail "app password" (spaces are ignored)
