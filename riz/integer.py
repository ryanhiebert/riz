from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class Integer:
    value: int

    @override
    def __str__(self):
        return str(self.value)
