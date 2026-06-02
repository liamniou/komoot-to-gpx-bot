import os
import re
import subprocess
import tempfile
import sys
import telebot


def _required_int(name: str) -> int:
    """Return the value of environment variable *name* converted to int.

    The process exits with a helpful message if the variable is missing or
    not a valid integer.  This avoids the cryptic ``ValueError`` shown in the
    logs when the container is started without setting the variable.
    """
    val = os.environ.get(name)
    if not val:
        sys.exit(f"environment variable {name!r} is required")
    try:
        return int(val)
    except ValueError:
        sys.exit(f"environment variable {name!r} must be an integer, got {val!r}")


ALLOWED_CHAT_ID = _required_int("ALLOWED_CHAT_ID")
bot = telebot.TeleBot(os.environ.get("BOT_TOKEN"))

# Optional: used only for private tours (tour/ID from saved account)
EMAIL = os.getenv("KOMOOT_EMAIL")
PASSWORD = os.getenv("KOMOOT_PASSWORD")

# Match komoot.com/tour/ID or komoot.com/smarttour/ID (query params ignored)
KOMOOT_URL_RE = re.compile(
    r"https?://(?:www\.)?komoot\.com/(tour|smarttour)/(\d+)",
    re.IGNORECASE,
)

# Rust komootgpx (cdown) for URL-based public routes; Python komootgpx for tour IDs
KOMOOTGPX_RUST = "komootgpx-rust"


def from_allowed_chat(message):
    return message.chat.id == ALLOWED_CHAT_ID


def extract_komoot(text: str) -> tuple[str | None, str | None]:
    """
    Extract (kind, id) from Komoot URL or plain numeric ID.
    kind is "tour" or "smarttour" from URL, or None for plain digit.
    """
    text = (text or "").strip()
    if not text:
        return None, None
    m = KOMOOT_URL_RE.search(text)
    if m:
        return m.group(1).lower(), m.group(2)
    if text.isdigit():
        return None, text
    return None, None


def download_gpx_via_url(url: str, output_path: str) -> bool:
    """Download GPX using Rust komootgpx (supports public smarttour/tour URLs)."""
    try:
        result = subprocess.run(
            [KOMOOTGPX_RUST, url, "-o", output_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"komootgpx (rust) stderr: {result.stderr}")
            return False
        return os.path.isfile(output_path)
    except FileNotFoundError:
        print("Rust komootgpx not found, falling back to Python")
        return False
    except subprocess.TimeoutExpired:
        print("komootgpx timed out")
        return False


def download_gpx_public(tour_id: str, output_dir: str) -> bool:
    """Download public tour as GPX via Python komootgpx (no login)."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        command = [
            "komootgpx",
            "-n",
            f"--make-gpx={tour_id}",
            f"--output={output_dir}",
            "-I",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"komootgpx stderr: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("komootgpx timed out")
        return False
    except subprocess.CalledProcessError as e:
        print(f"komootgpx error: {e.stderr}")
        return False


def download_gpx_private(tour_id: str, email: str, password: str, output_dir: str) -> bool:
    """Download tour using account (for private or saved tours)."""
    if not email or not password:
        return False
    try:
        os.makedirs(output_dir, exist_ok=True)
        command = [
            "komootgpx",
            "-m", email,
            "-p", password,
            f"--make-gpx={tour_id}",
            f"--output={output_dir}",
            "-I",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"komootgpx stderr: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("komootgpx timed out")
        return False
    except subprocess.CalledProcessError as e:
        print(f"komootgpx error: {e.stderr}")
        return False


def download_gpx_and_send_back_impl(chat_id: int, kind: str | None, tour_id: str):
    with tempfile.TemporaryDirectory(prefix="komoot_") as out_dir:
        ok = False
        if kind:
            url = f"https://www.komoot.com/{kind}/{tour_id}"
            gpx_path = os.path.join(out_dir, f"{tour_id}.gpx")
            ok = download_gpx_via_url(url, gpx_path)
        if not ok:
            ok = download_gpx_public(tour_id, out_dir)
        if not ok and EMAIL and PASSWORD:
            ok = download_gpx_private(tour_id, EMAIL, PASSWORD, out_dir)
        if not ok:
            bot.send_message(
                chat_id,
                "Could not download GPX. Try a public Komoot link (tour or smarttour) or a saved tour ID with credentials.",
            )
            return
        for name in os.listdir(out_dir):
            if name.endswith(".gpx"):
                path = os.path.join(out_dir, name)
                with open(path, "rb") as f:
                    bot.send_document(chat_id, f)
                return
        bot.send_message(chat_id, "No GPX file produced.")


@bot.message_handler(
    func=lambda m: from_allowed_chat(m) and extract_komoot(m.text or "")[1] is not None
)
def handle_komoot_url_or_id(message):
    kind, tour_id = extract_komoot(message.text)
    if not tour_id:
        return
    bot.send_message(message.chat.id, "Downloading GPX…")
    download_gpx_and_send_back_impl(message.chat.id, kind, tour_id)


@bot.message_handler(func=from_allowed_chat)
def handle_other(message):
    bot.send_message(
        message.chat.id,
        "Send a Komoot link (tour or smarttour) or a tour ID, e.g.\n"
        "• https://www.komoot.com/smarttour/10858632\n"
        "• https://www.komoot.com/tour/2792378782",
    )


if __name__ == "__main__":
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
