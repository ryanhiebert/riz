"""Build the current checkout into a content-addressed browser wheel."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> None:
    web = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="riz-browser-wheel-") as directory:
        _ = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", directory],
            cwd=web.parent,
            check=True,
        )
        wheel, = Path(directory).glob("*.whl")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        target = web / "public" / "runtime" / digest / wheel.name
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copyfile(wheel, target)
        _ = (web / "public" / "runtime" / "riz-wheel.json").write_text(
            json.dumps({"wheel": f"{digest}/{wheel.name}"}) + "\n", encoding="utf-8"
        )
        # Only clean our own obsolete content-addressed build directories.
        for previous in target.parent.parent.iterdir():
            if (previous.is_dir() and len(previous.name) == 64
                    and all(char in "0123456789abcdef" for char in previous.name)
                    and previous.name != digest):
                shutil.rmtree(previous)
    print(f"Prepared {wheel.name}")


if __name__ == "__main__":
    main()
