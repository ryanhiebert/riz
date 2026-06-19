"""Entry point: `python -m riz` launches the REPL."""

from .repl import repl

if __name__ == "__main__":  # runs under `python -m riz`, not on pytest import
    repl()
