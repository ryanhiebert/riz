import json
from typing import cast

import pytest
import riz

from .browser_adapter import Reply, Session


def run(session: Session, source: str) -> tuple[str, str, bool]:
    result = cast(Reply, json.loads(session.start(source)))
    output = result["output"]
    for _ in range(1000):
        if result["status"] == "finished":
            return output, result["text"], result["error"]
        result = cast(Reply, json.loads(session.step(1)))
        output += result["output"]
    raise AssertionError("entry did not finish")


def test_session_values_bindings_and_exact_arithmetic():
    session = Session()
    assert run(session, "x = 5 / 2") == ("", "", False)
    assert run(session, "x + x") == ("", "5", False)
    assert run(session, "()") == ("", "", False)
    assert run(session, " \n ") == ("", "", False)


def test_nested_prints_keep_their_order_before_the_result():
    session = Session()
    assert run(session, 'fn inner(): print("héllo")\nfn outer(): inner()\n'
               + 'outer()\nprint("second")\n5 / 2') == ("héllo\nsecond\n", "5/2", False)


def test_failed_entry_does_not_commit_bindings_but_output_remains():
    session = Session()
    assert run(session, 'x = 42\nprint("before")\n1 / 0') == (
        "before\n", "error: RizDivisionByZeroError", True)
    assert run(session, "x") == ("", "error: RizNameError", True)
    assert run(session, "True + 1") == ("", "error: RizTypeError", True)
    assert run(session, "1 +") == ("", "error: RizParseError", True)
    assert run(session, "2 + 3") == ("", "5", False)


def test_output_is_delivered_before_resuming_into_a_native_host_effect():
    session = Session()
    output: list[str] = []

    def host_write(runtime: riz.Runtime, arguments: riz.Product[riz.Value]) -> riz.NativeResult:
        del runtime, arguments
        output.append("second\n")
        return riz.Ok(riz.Unit())

    assert session.runtime.define_function(
        "host_write", riz.FunctionType(riz.ProductType(()), riz.ProductType(())), host_write
    ) == riz.Ok(riz.Unit())
    _ = session.start('print("first")\nhost_write()\nprint("third")')
    while True:
        result = cast(Reply, json.loads(session.step()))
        if result["output"]:
            output.append(result["output"])
        if result["status"] == "finished":
            break
    assert output == ["first\n", "second\n", "third\n"]


def test_continuation_uses_riz_tokens_and_blank_line_finishes_block():
    session = Session()
    assert json.loads(session.start("fn half(n):", False))["status"] == "continuation"
    assert json.loads(session.start("fn half(n):\n  n / 2", False))["status"] == "continuation"
    assert json.loads(session.start("fn half(n):\n  n / 2\n", False))["status"] == "running"
    while json.loads(session.step())["status"] != "finished":
        pass
    assert run(session, "half(5)") == ("", "5/2", False)
    assert json.loads(session.start('\":\"', False))["status"] == "running"
    session.stop()


def test_stop_discards_unfinished_bindings_and_preserves_previous_entries():
    session = Session()
    assert run(session, "n = 42") == ("", "", False)
    assert json.loads(session.start("n = 99\nwhile True: ()"))["status"] == "running"
    assert json.loads(session.step(3))["status"] == "running"
    session.stop()
    assert run(session, "n") == ("", "42", False)
    assert run(session, "6 / 4") == ("", "3/2", False)


def test_unknown_suspensions_remain_host_errors():
    session = Session()
    def wait(runtime: riz.Runtime, arguments: riz.Product[riz.Value]) -> riz.NativeResult:
        del runtime, arguments
        return riz.Suspend(object())
    assert session.runtime.define_function(
        "wait", riz.FunctionType(riz.ProductType(()), riz.ProductType(())), wait
    ) == riz.Ok(riz.Unit())
    _ = session.start("wait()")
    with pytest.raises(RuntimeError, match="cannot resolve"):
        _ = session.step()


def test_session_rejects_overlapping_entries():
    session = Session()
    _ = session.start("while True: ()")
    with pytest.raises(RuntimeError, match="already running"):
        _ = session.start("2 + 3")
