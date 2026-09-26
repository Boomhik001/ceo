# Автопостинг рилсов (YouTube Shorts) v1.0.0

Скилл-обвязка Upload-Post + планировщик публикаций. Только stdlib Python 3, без pip-зависимостей.

## Структура
```
scheduler.py            # планировщик: слоты, очередь, лимиты, state
schedule.json           # правила расписания (день/время, лимит в день, зазор)
inbox/                  # сюда кладёшь видео (+ одноимённый .txt или queue.json)
state/state.json        # журнал запланированного/опубликованного (в git не попадает)
.env                    # UPLOAD_POST_API_KEY, UPLOAD_POST_USER (не в git)
reels-autopost/         # исходные скиллы из архива
~/.claude/skills/reels-publisher/scripts/publish_reel.py   # сам отправщик
```

## Быстрый старт
```bash
python3 scheduler.py plan              # посмотреть ближайшие слоты (без отправки)
python3 scheduler.py run --dry-run     # прогон с проверкой аккаунтов, ничего не публикует
python3 scheduler.py run               # поставить реальные публикации по слотам
python3 scheduler.py status            # очередь и статусы
```

## Как выкладывать видео
Вариант А — sidecar: `inbox/ep01.mp4` + `inbox/ep01.txt`, где первая строка = заголовок,
остальное = описание. Вариант Б — `inbox/queue.json`:
```json
[{"file": "ep01.mp4", "title": "Эпизод 1", "description": "…", "publish_at": null}]
```
`publish_at: null` → слот подбирается автоматически по `schedule.json`.

## Расписание (schedule.json)
| поле | смысл |
|---|---|
| `platforms` | куда постить (`["youtube"]`, можно добавить `instagram`) |
| `rules[].weekday` | дни недели, пн=0 … вс=6 |
| `rules[].time` | время слота `HH:MM` в `timezone` |
| `max_per_day` | максимум постов в сутки |
| `min_gap_minutes` | минимальный зазор между постами |
| `yt_privacy` | `public/unlisted/private` — применяется, если у publish_reel.py есть флаг `--yt-privacy`; иначе приватность задаётся в профиле Upload-Post |

По умолчанию: будни 11:00 и 18:30, выходные 12:00 (МСК), до 3 постов/сутки, зазор 3 ч.

## Автозапуск (чтобы реально работало без меня)
Планировщику нужен «будильник». Выбери один вариант:

**cron (VPS/сервер):**
```cron
*/30 * * * * cd /path/to/project && /usr/local/bin/python3 scheduler.py run >> logs/sched.log 2>&1
```

**systemd timer:**
```ini
# /etc/systemd/system/reels-sched.service  (Type=oneshot, WorkingDirectory=..., ExecStart=/usr/local/bin/python3 .../scheduler.py run)
# /etc/systemd/system/reels-sched.timer    (OnCalendar=*:0/30)
systemctl enable --now reels-sched.timer
```

**фоновый режим на этой машине:**
```bash
nohup python3 scheduler.py daemon --interval 1800 >> logs/sched.log 2>&1 &
```

## Важно про YouTube
Upload-Post публикует Shorts как обычные вертикальные видео: залей ролик в канал, он определится
как Short автоматически (вертикаль, ≤3 мин). Перед боем держи первый выпуск в `unlisted`/`private`
и проверяй результат в YT Studio.

## Безопасность
`.env` и `state/` исключены из git; API-ключ никуда не пушится. Видеофайлы из `inbox/` в git не попадают.
