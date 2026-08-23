import riz


def test_public_embedding_api_defines_and_looks_up_values():
    runtime = riz.Runtime()
    assert runtime.define("answer", riz.Integer(42)) == riz.Ok(riz.Unit())
    assert runtime.lookup("answer") == riz.Ok(riz.Integer(42))
    assert runtime.evaluate("answer + 1") == riz.Ok(riz.Integer(43))


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
