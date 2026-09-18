from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Unit:
    """The compact runtime representation of the empty product.

    A real value (not host ``None``); bindings return it and the REPL suppresses
    it on display.
    """

    @override
    def __str__(self):
        return "()"
