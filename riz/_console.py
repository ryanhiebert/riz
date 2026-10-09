"""Synchronous execution policy shared by the CLI and interactive shell."""

import sys

from .eval import Value
from .result import Err, Ok, Result
from .runtime import Finished, OutputRequest, Runtime, Suspended
from .unit import Unit


def evaluate(source: str, runtime: Runtime) -> Result[Value]:
    started = runtime.start(source)
    if isinstance(started, Err):
        return started
    computation = started.value
    event = computation.advance()
    while True:
        match event:
            case Finished(result):
                return result
            case Suspended(OutputRequest(text)):
                _ = sys.stdout.write(text)
                event = computation.resume(Ok(Unit()))
            case Suspended():
                raise RuntimeError("console cannot resolve this suspension")
            case _:
                event = computation.advance()
