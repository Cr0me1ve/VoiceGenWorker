import os
import uuid
import logging
import subprocess
import tempfile
from urllib.parse import urlparse

import httpx
import soundfile as sf
import torch

from worker.config import get_settings
from worker.generators.base import BaseTTSGenerator, ParamSpec

logger = logging.getLogger(__name__)
_settings = get_settings()


class OmniVoiceGenerator(BaseTTSGenerator):
    """
    TTS via OmniVoice (k2-fsa/OmniVoice).

    Поддерживает:
      - zero-shot voice cloning (ref_audio + ref_text)
      - voice design (instruct: "female, low pitch, british accent")
      - auto voice (без ref_audio и instruct)
      - non-verbal symbols: [laughter], [sigh], ...
      - Chinese/English pronunciation correction

    Params:
        ref_audio   - путь к файлу или URL с референс-аудио для клонирования голоса (3-10 сек)
        ref_text    - транскрипция ref_audio
        instruct    - описание голоса (gender, age, pitch, accent, dialect, style)
        num_step    - число шагов диффузии (16 — быстрее, 32 — качественнее)
        speed       - множитель скорости речи (>1.0 быстрее, <1.0 медленнее)
        duration    - фиксированная длительность вывода в секундах
        language_id - идентификатор языка
        seed        - seed для воспроизводимости
        dtype       - torch dtype: float16, float32, bfloat16
        device      - cuda:0, cpu, mps
    """

    PARAMS = {
        "ref_audio":   ParamSpec(None,  str,   "Путь или URL референс-аудио для клонирования голоса"),
        "ref_text":    ParamSpec(None,  str,   "Транскрипция референс-аудио"),
        "instruct":    ParamSpec(None,  str,   "Описание голоса: gender, age, pitch, accent, dialect"),
        "num_step":    ParamSpec(32,    int,   "Число шагов диффузии (16 — быстро, 32 — качественно)"),
        "speed":       ParamSpec(1.0,   float, "Множитель скорости речи (>1.0 быстрее)"),
        "duration":    ParamSpec(None,  float, "Фиксированная длительность вывода в секундах"),
        "language_id": ParamSpec(None,  str,   "Идентификатор языка"),
        "seed":        ParamSpec(None,  int,   "Seed для воспроизводимости"),
        "dtype":       ParamSpec("float16", str, "torch dtype: float16 | float32 | bfloat16"),
        "device":      ParamSpec("auto", str,  "Устройство: auto | cuda:0 | cpu | mps"),
        "model_id":    ParamSpec("k2-fsa/OmniVoice", str, "HuggingFace repo id модели"),
    }

    _model_cache: dict[str, object] = {}
    _SAMPLE_RATE = 24000

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device and device != "auto":
            return device
        if torch.cuda.is_available():
            return "cuda:0"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _resolve_dtype(dtype: str):
        mapping = {
            "float16": torch.float16,
            "fp16":    torch.float16,
            "half":    torch.float16,
            "float32": torch.float32,
            "fp32":    torch.float32,
            "float":   torch.float32,
            "bfloat16": torch.bfloat16,
            "bf16":    torch.bfloat16,
        }
        return mapping.get((dtype or "").lower(), torch.float16)

    def _load_model(self, model_id: str, device: str, dtype_str: str):
        cache_key = f"{model_id}|{device}|{dtype_str}"
        if cache_key not in OmniVoiceGenerator._model_cache:
            from omnivoice import OmniVoice

            logger.info("Загрузка OmniVoice модели: %s (device=%s dtype=%s)",
                        model_id, device, dtype_str)
            model = OmniVoice.from_pretrained(
                model_id,
                device_map=device,
                dtype=self._resolve_dtype(dtype_str),
            )
            OmniVoiceGenerator._model_cache[cache_key] = model
            logger.info("OmniVoice модель загружена и закэширована")
        return OmniVoiceGenerator._model_cache[cache_key]

    @staticmethod
    def _maybe_download(ref_audio: str | None) -> tuple[str | None, str | None]:
        """Если ref_audio — URL, скачивает во временный файл.
        Возвращает (local_path, tmp_path_to_cleanup)."""
        if not ref_audio:
            return None, None
        parsed = urlparse(ref_audio)
        if parsed.scheme in ("http", "https"):
            suffix = os.path.splitext(parsed.path)[1] or ".wav"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="omnivoice_ref_")
            os.close(fd)
            logger.debug("Скачивание ref_audio %s -> %s", ref_audio, tmp_path)
            with httpx.stream("GET", ref_audio, timeout=60, follow_redirects=True) as r:
                r.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            return tmp_path, tmp_path
        return ref_audio, None

    @staticmethod
    def _wav_to_mp3(wav_path: str, mp3_path: str) -> None:
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame",
             "-qscale:a", "2", mp3_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def generate(self, text: str, params: dict) -> str:
        p = self.resolve_params(params)

        device = self._resolve_device(p["device"])
        model = self._load_model(p["model_id"], device, p["dtype"])

        gen_kwargs: dict = {"text": text}
        for key in ("ref_text", "instruct", "num_step", "speed",
                    "duration", "language_id", "seed"):
            val = p.get(key)
            if val is not None:
                gen_kwargs[key] = val

        # пропускаем произвольные доп. kwargs (для forward-compat)
        declared = set(self.PARAMS.keys()) | {"text"}
        for key, val in p.items():
            if key not in declared and val is not None:
                gen_kwargs[key] = val

        ref_local, tmp_to_cleanup = self._maybe_download(p.get("ref_audio"))
        if ref_local:
            gen_kwargs["ref_audio"] = ref_local

        logger.debug("OmniVoice generate: text_len=%d kwargs=%s",
                     len(text), {k: v for k, v in gen_kwargs.items() if k != "text"})

        try:
            audio = model.generate(**gen_kwargs)
        finally:
            if tmp_to_cleanup and os.path.exists(tmp_to_cleanup):
                try:
                    os.remove(tmp_to_cleanup)
                except OSError:
                    pass

        # audio может быть list[np.ndarray] или np.ndarray
        wav_data = audio[0] if isinstance(audio, (list, tuple)) else audio

        uid = uuid.uuid4().hex[:8]
        wav_path = os.path.join(_settings.temp_dir, f"omnivoice_{uid}.wav")
        mp3_path = os.path.join(_settings.temp_dir, f"omnivoice_{uid}.mp3")

        sf.write(wav_path, wav_data, self._SAMPLE_RATE)
        try:
            self._wav_to_mp3(wav_path, mp3_path)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

        logger.debug("Аудио сохранено: %s (%d байт)", mp3_path, os.path.getsize(mp3_path))
        return mp3_path
