#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_DIR/.env"

echo "=== VoiceGenWorker setup ==="

# ── .env ────────────────────────────────────────────────────────
ENV_SKIP=0
if [ -f "$ENV_FILE" ]; then
    read -rp ".env уже существует. Перезаписать? [y/N] " answer
    case "$answer" in
        [yY][eE][sS]|[yY]) ENV_SKIP=0 ;;
        *) echo "Оставляю существующий .env."; ENV_SKIP=1 ;;
    esac
fi

if [ "$ENV_SKIP" -eq 0 ]; then
    read -rp "REDIS_HOST (default: minet.space): " REDIS_HOST
    REDIS_HOST="${REDIS_HOST:-minet.space}"

    read -rp "REDIS_PORT (default: 6379): " REDIS_PORT
    REDIS_PORT="${REDIS_PORT:-6379}"

    read -rsp "REDIS_PASSWORD: " REDIS_PASSWORD
    echo

    read -rp "DEFAULT_GENERATOR (default: silero): " DEFAULT_GENERATOR
    DEFAULT_GENERATOR="${DEFAULT_GENERATOR:-silero}"

    read -rp "DEFAULT_SPEAKER (default: eugene): " DEFAULT_SPEAKER
    DEFAULT_SPEAKER="${DEFAULT_SPEAKER:-eugene}"

    read -rp "DEFAULT_SAMPLE_RATE (default: 48000): " DEFAULT_SAMPLE_RATE
    DEFAULT_SAMPLE_RATE="${DEFAULT_SAMPLE_RATE:-48000}"

    read -rp "TEMP_DIR (default: temp): " TEMP_DIR
    TEMP_DIR="${TEMP_DIR:-temp}"

    cat > "$ENV_FILE" <<EOF
# Redis / Celery — подключение к GenManager на minet.space
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}
REDIS_PASSWORD=${REDIS_PASSWORD}

CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/1

# TTS
DEFAULT_GENERATOR=${DEFAULT_GENERATOR}
DEFAULT_SPEAKER=${DEFAULT_SPEAKER}
DEFAULT_SAMPLE_RATE=${DEFAULT_SAMPLE_RATE}

# Temp dir
TEMP_DIR=${TEMP_DIR}
EOF
    echo ".env создан."
fi

# ── Docker ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "Docker не найден. Устанавливаю..."
    curl -fsSL https://get.docker.com | sh
fi

echo "Собираю и запускаю контейнер..."
docker compose up -d --build

echo ""
echo "=== Готово ==="
echo "Воркер слушает очередь 'voice', Redis: ${REDIS_HOST:-minet.space}:${REDIS_PORT:-6379}"
echo "Логи: docker compose logs -f"
