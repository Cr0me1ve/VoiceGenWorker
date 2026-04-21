# VoiceGenWorker

Celery-воркер синтеза речи. Слушает очередь `voice` в Redis, генерирует MP3 через Silero TTS и раздаёт файлы через Nginx внутри сети Netbird.

## Архитектура

```
GenManager ──► Redis (очередь voice) ──► VoiceGenWorker ──► Silero TTS ──► /temp/*.mp3
                                                                               │
                                                              Nginx ◄──────────┘
                                                                │
                                                         download_url (Netbird)
```

- **Брокер**: Redis DB 0, **бэкенд результатов**: Redis DB 1
- **Сеть**: Netbird VPN — файловый сервер доступен только внутри VPN
- **Concurrency**: `--concurrency=1 --pool=solo` (последовательная обработка)
- **TTL файлов**: 15 минут (очистка через Celery Beat)

## Быстрый старт

```bash
git clone <repo>
cd VoiceGenWorker
sudo bash setup.sh
```

`setup.sh` автоматически:
1. Устанавливает и подключает Netbird (запрашивает Setup Key)
2. Устанавливает Docker
3. Создаёт `.env` через интерактивный диалог
4. Открывает порт в UFW и запускает контейнеры

## Ручная установка

### 1. Создать `.env`

```bash
cat > .env <<EOF
REDIS_HOST=<IP GenManager в Netbird>
REDIS_PORT=6379
REDIS_PASSWORD=<пароль Redis>
DEFAULT_GENERATOR=silero
DEFAULT_SPEAKER=eugene
DEFAULT_SAMPLE_RATE=48000
TEMP_DIR=temp
FILE_TTL_MINUTES=15
NETBIRD_IP=<IP этого воркера в Netbird>
FILE_SERVER_PORT=8888
EOF
chmod 600 .env
```

### 2. Запустить контейнеры

```bash
docker compose up -d --build
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `REDIS_HOST` | `localhost` | Хост Redis |
| `REDIS_PORT` | `6379` | Порт Redis |
| `REDIS_PASSWORD` | `` | Пароль Redis |
| `CELERY_BROKER_URL` | авто | Полный URL брокера (переопределяет `REDIS_*`) |
| `CELERY_RESULT_BACKEND` | авто | Полный URL бэкенда результатов |
| `DEFAULT_GENERATOR` | `silero` | Генератор TTS по умолчанию |
| `DEFAULT_SPEAKER` | `eugene` | Голос по умолчанию |
| `DEFAULT_SAMPLE_RATE` | `48000` | Частота дискретизации (Гц) |
| `TEMP_DIR` | `temp` | Директория для аудиофайлов |
| `FILE_TTL_MINUTES` | `15` | Время жизни MP3-файлов в минутах |
| `NETBIRD_IP` | `127.0.0.1` | IP воркера в Netbird; на него биндится Nginx |
| `FILE_SERVER_PORT` | `8888` | Порт Nginx файлового сервера |

`CELERY_BROKER_URL` и `CELERY_RESULT_BACKEND` строятся автоматически из `REDIS_*`, но их можно задать явно.

## Celery-задача

**Имя:** `voice_worker.tasks.generate`
**Очередь:** `voice`

### Параметры

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `prompt` | str | да | Текст для синтеза |
| `request_type` | str | да | Должен быть `"voice"` |
| `model_name` | str | нет | Имя генератора (default: `DEFAULT_GENERATOR`) |
| `max_timeout` | int | нет | Информационный таймаут (воркером не используется) |
| `callback_url` | str | нет | URL для POST-уведомления по завершении |
| `**kwargs` | — | нет | Параметры генератора (`speaker`, `sample_rate` и др.) |

### Возвращаемое значение

```json
{
    "download_url": "http://<NETBIRD_IP>:<FILE_SERVER_PORT>/<filename>.mp3"
}
```

Файл доступен внутри Netbird-сети до истечения `FILE_TTL_MINUTES`.

### Передача параметров генератора

**Через kwargs:**
```json
{
    "prompt": "Привет, мир",
    "request_type": "voice"
    "kwargs": {
        "speaker": "aidar",
        "sample_rate": 24000
    }
}
```

**JSON-префиксом в prompt** (первая строка — JSON, остальное — текст):
```json
{
    "prompt": "{\"speaker\":\"aidar\",\"sample_rate\":24000}\nПривет, мир",
    "request_type": "voice"
}
```

При одновременном использовании kwargs имеют приоритет над JSON-префиксом.

## Генератор Silero

### Параметры

| Параметр | По умолчанию | Описание |
|---|---|---|
| `speaker` | `eugene` | Голос |
| `sample_rate` | `48000` | Частота дискретизации: `8000`, `24000`, `48000` |
| `language` | `ru` | Код языка: `ru`, `en`, `de`, `es`, `fr`, … |
| `speaker_model` | `v5_ru` | Вариант модели: `v5_ru`, `v3_en`, … |

### Доступные голоса

| Голос | Пол |
|---|---|
| `aidar` | мужской |
| `baya` | женский |
| `kseniya` | женский |
| `xenia` | женский |
| `eugene` | мужской (по умолчанию) |
| `random` | случайный |

Модели кэшируются в памяти — повторные запросы с тем же языком/вариантом не перезагружают модель.

## Генератор OmniVoice

Zero-shot multilingual TTS от k2-fsa ([huggingface.co/k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice)).
Поддерживает 600+ языков, клонирование голоса из короткого аудио, voice design по описанию и non-verbal символы (`[laughter]`, `[sigh]` и т.д.).

### Параметры

| Параметр | По умолчанию | Описание |
|---|---|---|
| `ref_audio` | — | Путь к файлу или **URL** референс-аудио (3–10 сек) для клонирования голоса |
| `ref_text` | — | Транскрипция `ref_audio` |
| `instruct` | — | Описание голоса: `"female, low pitch, british accent"` |
| `num_step` | `32` | Шаги диффузии (16 — быстрее, 32 — качественнее) |
| `speed` | `1.0` | Множитель скорости (>1.0 быстрее) |
| `duration` | — | Фиксированная длительность в секундах |
| `language_id` | — | Идентификатор языка |
| `seed` | — | Seed для воспроизводимости |
| `dtype` | `float16` | `float16` \| `float32` \| `bfloat16` |
| `device` | `auto` | `auto` \| `cuda:0` \| `cpu` \| `mps` |
| `model_id` | `k2-fsa/OmniVoice` | HF repo id модели |

### Режимы работы

**Voice cloning** — передать `ref_audio` (URL или путь) и `ref_text`:
```json
{
    "prompt": "Hello, this is a cloned voice.",
    "request_type": "voice",
    "model_name": "omnivoice",
    "kwargs": {
        "ref_audio": "http://100.95.0.1:8888/sample.wav",
        "ref_text": "Original transcription."
    }
}
```

**Voice design** — описать голос через `instruct`:
```json
{
    "prompt": "Привет!",
    "request_type": "voice",
    "model_name": "omnivoice",
    "kwargs": {"instruct": "female, young, high pitch"}
}
```

**Auto voice** — без `ref_audio` и `instruct`, голос выбирается автоматически.

> ⚠️ Для приемлемой скорости нужен GPU. В базовом `Dockerfile` ставится PyTorch CPU — для CUDA замени строку `pip install torch ...` на версию с `--index-url https://download.pytorch.org/whl/cu128` и пробрось GPU в `docker-compose.yml` (`deploy.resources.reservations.devices`).

## Структура проекта

```
VoiceGenWorker/
├── worker/
│   ├── tasks.py              # Задачи: generate, cleanup_old_files
│   ├── celery_app.py         # Инициализация Celery
│   ├── config.py             # Настройки (Pydantic Settings)
│   └── generators/
│       ├── __init__.py       # Реестр генераторов
│       ├── base.py           # BaseTTSGenerator + ParamSpec
│       └── silero.py         # Реализация Silero TTS
├── nginx/
│   └── file-server.conf      # Конфигурация Nginx
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── setup.sh                  # Скрипт автодеплоя
```

## Добавление нового генератора

1. Создать `worker/generators/my_tts.py`:

```python
from worker.generators.base import BaseTTSGenerator, ParamSpec

class MyTTSGenerator(BaseTTSGenerator):
    PARAMS = {
        "voice": ParamSpec("default", str, "Голос"),
    }

    def generate(self, text: str, params: dict) -> str:
        p = self.resolve_params(params)
        # ... генерация аудио ...
        return file_path  # путь к .mp3
```

2. Зарегистрировать в `worker/generators/__init__.py`:

```python
from worker.generators.my_tts import MyTTSGenerator
_REGISTRY["my_tts"] = MyTTSGenerator
```

3. Передать `model_name="my_tts"` в задачу.

## Управление

```bash
# Логи
docker compose logs -f

# Перезапуск
docker compose restart

# Обновление
git pull && docker compose up -d --build

# Остановка
docker compose down
```
