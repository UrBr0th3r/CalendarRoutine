from pathlib import Path as _Path

__all__ = ["ImmutableMeta", "Paths"]

_ROOT = _Path(__file__).resolve().parent.parent.parent

class ImmutableMeta(type):
    """Metaclasse che impedisce la modifica o l'eliminazione degli attributi di classe."""
    def __setattr__(cls, name, value):
        raise AttributeError(f"Impossibile modificare '{name}': la classe '{cls.__name__}' è immutabile.")

    def __delattr__(cls, name):
        raise AttributeError(f"Impossibile eliminare '{name}': la classe '{cls.__name__}' è immutabile.")

class Paths(metaclass=ImmutableMeta):
    PROJECT = _ROOT
    PRIVATE = _ROOT / "private"
    OAUTH = _ROOT / "private" / "OAuth"
    EVENTS = _ROOT / "events"
    SRC = _ROOT / "src"

