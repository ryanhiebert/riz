from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Boolean:
    value: bool

    @override
    def __str__(self):
        return "True" if self.value else "False"
