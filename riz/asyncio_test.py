import asyncio
from dataclasses import dataclass

import riz
import riz.asyncio


@dataclass(frozen=True)
class ReadAnswer:
    pass


def test_asyncio_driver_yields_and_resolves_a_suspended_native_call():
    runtime = riz.Runtime()
    signature = riz.FunctionType(riz.ProductType(()), riz.Type.INTEGER)

    def read_answer(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.NativeResult:
        del runtime
        assert not arguments.items
        return riz.Suspend(ReadAnswer())

    assert (
        runtime.define_function("read_answer", signature, read_answer)
        == riz.Ok(riz.Unit())
    )
    started = runtime.start("before = 1\nanswer = read_answer()\nanswer + before")
    assert isinstance(started, riz.Ok)

    async def exercise() -> riz.Result[riz.Value]:
        activity: list[str] = []

        async def observe_yield() -> None:
            activity.append("other task ran")

        async def resolve(request: object) -> riz.Value:
            assert isinstance(request, ReadAnswer)
            activity.append("resolving")
            await asyncio.sleep(0)
            return riz.Integer(41)

        observer = asyncio.create_task(observe_yield())
        result = await riz.asyncio.run(started.value, resolve)
        await observer
        assert activity == ["other task ran", "resolving"]
        return result

    assert asyncio.run(exercise()) == riz.Ok(riz.Integer(42))


def test_asyncio_driver_propagates_resolver_exceptions():
    runtime = riz.Runtime()
    signature = riz.FunctionType(riz.ProductType(()), riz.Type.INTEGER)

    def wait(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.NativeResult:
        del runtime, arguments
        return riz.Suspend("request")

    assert runtime.define_function("wait", signature, wait) == riz.Ok(riz.Unit())
    started = runtime.start("wait()")
    assert isinstance(started, riz.Ok)

    async def resolve(request: object) -> riz.Value:
        assert request == "request"
        raise LookupError("unresolved")

    async def exercise() -> None:
        try:
            _ = await riz.asyncio.run(started.value, resolve)
        except LookupError as error:
            assert str(error) == "unresolved"
        else:
            raise AssertionError("resolver exceptions should propagate")

    asyncio.run(exercise())
