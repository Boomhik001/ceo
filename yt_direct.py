#!/usr/bin/env python3
"""Прямая публикация видео в YouTube через официальный Data API v3 (без Upload-Post).

Сценарий:
  1) создай OAuth Client ID типа "Desktop app" в Google Cloud Console,
     скачай JSON и положи рядом как client_secret.json
  2) python3 yt_direct.py auth            -> откроется браузер, подтверди доступ
  3) python3 yt_direct.py whoami          -> проверка канала
  4) python3 yt_direct.py upload file.mp4 --title "..." --privacy unlisted [--short]
  5) python3 yt_direct.py list / delete <video_id>

Токен хранится локально в state/yt_token.json (в .gitignore), refresh-токен
позволяет публиковать без браузера дальше — это и есть «прямой автопостинг».
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLIENT_SECRET = BASE / "client_secret.json"
TOKEN_PATH = BASE / "state" / "yt_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _load_env() -> None:
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not TOKEN_PATH.exists():
        sys.exit("Нет токена. Сначала выполни: python3 yt_direct.py auth")
    cred = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    return build("youtube", "v3", credentials=cred)


def cmd_auth(_args) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET.exists():
        sys.exit(
            f"Не найден {CLIENT_SECRET.name}. Скачай JSON OAuth-клиента "
            "(тип Desktop app) из Google Cloud Console → Credentials и положи в корень проекта."
        )
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    # localhost-редирект: браузер открывается на этой машине
    cred = flow.run_local_server(port=0, prompt="consent")
    TOKEN_PATH.write_text(cred.to_json(), encoding="utf-8")
    print(f"OK: токен сохранён в {TOKEN_PATH}")


def cmd_whoami(_args) -> None:
    svc = build_service()
    ch = svc.channels().list(part="snippet,contentDetails", mine=True).execute()
    items = ch.get("items", [])
    if not items:
        sys.exit("Учётка авторизована, но каналов нет.")
    for it in items:
        print(
            "канал:",
            it["snippet"]["title"],
            "| id:",
            it["id"],
            "| подписчики:",
            it.get("statistics", {}).get("subscribersCount", "?"),
        )


def cmd_upload(args) -> None:
    from googleapiclient.http import MediaFileUpload

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"Файл не найден: {path}")
    mime = mimetypes.guess_type(str(path))[0] or "video/mp4"
    body = {
        "snippet": {
            "title": args.title[:100],
            "description": args.desc or "",
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
            "categoryId": args.category,
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": bool(args.kids),
        },
    }
    media = MediaFileUpload(
        str(path), chunksize=args.chunk * 1024 * 1024, resumable=True, mimetype=mime
    )
    svc = build_service()
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)

    def progress(response, bytes_chunk):
        got = getattr(response, "total_size", None)
        if got:
            print(f"\rзагрузка: {bytes_chunk / got:.0%}", end="", flush=True)

    response = None
    while response is None:
        status, response = req.next_progress(callback=progress)
        if status is not None:
            sys.exit(f"ошибка загрузки: {status}")
    print()
    vid = response["id"]
    url = f"https://youtube.com/shorts/{vid}" if args.short else f"https://youtu.be/{vid}"
    print("OK videoId:", vid)
    print("URL:", url)
    if args.schedule_at:
        svc.videos().update(
            part="status",
            body={"id": vid, "status": {"privacyStatus": "private",
                                        "publishAt": args.schedule_at}},
        ).execute()
        print("Запланировано к публикации в:", args.schedule_at, "(UTC ISO8601)")


def cmd_list(args) -> None:
    svc = build_service()
    res = svc.videos().list(part="snippet,status", mine=True, maxResults=args.max).execute()
    for it in res.get("items", []):
        s = it["snippet"]
        st = it["status"]
        print(f"{it['id']}  {st.get('privacyStatus'):9} {s['title'][:60]}")


def cmd_delete(args) -> None:
    svc = build_service()
    svc.videos().delete(id=args.video_id).execute()
    print("Удалено:", args.video_id)


def main() -> None:
    _load_env()
    p = argparse.ArgumentParser(description="Прямая публикация в YouTube (Data API v3)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="первый OAuth-логин в браузере").set_defaults(func=cmd_auth)
    sub.add_parser("whoami", help="показать канал").set_defaults(func=cmd_whoami)

    up = sub.add_parser("upload", help="загрузить видео")
    up.add_argument("file")
    up.add_argument("--title", required=True)
    up.add_argument("--desc", default="")
    up.add_argument("--tags", default="")
    up.add_argument("--category", default="22")
    up.add_argument(
        "--privacy",
        choices=["public", "unlisted", "private"],
        default=os.environ.get("YT_PRIVACY", "unlisted"),
    )
    up.add_argument("--short", action="store_true", help="ссылка как Shorts")
    up.add_argument("--kids", action="store_true")
    up.add_argument("--chunk", type=int, default=8, help="размер чанка, МБ")
    up.add_argument("--schedule-at", default="", help="ISO8601 UTC, напр. 2026-09-27T08:00:00Z")
    up.set_defaults(func=cmd_upload)

    ls = sub.add_parser("list", help="последние видео")
    ls.add_argument("--max", type=int, default=10)
    ls.set_defaults(func=cmd_list)

    de = sub.add_parser("delete", help="удалить видео по id")
    de.add_argument("video_id")
    de.set_defaults(func=cmd_delete)

    args = p.parse_args()
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "invalid_grant" in msg or "RefreshTokenExpired" in msg:
            sys.exit("Refresh-токен отозван/истёк — повтори: python3 yt_direct.py auth")
        raise


if __name__ == "__main__":
    main()
