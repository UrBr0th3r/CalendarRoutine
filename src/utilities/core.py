from abc import ABC, abstractmethod
from pathlib import Path as _Path

__all__ = ["ImmutableMeta", "Paths", "Singleton", "Serializable"]

from typing import Any

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
    EVENTS = _ROOT / "resources"
    SRC = _ROOT / "src"

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Serializable(ABC):
    @abstractmethod
    def JSON(self) -> dict[str, Any]:
        ...