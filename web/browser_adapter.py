"""Experimental browser host policy; no browser or event-loop dependencies.

Only JSON text leaves this adapter. Discarding a computation is a shell policy,
not language-level cancellation. Already performed host effects are not undone.
"""

import json
from time import monotonic
from typing import TypedDict, final

import riz
from riz.lex import ColonToken, lex


class Reply(TypedDict):
    status: str
    output: str
    text: str
    error: bool


def reply(status: str, output: str = "", text: str = "", error: bool = False) -> str:
    return json.dumps(Reply(status=status, output=output, text=text, error=error))


@final
class Session:
    def __init__(self):
        self.runtime = riz.Runtime()
        self.computation: riz.Computation | None = None
        self.event: riz.ComputationEvent | None = None
        self.output_pending = False

    def start(self, source: str, force: bool = True) -> str:
        if self.computation is not None:
            raise RuntimeError("an entry is already running")
        if not force and source.split("\n")[-1].strip():
            tokens = lex(source)
            if "\n" in source or (tokens and isinstance(tokens[-1], ColonToken)):
                return reply("continuation")
        if not source.strip():
            return reply("finished")
        started = self.runtime.start(source)
        if isinstance(started, riz.Err):
            return reply("finished", text=f"error: {type(started.error).__name__}", error=True)
        self.computation = started.value
        self.event = None
        return reply("running")

    def step(self, budget: int = 100) -> str:
        computation = self.computation
        if computation is None:
            raise RuntimeError("no entry is running")
        deadline = monotonic() + 0.008
        for _ in range(budget):
            event = self.event
            if self.output_pending:
                self.output_pending = False
                event = computation.resume(riz.Ok(riz.Unit()))
            elif event is None or isinstance(event, riz.Yielded):
                event = computation.advance()
            if isinstance(event, riz.Suspended):
                if not isinstance(event.request, riz.OutputRequest):
                    raise RuntimeError("browser shell cannot resolve this suspension")
                self.event = event
                self.output_pending = True
                # Deliver this output before resuming: a later Python callback
                # may write directly to stdout during the next step.
                return reply("running", output=event.request.text)
            elif isinstance(event, riz.Finished):
                self.stop()
                if isinstance(event.result, riz.Err):
                    return reply("finished", text=f"error: {type(event.result.error).__name__}", error=True)
                text = "" if isinstance(event.result.value, riz.Unit) else str(event.result.value)
                return reply("finished", text=text)
            else:
                self.event = event
            if monotonic() >= deadline:
                break
        return reply("running")

    def stop(self) -> None:
        # Successful entries commit through Runtime; unfinished ones do not.
        self.computation = None
        self.event = None
        self.output_pending = False
