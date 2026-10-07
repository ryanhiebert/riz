"""Drive a Riz computation with Python's asyncio event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .eval import Value
from .result import Result
from .runtime import Computation, Finished, Suspended, Yielded


type Resolver = Callable[[object], Awaitable[Value]]


async def run(computation: Computation, resolve: Resolver) -> Result[Value]:
    """Run a computation, delegating suspension requests to ``resolve``.

    Resolver exceptions, including cancellation, remain Python exceptions. Riz
    exception injection is intentionally outside this adapter until the language
    has an exception model.
    """
    event = computation.advance()
    while True:
        match event:
            case Yielded():
                await asyncio.sleep(0)
                event = computation.advance()
            case Suspended(request):
                value = await resolve(request)
                event = computation.resume(value)
            case Finished(result):
                return result
