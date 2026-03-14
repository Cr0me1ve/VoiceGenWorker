# VoiceGenWorker

Celery-воркер генерации речи для [GenManager](https://github.com/Cr0me1ve/GenManager).  
Слушает очередь `voice`, подключается к Redis на `minet.space`, возвращает путь к сгенерированному `.mp3` файлу.

---

## Стек

| Компонент | Роль |
|-----------|------|
| **Celery** | Получение задач из очереди `voice` |
| **Redis** | Брокер и result backend (GenManager на `minet.space`) |
| **Silero TTS** | Генерация речи |
| **Docker** | Изоляция запуска |

---

## Архитектура

```
GenManager (minet.space)
    ↓  POST /api/v1/generate  {request_type: "voice"}
    ↓  Celery → Redis → очередь "voice"
    ↓
VoiceGenWorker (celery -Q voice)
    ↓
worker/generators/
    ├── silero.py     ← по умолчанию
    └── ... (добавляй новые)
    ↓
temp/<name>.mp3  →  Redis result backend  →  GenManager  →  Клиент
```

---

## Быстрый старт

```bash
git clone -b multi_queue git@github.com:Cr0me1ve/VoiceGenWorker.git
cd VoiceGenWorker
sudo bash setup.sh
```

Скрипт спросит параметры и создаст `.env`, затем соберёт и запустит контейнер.

### Что делает `setup.sh`

1. Если `.env` уже есть — спрашивает, надо ли перезаписать
2. Интерактивно запрашивает `REDIS_HOST` (default: `minet.space`), `REDIS_PASSWORD` и др.
3. Устанавливает Docker, если его нет
4. Запускает `docker compose up -d --build`

### Ручной запуск

```bash
# Создай .env вручную
cat > .env <<EOF
REDIS_HOST=minet.space
REDIS_PORT=6379
REDIS_PASSWORD=your_password
CELERY_BROKER_URL=redis://:your_password@minet.space:6379/0
CELERY_RESULT_BACKEND=redis://:your_password@minet.space:6379/1
DEFAULT_GENERATOR=silero
DEFAULT_SPEAKER=eugene
DEFAULT_SAMPLE_RATE=48000
TEMP_DIR=temp
EOF

docker compose up -d --build
```

---

## Параметры `.env`

| Переменная | По умолчанию | Описание |
|-------------|-----------|----------|
| `REDIS_HOST` | `minet.space` | Хост Redis (GenManager) |
| `REDIS_PORT` | `6379` | Порт Redis |
| `REDIS_PASSWORD` | — | Пароль Redis |
| `CELERY_BROKER_URL` | авто | Переопределяет автовычисленный broker URL |
| `CELERY_RESULT_BACKEND` | авто | Переопределяет автовычисленный backend URL |
| `DEFAULT_GENERATOR` | `silero` | Имя генератора по умолчанию |
| `DEFAULT_SPEAKER` | `eugene` | Голос по умолчанию |
| `DEFAULT_SAMPLE_RATE` | `48000` | Частота дискретизации |
| `TEMP_DIR` | `temp` | Папка для сгенерированных файлов |

---

## Использование через GenManager

```bash
# Async
curl -X POST https://minet.space/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"prompt": "Привет мир", "request_type": "voice", "model_name": "silero"}'
# → {"task_id": "...", "status": "queued", "queue": "voice"}

# Получить результат
curl https://minet.space/api/v1/result/{task_id} \
  -H "X-API-Key: YOUR_KEY"
# → {"status": "completed", "result": "temp/silero_eugene_a1b2c3d4.mp3"}
```

### Передача параметров генератора

Два способа передать параметры Silero (speaker, sample_rate и др.):

**1. Через `kwargs` (если GenManager поддерживает):**
```json
{
  "prompt": "Текст для озвучки",
  "request_type": "voice",
  "speaker": "aidar",
  "sample_rate": 24000
}
```

**2. JSON-префикс в `prompt`:**
```json
{
  "prompt": "{\"speaker\":\"aidar\",\"sample_rate\":24000}\nТекст для озвучки",
  "request_type": "voice"
}
```

---

## Поддерживаемые голоса Silero

| Голос | Язык |
|-------|-------|
| `eugene` | русский |
| `aidar` | русский |
| `baya` | русский |
| `kseniya` | русский |
| `xenia` | русский |
| `random` | случайный |

---

## Добавить новый TTS-генератор

1. Создай `worker/generators/my_tts.py`, наследуй `BaseTTSGenerator`
2. Объяви `PARAMS` и реализуй `generate(text, params) -> str`
3. Зарегистрируй в `worker/generators/__init__.py`
4. В `model_name` запроса передай имя нового генератора

---

## Структура проекта

```
VoiceGenWorker/
├── worker/
│   ├── celery_app.py        # Celery + очередь voice
│   ├── config.py            # Настройки из .env (pydantic-settings)
│   ├── tasks.py             # Маин таска voice_worker.tasks.generate
│   └── generators/
│       ├── base.py          # Абстрактный класс + ParamSpec
│       ├── silero.py        # Silero TTS (по умолчанию)
│       └── __init__.py      # Реестр генераторов
├── setup.sh                 # Интерактивный скрипт настройки
├── docker-compose.yml       # Запуск контейнера
├── Dockerfile
├── requirements.txt
└── .env                     # (не в git)
```

---

## Управление

```bash
# Логи
docker compose logs -f

# Перезапуск
docker compose restart

# Обновление
git pull && docker compose up -d --build

# Статус
docker compose ps
```
