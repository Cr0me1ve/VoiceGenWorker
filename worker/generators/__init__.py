from worker.generators.base import BaseTTSGenerator, ParamSpec
from worker.generators.silero import SileroGenerator

# Registry: model_name -> generator class
_REGISTRY: dict[str, type[BaseTTSGenerator]] = {
    "silero": SileroGenerator,
}


def get_generator(name: str) -> BaseTTSGenerator:
    """Return an instance of the requested generator."""
    name = name.lower()
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"Unknown generator '{name}'. Available: {available}")
    return _REGISTRY[name]()


def register_generator(name: str, cls: type[BaseTTSGenerator]) -> None:
    """Register a custom generator at runtime."""
    _REGISTRY[name.lower()] = cls


def list_generators() -> dict:
    """Return all registered generators with their param schemas."""
    return {
        name: cls.params_schema()
        for name, cls in _REGISTRY.items()
    }
