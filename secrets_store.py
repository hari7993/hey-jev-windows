"""Her API keys, kept in Windows Credential Manager. A .env file next to the code wins over it, which is handy while
developing.

Only free services: OpenCode Zen and Kilo Gateway (answers, free models only) and Fish Audio (her voice, free model).
"""
import os

import keyring
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))  # works from the shortcut too

SERVICE = "Hey Jev"  # shows up in Credential Manager > Windows Credentials
KEY_NAMES = ("OPENCODE_ZEN_API_KEY", "FISH_AUDIO_API_KEY", "KILO_API_KEY", "TELEGRAM_BOT_TOKEN")
# Kilo Gateway's free models, besides OpenCode's (see opencode.py); your own Telegram bot, for your phone
OPTIONAL = ("KILO_API_KEY", "TELEGRAM_BOT_TOKEN")
ALIASES = {"OPENCODE_ZEN_API_KEY": ("OPENCODE_API_KEY",)}  # the name OpenCode's own docs use


def vault_value(name):
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def get_secret(name):
    """The key: from the environment or .env first, so editing .env always takes effect, else Credential Manager."""
    found = next((os.environ[n] for n in (name, *ALIASES.get(name, ())) if os.environ.get(n)), None)
    return found or vault_value(name)


def save_secret(name, key):
    """Keeps a key pasted in the Keys tab. A blank box changes nothing."""
    if KEY_NAMES.count(name) == 0:
        raise ValueError(f"{name} isn't one of her keys")
    key = (key or "").strip()
    if key:
        try:
            keyring.set_password(SERVICE, name, key)
        except Exception as exc:
            raise RuntimeError(f"Could not save to Credential Manager: {exc}")


def missing_secrets():
    """The keys she can't start without and doesn't have yet."""
    return [n for n in KEY_NAMES if n not in OPTIONAL and not get_secret(n)]
