import os
import json
import logging
import time
from worker.celery_app import celery
from worker.config import get_settings
from worker.generators import get_generator

logger = logging.getLogger(__name__)
settings = get_settings()


@celery.task(name="voice_worker.tasks.generate", bind=True)
def generate(
    self,
    prompt: str,
    request_type: str,
    model_name: str | None = None,
    max_timeout: int = 180,
    callback_url: str | None = None,
    **kwargs,
):
    """
    Celery task для GenManager (multi_queue).
    Слушает очередь 'voice', обрабатывает request_type='voice'.

    Параметры генератора передаются двумя способами:
    1. Через kwargs: {"speaker": "aidar", "sample_rate": 24000}
    2. JSON-префиксом в prompt:
       '{"speaker":"aidar","sample_rate":24000}\nТекст для озвучки'

    Возвращает dict:
        {
            "download_url": "http://<netbird_ip>:<port>/<filename>",
            "filename":     "<filename>"
        }
    Файл доступен внутри Netbird-сети пока не будет удалён из temp/.
    """
    task_id = self.request.id
    logger.info("[%s] Получена задача: request_type=%s model=%s prompt_len=%d",
                task_id, request_type, model_name, len(prompt))

    if request_type != "voice":
        logger.error("[%s] Неподдерживаемый request_type: %s", task_id, request_type)
        raise ValueError(
            f"VoiceGenWorker handles only request_type='voice', got '{request_type}'"
        )

    # --- Извлекаем JSON-параметры из префикса prompt ---
    text = prompt
    inline_params: dict = {}
    first_line, _, rest = prompt.partition("\n")
    if first_line.strip().startswith("{"):
        try:
            inline_params = json.loads(first_line.strip())
            text = rest.strip()
            logger.debug("[%s] JSON-параметры из prompt: %s", task_id, inline_params)
        except json.JSONDecodeError:
            logger.warning("[%s] Не удалось распарсить JSON-префикс, трактую как обычный текст", task_id)

    raw_params = {**inline_params, **kwargs}
    generator_name = model_name or settings.default_generator
    logger.info("[%s] Генератор: %s | параметры: %s", task_id, generator_name, raw_params)

    os.makedirs(settings.temp_dir, exist_ok=True)

    t_start = time.monotonic()
    try:
        generator = get_generator(generator_name)
        file_path = generator.generate(text=text, params=raw_params)
    except Exception as exc:
        elapsed = time.monotonic() - t_start
        logger.exception("[%s] Ошибка генерации (%.2fs): %s", task_id, elapsed, exc)
        raise

    elapsed = time.monotonic() - t_start
    filename = os.path.basename(file_path)
    download_url = f"{settings.file_base_url}/{filename}"
    logger.info("[%s] Готово за %.2fs → %s", task_id, elapsed, download_url)

    result = {"download_url": download_url}

    if callback_url:
        logger.debug("[%s] Отправка callback на %s", task_id, callback_url)
        _send_callback(callback_url, result)

    return result


@celery.task(name="voice_worker.tasks.cleanup_old_files")
def cleanup_old_files():
    """Удаляет mp3 файлы из temp/, которые старше file_ttl_minutes."""
    ttl_seconds = settings.file_ttl_minutes * 60
    temp_dir = settings.temp_dir
    if not os.path.isdir(temp_dir):
        return

    now = time.time()
    removed = 0
    for filename in os.listdir(temp_dir):
        if not filename.lower().endswith(".mp3"):
            continue
        filepath = os.path.join(temp_dir, filename)
        try:
            if now - os.path.getmtime(filepath) > ttl_seconds:
                os.remove(filepath)
                removed += 1
        except OSError as exc:
            logger.warning("Не удалось удалить %s: %s", filepath, exc)

    if removed:
        logger.info("Очистка: удалено %d файлов старше %d мин", removed, settings.file_ttl_minutes)


def _send_callback(url: str, result: dict) -> None:
    try:
        import httpx
        httpx.post(url, json={"result": result}, timeout=10)
        logger.debug("Сallback отправлен: %s", url)
    except Exception as exc:
        logger.warning("Ошибка отправки callback на %s: %s", url, exc)
