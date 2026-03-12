import os
import uuid
import torch

from worker.config import get_settings
from worker.generators.base import BaseTTSGenerator, ParamSpec

_settings = get_settings()


class SileroGenerator(BaseTTSGenerator):
    """
    TTS via Silero (snakers4/silero-models).

    Params:
        speaker       - voice name (eugene, aidar, baya, kseniya, xenia, random)
        sample_rate   - 8000 | 24000 | 48000
        language      - ru | en | de | es | fr | ...
        speaker_model - model variant (v5_ru, v3_en, ...)
    """

    PARAMS = {
        "speaker":       ParamSpec("eugene",  str, "Silero speaker name (eugene, aidar, baya, kseniya, xenia, random)"),
        "sample_rate":   ParamSpec(48000,     int, "Output sample rate: 8000, 24000 or 48000"),
        "language":      ParamSpec("ru",      str, "Language code (ru, en, de, ...)"),
        "speaker_model": ParamSpec("v5_ru",   str, "Silero model variant (v5_ru, v3_en, ...)"),
    }

    # Class-level cache: avoids re-downloading on every task
    _model_cache: dict[str, object] = {}

    def _load_model(self, language: str, speaker_model: str):
        cache_key = f"{language}_{speaker_model}"
        if cache_key not in SileroGenerator._model_cache:
            model, _ = torch.hub.load(
                "snakers4/silero-models",
                "silero_tts",
                language=language,
                speaker=speaker_model,
            )
            SileroGenerator._model_cache[cache_key] = model
        return SileroGenerator._model_cache[cache_key]

    def generate(self, text: str, params: dict) -> str:
        p = self.resolve_params(params)

        model = self._load_model(p["language"], p["speaker_model"])

        filename = f"silero_{p['speaker']}_{uuid.uuid4().hex[:8]}.mp3"
        file_path = os.path.join(_settings.temp_dir, filename)

        model.save_wav(
            text=text,
            speaker=p["speaker"],
            sample_rate=p["sample_rate"],
            audio_path=file_path,
        )

        return file_path
