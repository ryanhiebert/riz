from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Unit:
    """The absence of a meaningful value — what a binding evaluates to.

    A real value (not host ``None``); the REPL suppresses it on display.
    """

    @override
    def __str__(self):
        return "()"
