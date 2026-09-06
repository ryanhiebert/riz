import json
from dataclasses import dataclass
from typing import override


@dataclass(frozen=True)
class String:
    value: str

    @override
    def __str__(self) -> str:
        return json.dumps(self.value, ensure_ascii=False)
