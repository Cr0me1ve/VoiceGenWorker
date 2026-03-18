from abc import ABC, abstractmethod
from typing import Any
from venv import logger


class ParamSpec:
    """
    Descriptor for a single generator parameter.

    Example:
        ParamSpec(default="eugene", type_=str, description="Speaker voice name")
    """

    def __init__(self, default: Any, type_: type, description: str = ""):
        self.default = default
        self.type_ = type_
        self.description = description

    def cast(self, value: Any) -> Any:
        """Cast value to the declared type."""
        if value is None:
            return self.default
        try:
            return self.type_(value)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Cannot cast {value!r} to {self.type_.__name__}: {e}"
            )


class BaseTTSGenerator(ABC):
    """
    Abstract base for all TTS generators.

    Subclasses declare their accepted parameters via the PARAMS class variable:

        PARAMS: dict[str, ParamSpec] = {
            "speaker":      ParamSpec("eugene", str,  "Voice speaker name"),
            "sample_rate":  ParamSpec(48000,    int,  "Audio sample rate"),
        }

    Call self.resolve_params(raw) in generate() to get a validated dict.

    To add a new generator:
    1. Create worker/generators/my_tts.py, subclass BaseTTSGenerator
    2. Declare PARAMS
    3. Implement generate(text, params)
    4. Register in worker/generators/__init__.py
    """

    # Each subclass overrides this with its own params
    PARAMS: dict[str, ParamSpec] = {}

    def resolve_params(self, raw: dict) -> dict:
        logger.debug(f"RAW PARAMS: {raw}")
        """
        Merge incoming raw dict with declared defaults, cast to correct types.
        Unknown keys are passed through as-is (for forward compatibility).
        """
        resolved = {}
        for name, spec in self.PARAMS.items():
            resolved[name] = spec.cast(raw.get(name))
        # pass-through unknown keys
        for key, val in raw.items():
            if key not in resolved:
                resolved[key] = val
        return resolved

    @classmethod
    def params_schema(cls) -> dict:
        """Return human-readable schema of accepted params."""
        return {
            name: {
                "default": spec.default,
                "type": spec.type_.__name__,
                "description": spec.description,
            }
            for name, spec in cls.PARAMS.items()
        }

    @abstractmethod
    def generate(self, text: str, params: dict) -> str:
        """
        Generate audio from text.

        Args:
            text:   Input text to synthesize.
            params: Validated dict from resolve_params().

        Returns:
            Path to saved audio file, e.g. 'temp/silero_eugene_abc123.mp3'
        """
        ...
