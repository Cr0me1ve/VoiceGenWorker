import os
import json
from worker.celery_app import celery
from worker.config import get_settings
from worker.generators import get_generator

settings = get_settings()


@celery.task(name="worker.tasks.generate", bind=True)
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
    Celery task compatible with GeminiBApiServer.
    Handles request_type='audio'.

    Extra generator params can be passed two ways:

    1. Via kwargs directly (when caller uses celery.send_task with extra kwargs):
           {"speaker": "aidar", "sample_rate": 24000}

    2. As JSON prefix in prompt (for callers that can only send prompt string):
           prompt = '{"speaker":"aidar","sample_rate":24000}\\nТекст для озвучки'
       The JSON object on the first line is stripped and used as params.
    """
    if request_type != "audio":
        raise ValueError(
            f"VoiceGen only handles request_type='audio', got '{request_type}'"
        )

    # --- Extract params from JSON prefix in prompt (optional) ---
    text = prompt
    inline_params: dict = {}
    first_line, _, rest = prompt.partition("\n")
    if first_line.strip().startswith("{"):
        try:
            inline_params = json.loads(first_line.strip())
            text = rest.strip()
        except json.JSONDecodeError:
            pass  # treat the whole prompt as plain text

    # kwargs take priority over inline JSON
    raw_params = {**inline_params, **kwargs}

    generator_name = model_name or settings.default_generator

    os.makedirs(settings.temp_dir, exist_ok=True)

    generator = get_generator(generator_name)
    file_path = generator.generate(text=text, params=raw_params)

    if callback_url:
        _send_callback(callback_url, file_path)

    return file_path


def _send_callback(url: str, file_path: str) -> None:
    try:
        import httpx
        httpx.post(url, json={"result": file_path}, timeout=10)
    except Exception:
        pass
