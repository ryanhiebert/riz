"""Drive a Riz computation with Python's asyncio event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .eval import Value
from .result import Result
from .runtime import Computation, Finished, Suspended, Yielded


type Resolver = Callable[[object], Awaitable[Result[Value]]]


async def run(computation: Computation, resolve: Resolver) -> Result[Value]:
    """Run a computation, delegating suspension requests to ``resolve``.

    Resolvers return Ok(value) or Err(error) to complete the native call.
    Raised Python exceptions, including cancellation, remain host exceptions.
    """
    event = computation.advance()
    while True:
        match event:
            case Yielded():
                await asyncio.sleep(0)
                event = computation.advance()
            case Suspended(request):
                result = await resolve(request)
                event = computation.resume(result)
            case Finished(result):
                return result
