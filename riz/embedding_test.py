from collections.abc import Mapping

import riz


def test_public_embedding_api_advances_a_computation_through_checkpoints():
    runtime = riz.Runtime()
    started = runtime.start("value = 41\nvalue + 1")
    assert isinstance(started, riz.Ok)

    computation: riz.Computation = started.value
    event: riz.ComputationEvent = computation.advance()
    assert event == riz.Yielded()
    assert computation.advance() == riz.Finished(riz.Ok(riz.Integer(42)))


def test_public_embedding_api_defines_and_looks_up_values():
    runtime = riz.Runtime()
    assert runtime.define("answer", riz.Integer(42)) == riz.Ok(riz.Unit())
    assert runtime.lookup("answer") == riz.Ok(riz.Integer(42))
    assert runtime.evaluate("answer + 1") == riz.Ok(riz.Integer(43))


def test_public_embedding_api_supports_strings():
    runtime = riz.Runtime()
    assert runtime.define("module_name", riz.String("machine")) == riz.Ok(riz.Unit())
    assert runtime.evaluate("module_name") == riz.Ok(riz.String("machine"))


def test_host_can_expose_an_existing_python_object():
    class Robot:
        def __init__(self):
            self.position: int = 0

        def move(self, distance: int) -> None:
            self.position += distance

    robot = Robot()
    runtime = riz.Runtime()
    assert runtime.define("robot", riz.PythonValue(robot)) == riz.Ok(riz.Unit())
    source = (
        'match robot.attr("move"):\n'
        "  Ok(move):\n"
        "    match move(10):\n"
        "      Ok(result): result.unit()\n"
        "      Err(error): None\n"
        "  Err(error): None"
    )
    assert runtime.evaluate(source) == riz.Ok(riz.Some(riz.Unit()))
    assert robot.position == 10


def test_host_products_have_structural_types():
    runtime = riz.Runtime()
    point = riz.Product((riz.Integer(20), riz.Integer(22)))
    assert runtime.define("point", point) == riz.Ok(riz.Unit())
    assert runtime.evaluate("(x, y) = point") == riz.Ok(riz.Unit())
    assert runtime.evaluate("x + y") == riz.Ok(riz.Integer(42))


def test_host_definition_can_rebind_an_existing_name():
    runtime = riz.Runtime()
    assert runtime.define("value", riz.Boolean(True)) == riz.Ok(riz.Unit())
    assert runtime.define("value", riz.Integer(41)) == riz.Ok(riz.Unit())
    assert runtime.evaluate("value + 1") == riz.Ok(riz.Integer(42))


def test_lookup_and_invalid_host_names_return_name_errors():
    runtime = riz.Runtime()
    missing = runtime.lookup("missing")
    invalid = runtime.define("not a Riz name", riz.Integer(1))
    reserved = runtime.define("True", riz.Integer(1))
    assert isinstance(missing, riz.Err)
    assert isinstance(invalid, riz.Err)
    assert isinstance(reserved, riz.Err)


def test_typed_native_function_is_callable_from_riz():
    runtime = riz.Runtime()
    signature = riz.FunctionType(
        riz.ProductType((riz.Type.INTEGER, riz.Type.INTEGER)),
        riz.Type.INTEGER,
    )

    def add(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.Result[riz.Value]:
        del runtime
        left, right = arguments.items
        assert isinstance(left, riz.Integer) and isinstance(right, riz.Integer)
        return riz.Ok(riz.Integer(left.value + right.value))

    assert runtime.define_function("host_add", signature, add) == riz.Ok(riz.Unit())
    assert runtime.evaluate("host_add(20, 22)") == riz.Ok(riz.Integer(42))
    wrong = runtime.evaluate("host_add(True, 1)")
    assert isinstance(wrong, riz.Err)


def test_native_function_return_is_checked_against_its_signature():
    runtime = riz.Runtime()
    signature = riz.FunctionType(riz.ProductType(()), riz.Type.INTEGER)

    def lies(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.Result[riz.Value]:
        del runtime, arguments
        return riz.Ok(riz.Boolean(True))

    assert runtime.define_function("lies", signature, lies) == riz.Ok(riz.Unit())
    result = runtime.evaluate("lies()")
    assert isinstance(result, riz.Err)


def test_extension_uses_registration_api_and_loads_atomically():
    runtime = riz.Runtime()
    answer_type = riz.FunctionType(riz.ProductType(()), riz.Type.INTEGER)

    def answer(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.Result[riz.Value]:
        del runtime, arguments
        return riz.Ok(riz.Integer(42))

    def extension(runtime: riz.Runtime) -> riz.Result[riz.Unit]:
        return runtime.define_function("answer", answer_type, answer)

    assert runtime.load(extension) == riz.Ok(riz.Unit())
    assert runtime.evaluate("answer()") == riz.Ok(riz.Integer(42))

    def broken_extension(runtime: riz.Runtime) -> riz.Result[riz.Unit]:
        assert runtime.define("temporary", riz.Integer(1)) == riz.Ok(riz.Unit())
        return riz.Err(object())

    assert isinstance(runtime.load(broken_extension), riz.Err)
    assert isinstance(runtime.lookup("temporary"), riz.Err)


def test_host_can_call_an_inferred_riz_function_directly():
    runtime = riz.Runtime()
    assert runtime.evaluate("fn double(value): value + value") == riz.Ok(riz.Unit())
    found = runtime.lookup("double")
    assert isinstance(found, riz.Ok)
    assert runtime.call(
        found.value, riz.Product((riz.Integer(21),))
    ) == riz.Ok(riz.Integer(42))
    assert runtime.call(
        found.value, riz.Product((riz.Ratio(1, 4),))
    ) == riz.Ok(riz.Ratio(1, 2))
    wrong = runtime.call(found.value, riz.Product((riz.Boolean(True),)))
    assert isinstance(wrong, riz.Err)


def test_host_call_works_for_native_functions_and_rejects_nonfunctions():
    runtime = riz.Runtime()
    signature = riz.FunctionType(
        riz.ProductType((riz.Type.INTEGER,)), riz.Type.INTEGER
    )

    def increment(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.Result[riz.Value]:
        del runtime
        (value,) = arguments.items
        assert isinstance(value, riz.Integer)
        return riz.Ok(riz.Integer(value.value + 1))

    assert runtime.define_function("increment", signature, increment) == riz.Ok(
        riz.Unit()
    )
    found = runtime.lookup("increment")
    assert isinstance(found, riz.Ok)
    assert runtime.call(
        found.value, riz.Product((riz.Integer(41),))
    ) == riz.Ok(riz.Integer(42))
    not_callable = runtime.call(riz.Integer(1), riz.Product(()))
    assert isinstance(not_callable, riz.Err)


def test_nested_closures_retain_their_inferred_types_for_host_calls():
    runtime = riz.Runtime()
    source = "fn make_adder(x):\n  fn add(y): x + y\n  add"
    assert runtime.evaluate(source) == riz.Ok(riz.Unit())
    maker = runtime.lookup("make_adder")
    assert isinstance(maker, riz.Ok)
    made = runtime.call(maker.value, riz.Product((riz.Integer(10),)))
    assert isinstance(made, riz.Ok)
    assert runtime.call(
        made.value, riz.Product((riz.Integer(32),))
    ) == riz.Ok(riz.Integer(42))


def test_registered_modules_are_static_lazy_and_cached():
    runtime = riz.Runtime()
    loads = 0
    interface = riz.ModuleType((("answer", riz.Type.INTEGER),))

    def load(runtime: riz.Runtime) -> riz.Result[Mapping[str, riz.Value]]:
        nonlocal loads
        del runtime
        loads += 1
        return riz.Ok({"answer": riz.Integer(42)})

    assert runtime.register_module("tools", interface, load) == riz.Ok(riz.Unit())
    assert runtime.evaluate("{tools} = use") == riz.Ok(riz.Unit())
    assert loads == 0
    assert runtime.evaluate("{answer} = tools\nanswer") == riz.Ok(riz.Integer(42))
    assert runtime.evaluate("tools.answer") == riz.Ok(riz.Integer(42))
    assert loads == 1


def test_module_use_is_lexically_scoped():
    runtime = riz.Runtime()
    interface = riz.ModuleType((("answer", riz.Type.INTEGER),))
    assert runtime.register_module(
        "tools", interface, lambda runtime: riz.Ok({"answer": riz.Integer(42)})
    ) == riz.Ok(riz.Unit())
    source = "fn get_answer():\n  {answer} = use.tools\n  answer"
    assert runtime.evaluate(source) == riz.Ok(riz.Unit())
    assert runtime.evaluate("get_answer()") == riz.Ok(riz.Integer(42))
    assert isinstance(runtime.lookup("answer"), riz.Err)


def test_module_traversal_does_not_initialize_modules():
    runtime = riz.Runtime()
    parent_loads = 0
    child_loads = 0
    child_interface = riz.ModuleType((("answer", riz.Type.INTEGER),))
    parent_interface = riz.ModuleType((("child", child_interface),))

    def load_child() -> riz.Result[Mapping[str, riz.Value]]:
        nonlocal child_loads
        child_loads += 1
        return riz.Ok({"answer": riz.Integer(42)})

    child = riz.ModuleValue("parent.child", child_interface, load_child)

    def load_parent(runtime: riz.Runtime) -> riz.Result[Mapping[str, riz.Value]]:
        nonlocal parent_loads
        del runtime
        parent_loads += 1
        return riz.Ok({"child": child})

    assert runtime.register_module("parent", parent_interface, load_parent) == riz.Ok(
        riz.Unit()
    )
    assert runtime.evaluate("{child} = use.parent") == riz.Ok(riz.Unit())
    assert (parent_loads, child_loads) == (0, 0)
    assert runtime.evaluate("child.answer") == riz.Ok(riz.Integer(42))
    assert (parent_loads, child_loads) == (1, 1)


def test_unknown_module_members_fail_before_loading():
    runtime = riz.Runtime()
    loads = 0
    interface = riz.ModuleType((("answer", riz.Type.INTEGER),))

    def load(runtime: riz.Runtime) -> riz.Result[Mapping[str, riz.Value]]:
        nonlocal loads
        del runtime
        loads += 1
        return riz.Ok({"answer": riz.Integer(42)})

    assert runtime.register_module("tools", interface, load) == riz.Ok(riz.Unit())
    result = runtime.evaluate("use.tools.missing")
    assert isinstance(result, riz.Err)
    assert loads == 0


def test_module_loader_must_match_its_interface():
    runtime = riz.Runtime()
    interface = riz.ModuleType((("answer", riz.Type.INTEGER),))
    assert runtime.register_module(
        "broken", interface, lambda runtime: riz.Ok({"answer": riz.Boolean(True)})
    ) == riz.Ok(riz.Unit())
    result = runtime.evaluate("use.broken.answer")
    assert isinstance(result, riz.Err)


def test_modules_can_export_checked_native_functions():
    runtime = riz.Runtime()
    signature = riz.FunctionType(
        riz.ProductType((riz.Type.INTEGER,)), riz.Type.INTEGER
    )
    interface = riz.ModuleType((("increment", signature),))

    def increment(
        runtime: riz.Runtime, arguments: riz.Product[riz.Value]
    ) -> riz.Result[riz.Value]:
        del runtime
        (value,) = arguments.items
        assert isinstance(value, riz.Integer)
        return riz.Ok(riz.Integer(value.value + 1))

    function = runtime.native_function("increment", signature, increment)
    assert isinstance(function, riz.Ok)
    assert runtime.register_module(
        "tools", interface, lambda runtime: riz.Ok({"increment": function.value})
    ) == riz.Ok(riz.Unit())
    assert runtime.evaluate("use.tools.increment(41)") == riz.Ok(riz.Integer(42))
