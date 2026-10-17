Changelog
=========

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com).

[0.1] - 2026-10-17
-----------------

Initial experimental release of the Riz programming language.
Requires Python 3.14 or later.

### Added

- Static type inference, exact integers and ratios, products and destructuring,
  and exhaustive matching for `Option` and `Result` variants.
- A Python embedding API with typed host modules, native functions,
  and resumable computations.
- An `asyncio` driver and host-controlled output through suspension requests.
- Command-line script execution and an interactive shell.
- An experimental browser shell running the interpreter through Pyodide.

[0.1]: https://github.com/ryanhiebert/riz/releases/tag/0.1
