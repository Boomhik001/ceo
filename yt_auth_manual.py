#!/usr/bin/env python3
"""Ручной (headless) OAuth для YouTube Data API v3.

В контейнере нет браузера, поэтому flow запускается в два такта:

  1) python3 yt_auth_manual.py step1
     -> печатает ссылку consent. Открой её в своём браузере, выбери аккаунт,
        нажми «Разрешить». Браузер покажет страницу вида
        http://localhost:PORT/code?code=XXXX  (ERR_CONNECTION_REFUSED — это нормально).
        Скопируй из адресной строки значение параметра code=... и пришли мне.

  2) python3 yt_auth_manual.py step2 "<КОД>"
     -> меняет код на access+refresh токен, сохраняет state/yt_token.json.
        После этого публикация работает без браузера (refresh-токен не живой).

Порт редиректа фиксируется в state/yt_oauth_port.txt между шагами.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLIENT_SECRET = BASE / "client_secret.json"
TOKEN_PATH = BASE / "state" / "yt_token.json"
PORT_PATH = BASE / "state" / "yt_oauth_port.txt"
REDIRECT_PORT = 8765

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _flow():
    from google_auth_oauthlib.flow import Flow

    if not CLIENT_SECRET.exists():
        sys.exit(f"Не найден {CLIENT_SECRET.name}")
    return Flow.from_client_secrets_file(
        str(CLIENT_SECRET), scopes=SCOPES,
        redirect_uri=f"http://localhost:{REDIRECT_PORT}/code",
    )


def step1() -> None:
    PORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PORT_PATH.write_text(str(REDIRECT_PORT))
    flow = _flow()
    url, _state = flow.authorization_url(prompt="consent", access_type="offline",
                                         include_granted_scopes="true")
    print("ОТКРОЙ ЭТУ ССЫЛКУ В БРАУЗЕРЕ:\n")
    print(url)
    print("\nПосле «Разрешить» скопируй из адресной строки значение code=... ")
    print("и выполни: python3 yt_auth_manual.py step2 \"<код>\"")


def step2(code: str) -> None:
    flow = _flow()
    flow.fetch_token(code=code)
    cred = flow.credentials
    TOKEN_PATH.write_text(cred.to_json(), encoding="utf-8")
    print(f"OK: токен сохранён в {TOKEN_PATH}")
    print("refresh_token получен:", bool(cred.refresh_token))
    print("проверка канала: python3 yt_direct.py whoami")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "step1":
        step1()
    elif args[0] == "step2" and len(args) > 1:
        step2(args[1])
    else:
        sys.exit("использование: yt_auth_manual.py step1 | step2 \"<код>\"")
