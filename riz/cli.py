"""Run a Riz script, or open the interactive shell when no file is supplied."""

import argparse
from pathlib import Path
import sys
from typing import cast

from .result import Err
from ._console import evaluate
from .runtime import Runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("file", nargs="?", type=Path, help="UTF-8 Riz script")
    args = parser.parse_args(argv)
    path = cast(Path | None, args.file)
    if path is None:
        from .repl import repl

        repl()
        return 0

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"{path}: error: {error}", file=sys.stderr)
        return 1

    if not source.strip():
        return 0

    result = evaluate(source, Runtime())
    if isinstance(result, Err):
        print(f"{path}: error: {type(result.error).__name__}", file=sys.stderr)
        return 1
    return 0
