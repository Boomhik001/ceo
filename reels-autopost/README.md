# Reels Autopost — скиллы автопубликации рилсов

Публикация вертикальных видео в **Instagram Reels + TikTok + YouTube Shorts** одной командой через официальные API платформ (сервис [Upload-Post](https://upload-post.com)). Без риска бана: никаких «серых» ботов и эмуляции приложений — только официальный OAuth.

Два скилла для AI-агентов (Hermes Agent, Claude Code и др.):

| Скилл | Когда срабатывает | Что делает |
|---|---|---|
| `reels-autopost-setup` | «Настрой автопубликацию рилсов» | Мастер настройки с нуля: регистрация в Upload-Post → подключение аккаунтов → приём API-ключа → проверка → тестовая публикация |
| `reels-publisher` | «Опубликуй / запости / выложи рилс» | Ежедневная публикация: превью → подтверждение → постинг во все платформы → отчёт со ссылками |

## Возможности

- 📤 Публикация одним вызовом в IG Reels, TikTok, YouTube Shorts (+ 19 других сетей при желании)
- 🕐 Отложенная публикация по расписанию (`--schedule`, таймзона)
- 📝 TikTok в режиме черновика (по умолчанию) — видео прилетает во входящие приложения, что даёт лучший органический охват
- 🛡 Защита от дублей (Idempotency-Key), распознавание скрытого фолбэка TikTok в черновики
- 🏷 Пометка AI-контента (`--ai-generated`), Instagram Trial Reels, кастомные обложки
- 🔍 `--dry-run` — проверка связи и аккаунтов без публикации
- Зависимости: только Python 3.8+ stdlib, ничего ставить не нужно

## Быстрый старт

### 1. Upload-Post

1. Зарегистрируйтесь на [upload-post.com](https://upload-post.com) (тариф Basic $24/мес — нужен для TikTok; Free работает только для IG+YT, 10 загрузок/мес)
2. Подключите аккаунты: Connect Instagram / TikTok / YouTube (OAuth). Instagram должен быть типа «Автор» или «Бизнес»
3. Скопируйте ключ в разделе **API Keys**

### 2. Ключ

```bash
export UPLOAD_POST_API_KEY="eyJhb..."        # или строкой в файле .env рядом со скриптом
export UPLOAD_POST_USER="ваш_профиль"         # username профиля Upload-Post
```

### 3. Публикация

```bash
python3 skills/reels-publisher/scripts/publish_reel.py \
  --video ./reel.mp4 \
  --title "Подпись для Instagram и TikTok #хэштеги" \
  --youtube-title "Заголовок для YouTube (до 100 символов)" \
  --platforms instagram tiktok youtube \
  --wait
```

Скрипт дождётся результата и выведет JSON со ссылками по каждой платформе.

### Ключевые флаги

- `--video` — локальный файл или публичный URL
- `--schedule "2026-09-01T19:00:00" --timezone Europe/Moscow` — по расписанию
- `--tiktok-mode direct` — TikTok полностью автоматом (по умолчанию `draft` — черновик во входящие)
- `--share-mode TRIAL_REELS_DONT_SHARE_TO_FOLLOWERS` — Instagram Trial Reels
- `--dry-run` — проверить ключ и аккаунты, ничего не публикуя

## Установка как скиллы агента

**Hermes Agent:** скопируйте `skills/reels-publisher` и `skills/reels-autopost-setup` в `~/.hermes/skills/social-media/`.

**Claude Code:** скопируйте в `.claude/skills/` вашего проекта.

После этого агент сам подхватит скиллы по триггерам: «настрой автопубликацию» / «опубликуй рилс».

## Лимиты и безопасность

- Дневные капы платформ: TikTok 15 постов/день, Instagram 50, YouTube 10 (на аккаунт)
- Новые аккаунты — «прогрев»: 1–3 поста/день первые 2–4 недели
- Видео: вертикаль 9:16, mp4 h264; без водяного знака TikTok (режет охваты на других платформах)
- Ключ API — секрет: не коммитить, хранить в env

## Структура

```
skills/
  reels-autopost-setup/SKILL.md      # мастер настройки с нуля
  reels-publisher/SKILL.md           # правила ежедневной публикации
  reels-publisher/scripts/
    publish_reel.py                  # скрипт публикации (stdlib only)
```

## Лицензия

MIT
