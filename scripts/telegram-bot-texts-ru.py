#!/usr/bin/env python3
"""Set the Russian texts of the AIVIS Telegram bot by the Bot API.

Run once on the server, after the bot's English texts are set in BotFather:

    python3 /opt/aivis/repo/scripts/telegram-bot-texts-ru.py

It reads TELEGRAM_BOT_TOKEN from the backend's env file (never printed) and sets,
for language_code "ru": the name (setMyName), the short description
(setMyShortDescription), the description above Start (setMyDescription) and the
/start command (setMyCommands). It prints one line per call: the method and
Telegram's "ok". Running it again sets the same texts again.
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_FILE = Path("/opt/aivis/repo/backend/.env")
LANG = "ru"

NAME = "AIVIS.ONE"
SHORT = "Визионер для визионеров. Ваш кабинет AIVIS.ONE: покупайте части проектов и следите за своими долями."
DESCRIPTION = (
    "AIVIS.ONE — визионер для визионеров.\n"
    "\n"
    "Ваш кабинет открывается прямо в Telegram: войдите или создайте аккаунт, "
    "покупайте части проектов и следите за своими долями.\n"
    "\n"
    "Нажмите «Старт», чтобы открыть его."
)
COMMANDS = [{"command": "start", "description": "Открыть кабинет AIVIS.ONE"}]

# Telegram's limits: name 64, short description 120, description 512, command description 256.
assert len(NAME) <= 64 and len(SHORT) <= 120 and len(DESCRIPTION) <= 512
assert all(len(c["description"]) <= 256 for c in COMMANDS)


def read_token(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            if token:
                return token
    sys.exit(f"TELEGRAM_BOT_TOKEN not found in {env_file}")


def call(token: str, method: str, params: dict) -> bool:
    data = urllib.parse.urlencode(
        {k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in params.items()}
    ).encode("utf-8")
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as error:
        answer = json.load(error)
    print(method, "ok" if answer.get("ok") else f"refused: {answer.get('description', '')}")
    return bool(answer.get("ok"))


def main() -> int:
    token = read_token(ENV_FILE)
    results = [
        call(token, "setMyName", {"name": NAME, "language_code": LANG}),
        call(token, "setMyShortDescription", {"short_description": SHORT, "language_code": LANG}),
        call(token, "setMyDescription", {"description": DESCRIPTION, "language_code": LANG}),
        call(token, "setMyCommands", {"commands": COMMANDS, "language_code": LANG}),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
