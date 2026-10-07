"""Entry point for `python -m riz`."""

from .cli import main

if __name__ == "__main__":  # runs under `python -m riz`, not on pytest import
    raise SystemExit(main())
