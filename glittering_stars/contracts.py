"""Versioned immutable command/event boundaries shared by desktop adapters."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Mode(str, Enum):
    GENERATE = 'generate'
    REPLAY = 'replay'
    LOOP = 'loop'


class Phase(str, Enum):
    IDLE = 'Idle'
    HOLDING = 'Holding'
    GAP = 'Gap'
    PAUSED = 'Paused'
    ERROR = 'Error'


@dataclass(frozen=True)
class Command:
    number: int
    name: str
    payload: tuple[tuple[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Acknowledgement:
    number: int
    accepted: bool
    revision: int
    status: str


@dataclass(frozen=True)
class ConfigRevision:
    number: int
    config: Any
    boundary: str = 'next_generation'
