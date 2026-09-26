#!/usr/bin/env python3
"""Автопостинг-планировщик для Upload-Post (YouTube Shorts и др.).

Как это работает
----------------
1. Ты кладёшь видео в папку inbox/ (или поддомены inbox/<имя_профиля>/).
2. Рядом кладёшь sidecar .txt с тем же именем (необязательно) -- текст = описание/заголовок.
   Либо один queue.json со списком {file,title,description,tags,publish_at}.
3. Этот скрипт считает ближайший свободный слот по правилам schedule.json
   (день недели + время, лимит постов в день, минимальный зазор между постами),
   вызывает publish_reel.py --schedule <слот> и пишет результат в state/state.json.

Режимы:
  python3 scheduler.py plan            -- показать ближайшие слоты без публикации
  python3 scheduler.py run             -- поставить всё из inbox/ в очередь (реальная публикация)
  python3 scheduler.py run --dry-run   -- то же самое, но ничего не отправляет в API
  python3 scheduler.py status          -- что уже запланировано/опубликовано
  python3 scheduler.py daemon          -- фоновый цикл (для cron/systemd можно просто run раз в час)

Только stdlib. Секреты берутся из .env (UPLOAD_POST_API_KEY, UPLOAD_POST_USER).
"""
import argparse, json, os, shlex, subprocess, sys, time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")
SCHED_PATH = os.path.join(ROOT, "schedule.json")
STATE_PATH = os.path.join(ROOT, "state", "state.json")
INBOX = os.path.join(ROOT, "inbox")
PUBLISHER = os.path.expanduser("~/.claude/skills/reels-publisher/scripts/publish_reel.py")
VID_EXT = (".mp4", ".mov", ".webm", ".mkv", ".avi")


# ---------------------------------------------------------------- инфраструктура
def load_env():
    env = dict(os.environ)
    if os.path.isfile(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def load_sched():
    with open(SCHED_PATH, encoding="utf-8") as f:
        return json.load(f)


def tz(sched):
    name = sched.get("timezone", "Europe/Moscow")
    if name == "Europe/Moscow":
        return timezone(timedelta(hours=3), "MSK")
    try:  # py3.9+ zoneinfo
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=3), "MSK")


def load_state():
    if os.path.isfile(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"items": []}


def save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


# ---------------------------------------------------------------- слоты
def slot_candidates(sched, now):
    """Все слоты (день недели + время) на 14 дней вперёд, отсортированы по возрастанию."""
    out = []
    for r in sched["rules"]:
        wd = r["weekday"] if isinstance(r["weekday"], list) else [r["weekday"]]
        wd = {int(x) % 7 for x in wd}          # приводим ISO/пн=0 схему к date().weekday()
        hh, mm = (int(x) for x in r["time"].split(":"))
        for d in range(0, 15):
            day = (now + timedelta(days=d)).date()
            if day.weekday() in wd:
                out.append(datetime(day.year, day.month, day.day, hh, mm, tzinfo=now.tzinfo))
    return sorted(set(out))


def next_slot(sched, st, now, taken=None):
    """Ближайший слот, удовлетворяющий max_per_day и min_gap_minutes."""
    taken = list(taken or [])
    published = [datetime.fromisoformat(i["publish_at"]) for i in st["items"]
                 if i.get("publish_at") and i.get("status") in ("scheduled", "published")]
    gap = timedelta(minutes=sched.get("min_gap_minutes", 60))
    limit = sched.get("max_per_day", 99)
    horizon = now + timedelta(days=30)
    cands = [c for c in slot_candidates(sched, now) if c > now + timedelta(minutes=5)]
    for cand in cands:
        if cand > horizon:
            break
        if any(abs(cand - p) < gap for p in published + taken):
            continue
        same_day = [p for p in published + taken if p.date() == cand.date()]
        if len(same_day) >= limit:
            continue
        return cand
    return None


# ---------------------------------------------------------------- очередь
def scan_inbox(sched):
    """Собираем кандидатов: sidecar-файлы рядом с видео + queue.json."""
    items = []
    qf = os.path.join(INBOX, "queue.json")
    if os.path.isfile(qf):
        with open(qf, encoding="utf-8") as f:
            for e in json.load(f):
                path = e["file"] if os.path.isabs(e["file"]) else os.path.join(INBOX, e["file"])
                items.append({
                    "file": path,
                    "title": e.get("title") or os.path.splitext(os.path.basename(path))[0],
                    "description": e.get("description") or "",
                    "tags": e.get("tags") or [],
                    "publish_at": e.get("publish_at"),
                    "platforms": e.get("platforms") or sched["platforms"],
                })
    if os.path.isdir(INBOX):
        for dirpath, _dirs, files in os.walk(INBOX):
            for fn in sorted(files):
                if not fn.lower().endswith(VID_EXT):
                    continue
                full = os.path.join(dirpath, fn)
                if any(full == i["file"] for i in items):
                    continue
                stem = os.path.splitext(fn)[0]
                meta = {}
                for ext in (".txt", ".json", ".md"):
                    m = os.path.join(dirpath, stem + ext)
                    if os.path.isfile(m):
                        if ext == ".json":
                            meta = json.load(open(m, encoding="utf-8"))
                        else:
                            txt = open(m, encoding="utf-8").read().strip()
                            lines = txt.splitlines()
                            meta = {"title": lines[0][:90] if lines else stem,
                                    "description": "\n".join(lines[1:]).strip()}
                        break
                profile = os.path.basename(dirpath) if dirpath != INBOX else sched.get("profile")
                items.append({
                    "file": full, "title": meta.get("title") or stem,
                    "description": meta.get("description") or meta.get("title") or stem,
                    "tags": meta.get("tags") or [], "publish_at": meta.get("publish_at"),
                    "platforms": meta.get("platforms") or sched["platforms"],
                    "user": meta.get("user") or profile,
                })
    return items


def build_cmd(item, when, sched, env):
    """Собираем команду publish_reel.py. Приватность YouTube включается флагом
    --yt-privacy ТОЛЬКО если он поддерживается (см. publisher_supports_privacy)."""
    cmd = [sys.executable, PUBLISHER,
           "--video", item["file"],
           "--title", item["description"] or item["title"],
           "--youtube-title", item["title"][:100],
           "--youtube-description", (item["description"] or item["title"]),
           "--platforms", *item["platforms"],
           "--user", item.get("user") or env.get("UPLOAD_POST_USER", "default"),
           "--schedule", when.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "--timezone", sched.get("timezone", "Europe/Moscow")]
    if sched.get("yt_privacy") and publisher_supports_privacy():
        cmd += ["--yt-privacy", sched["yt_privacy"]]
    if sched.get("dry_run"):
        cmd += ["--dry-run"]
    return cmd


_PRIVACY_OK = None


def publisher_supports_privacy():
    """Есть ли у установленного publish_reel.py флаг --yt-privacy (кэш результата)."""
    global _PRIVACY_OK
    if _PRIVACY_OK is None:
        try:
            src = open(PUBLISHER, encoding="utf-8").read()
            _PRIVACY_OK = "--yt-privacy" in src
        except OSError:
            _PRIVACY_OK = False
        if not _PRIVACY_OK:
            print("! publish_reel.py без флага --yt-privacy: приватность берём из настроек "
                  "профиля Upload-Post (app.upload-post.com -> профиль -> YouTube privacy)")
    return _PRIVACY_OK


def run_publish(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    data = None
    if out:
        try:
            data = json.loads(out)
        except Exception:
            pass
    return p.returncode, data, out, err


# ---------------------------------------------------------------- команды
def cmd_plan(a):
    sched, st, env = load_sched(), load_state(), load_env()
    now = datetime.now(tz(sched))
    items = scan_inbox(sched)
    print(f"# План на {now:%Y-%m-%d %H:%M} ({sched.get('timezone')}) | видео в inbox: {len(items)}")
    if not items:
        print("  inbox пуст -- положи .mp4 (+ одноимённый .txt с описанием) или inbox/queue.json")
    taken = []
    for it in items:
        when = (datetime.fromisoformat(it["publish_at"]).replace(tzinfo=now.tzinfo)
                if it.get("publish_at") else next_slot(sched, st, now, taken))
        if when is None:
            print(f"  ! {os.path.basename(it['file'])}: нет свободного слота (лимит/зазор)")
            continue
        taken.append(when)
        print(f"  {when:%a %d.%m %H:%M}  {it['title'][:52]:<52} <- {os.path.relpath(it['file'], ROOT)}")
        print(f"      {' '.join(shlex.quote(x) for x in build_cmd(it, when, sched, env)[:6])} ...")


def cmd_run(a):
    sched, st, env = load_sched(), load_state(), load_env()
    if a.dry_run:
        sched = dict(sched); sched["dry_run"] = True
    now = datetime.now(tz(sched))
    done_keys = {i["file"] for i in st["items"] if i.get("status") in ("scheduled", "published")}
    items = [i for i in scan_inbox(sched) if i["file"] not in done_keys]
    if not items:
        print("Нечего публиковать (inbox пуст или всё уже в очереди)."); return 0
    taken, ok = [], 0
    for it in items:
        when = (datetime.fromisoformat(it["publish_at"]).replace(tzinfo=now.tzinfo)
                if it.get("publish_at") else next_slot(sched, st, now, taken))
        if when is None:
            print(f"! {os.path.basename(it['file'])}: нет слота, пропускаю"); continue
        taken.append(when)
        cmd = build_cmd(it, when, sched, env)
        code, data, out, err = run_publish(cmd)
        status = "scheduled" if code == 0 else "failed"
        rec = {"file": it["file"], "title": it["title"], "publish_at": when.isoformat(),
               "platforms": it["platforms"], "status": status, "code": code,
               "response": data or (out or err)[:500], "ts": now.isoformat(),
               "dry_run": bool(a.dry_run)}
        st["items"].append(rec); save_state(st); ok += code == 0
        tag = "OK " if code == 0 else "ERR"
        print(f"[{tag}] {when:%d.%m %H:%M} {it['title'][:46]} :: {(data or err or out)[:120] if isinstance((data or err or out), str) else json.dumps(data, ensure_ascii=False)[:160]}")
    print(f"\nЗапланировано/отправлено: {ok}/{len(items)}. Статус: python3 scheduler.py status")
    return 0 if ok else 1


def cmd_status(a):
    sched, st = load_sched(), load_state()
    now = datetime.now(tz(sched))
    if not st["items"]:
        print("Очередь пуста."); return
    for i in sorted(st["items"], key=lambda x: x.get("publish_at") or ""):
        w = datetime.fromisoformat(i["publish_at"]) if i.get("publish_at") else None
        flag = "DRY" if i.get("dry_run") else "LIVE"
        when = (w.strftime("%d.%m %H:%M") if w else "-")
        rel = "уже вышел" if w and w <= now else ""
        print(f"  [{i['status']:<9}|{flag}] {when:<12} {i['title'][:44]:<44} {rel}")


def cmd_daemon(a):
    while True:
        rc = cmd_run(argparse.Namespace(dry_run=a.dry_run))
        time.sleep(max(60, a.interval))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run"); r.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    d = sub.add_parser("daemon"); d.add_argument("--interval", type=int, default=3600); d.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    return {"plan": cmd_plan, "run": cmd_run, "status": cmd_status, "daemon": cmd_daemon}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main() or 0)
