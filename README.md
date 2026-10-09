# Riz

Riz is a statically typed, interpreted, and embeddable programming language with
Python interoperability.

## Aim

Riz is intended to be suitable as a child's first programming language—likely
while programming a robot—and capable enough that they never have to grow out of
it.

That requires a careful compromise between a beginner-friendly language, a
general-purpose language, a microcontroller language, and an extension language.
No one of those roles wins automatically. When they pull in different directions,
Riz should make the trade-off that leaves the language more trustworthy.

Embedding is useful in its own right, but it is also an architectural discipline:
an embeddable language needs modularity, explicit ownership, and clear boundaries
between the language, runtime, and host. A strong extension API should provide an
intentional path all the way down to the machine, much as CPython's extension API
does, without making low-level concerns part of ordinary Riz programming.

## Design values

### Trustworthy defaults

Riz should do the correct thing first and make approximations or lower-level
optimizations available when a programmer intentionally reaches for them.
Floating-point arithmetic is valuable and fast, for example, but it should not be
the incidental default when exact arithmetic is possible. The path from the
simple, correct model to expert control should be gradual and understandable.

### Static certainty without annotation ceremony

Runtime type discovery is too late. Riz should know types statically, while
inferring enough of them that programmers usually do not need to write them out.
Advanced type annotations may constrain or document a program, but they should
not compensate for types inferred from callers or for uncertainty deferred until
execution.

### Immutability first

Riz's preferred types are immutable. Mutable values will exist, including through
foreign-language interoperability, but mutation should be something programmers
choose intentionally rather than encounter incidentally. Transparent conversion
across a host boundary is welcome when the meaning is unambiguous; it must not
quietly give mutable host objects immutable Riz value semantics.

### Both errors and results

Riz needs both catchable exception-style errors and `Result` values. `Result`
types are excellent for modeled failures that callers can reasonably understand
and handle in type-safe ordinary control flow. They cannot enumerate every
unexpected or unexpectable failure without burdening every function and
distorting its useful type. Robust programs still need boundaries that can catch
such failures: the unexpected should itself be expected. Making every failure
exceptional is equally mistaken because it hides outcomes callers should
normally consider. The precise boundary is still being designed, but neither
mechanism should be forced to stand in for the other.

### One language as programs grow

Beginner accessibility must not come from a simplified model that later has to be
discarded. The same semantics should remain useful as a program grows from a
first robot exercise into a larger application or an extension backed by native
code.

## Useful reference points

Riz draws direction from several languages without trying to reproduce any one
of them:

- **Python** as a starting point for beginner friendliness and access to its
  enormous ecosystem, not as a syntax or semantics constraint.
- **Rust** for treating type safety as a primary constraint.
- **Clojure** for an immutability-first mental model.
- **Lua** for embeddability and a small, clear host boundary.
- **MicroPython** for practical programming on microcontrollers.

Familiar Python syntax is useful when it serves Riz, but familiarity is not a
design goal strong enough to preserve a less trustworthy or less coherent
choice.

Zig is the intended long-term implementation language for the core runtime. It
offers direct C interoperability and control over allocation and I/O without
requiring those mechanisms to leak into ordinary Riz source.

## Implementation direction

The current implementation is written in Python. It is both a usable embedding
surface and a place to prove language semantics and runtime boundaries. Python
support is permanent and likely critical to adoption, but the core should
eventually be implemented in Zig. CPython and MicroPython bindings should then be
optional adapters over the same embedding interface being developed here.

There is deliberately no fixed threshold yet for beginning the Zig
implementation. Python work should prove durable language or embedding contracts
and avoid large investments whose value exists only in this interpreter.

Riz is still experimental and does not carry compatibility or deprecation layers.
Once a design improvement is accepted, change the language and embedding API
directly, update their tests and examples, and remove the superseded design.

## Current direction

The implementation currently establishes these pieces of the model:

- Function types are inferred from definitions rather than specialized from
  their callers.
- Exact integers and ratios are ordinary numeric values.
- Products and destructuring are foundational language mechanisms.
- `Option` and `Result` variants support exhaustive matching.
- Host modules are typed, lazy, and independent of a filesystem layout.
- Python interoperability is explicit at the foreign boundary.
- A `Runtime` can define values, native functions, and host modules.
- A `Computation` is a unique, mutable, opaque execution machine.
- Computations report three nonterminal or terminal states:
  `Yielded`, `Suspended(request)`, and `Finished(result)`.
- Ordinary Riz functions may suspend through nested calls without a distinct
  async function type or visible `async`/`await` boundary.
- Native callbacks return `Ok(value)`, `Err(error)`, or `Suspend(request)`.
- Execution policy belongs outside the runtime. A small `asyncio` driver already
  demonstrates resolving opaque suspension requests without coupling the core
  runtime to Python's event loop.

Statement-level yielding is currently a deliberately simple mechanism for
proving resumable execution. It is not intended to be the final scheduling or
preemption policy.

## Important open questions

These areas are intentionally unsettled. Existing experiments and discussions
are evidence, not permission to choose their final design unilaterally:

- Result propagation syntax and whether successful values are ever lifted
  implicitly.
- The boundary between exception-style errors and `Result` values, including
  exception handling, cancellation, and exception injection into suspended
  computations.
- Spawning computations and the eventual concurrency API. Riz wants spawning,
  not arbitrary cloning or forking of execution state.
- User-defined types, generics, traits, and explicit concrete type annotations.
- Riz-defined modules, exports, package-internal imports, and eventual filesystem
  conventions.
- The ownership and identity rules for mutable and foreign values.
- The point at which further Python development should give way to the Zig core.
- The final balance between exact correctness and explicitly selected machine
  representations.

REPL polish, a broad standard library, and a complete scheduler are not current
prerequisites for proving the language and embedding model.

## Guidance for contributors and agents

Details matter in Riz. Syntax, core type semantics, dependencies, and public
embedding APIs can all commit the language to a direction that is difficult to
reverse. Do not finalize those decisions without explicit maintainer input.

Exploration is encouraged. Research prior art, compare alternatives, write tests,
and build reversible prototypes to obtain real evidence. Keep prototypes isolated
and the working tree clean enough that useful work can be separated from discarded
ideas. Clearly distinguish an experiment from an accepted design.

When choosing a useful next project:

1. Start from a gap at the current language/runtime frontier, not from generic
   feature completeness.
2. Do not privilege language semantics, embedding, MicroPython, or Zig preparation
   categorically. Weigh each opportunity against the project principles, how
   quickly it can produce useful evidence, and its risk of leading into a dead
   end.
3. Prefer work that proves a semantic or embedding contract shared by Python,
   Zig, CPython, and MicroPython.
4. Favor correctness, static knowledge, immutable defaults, and explicit host
   boundaries.
5. Avoid building Python-specific machinery unless it validates a portable
   interface or delivers lasting Python interoperability.
6. Use small executable examples and tests to expose design consequences.
7. Bring consequential alternatives and the evidence from prototypes back to the
   maintainer before settling the public design.

## Development

Run a UTF-8 Riz file as a script with:

```console
uv run riz example.riz
```

For example, save this as `example.riz`:

```riz
fn half(n): n / 2
print("Hello from Riz!")
half(5)
```

The script runs as one complete program in a fresh runtime. Its final value is
discarded; only explicit `print` calls produce output. `print(text)` is an
ordinary built-in function taking exactly one String, appending one newline, and
returning Unit. There is no implicit string conversion. Blank
files are a successful no-op. Errors go to stderr and produce a nonzero exit
status. `uv run python -m riz example.riz` works too.

Run the interpreter shell with:

```console
uv run riz
```

Run the test suite and static checker with:

```console
uv run pytest
uv run basedpyright
```

Tests live alongside the implementation. The main public embedding coverage is in
`riz/embedding_test.py`, and the `asyncio` driver is exercised in
`riz/asyncio_test.py`.

## Embedded output

The runtime owns no output stream. Built-in `print` suspends with the public,
immutable `riz.OutputRequest(text)`, whose Python string includes the appended
newline. A host writes or collects `request.text` verbatim and resumes the
computation with `riz.Ok(riz.Unit())`. This works through nested ordinary function calls.
Use `Runtime.start` and the existing `advance`/`resume` boundary; synchronous
`Runtime.evaluate` cannot resolve suspensions. CLI and REPL drivers write requests
to stdout. The async resolver passed to `riz.asyncio.run` handles the same request:

```python
import asyncio
import riz
import riz.asyncio

output: list[str] = []

async def resolve(request: object) -> riz.Result[riz.Value]:
    assert isinstance(request, riz.OutputRequest)
    output.append(request.text)
    return riz.Ok(riz.Unit())

started = riz.Runtime().start('print("Hello from an embedded program!")')
assert isinstance(started, riz.Ok)
assert asyncio.run(riz.asyncio.run(started.value, resolve)) == riz.Ok(riz.Unit())
assert output == ["Hello from an embedded program!\n"]
```

A host may instead resume with `riz.Err(error)` to fail the native call. The
error propagates through Riz execution just like an immediate native failure;
Riz does not yet have syntax to catch it. Resolvers return `Ok(value)` or
`Err(error)`. Python exceptions raised by a resolver or console write still
remain host exceptions; automatic translation and cancellation semantics are
still open questions.
