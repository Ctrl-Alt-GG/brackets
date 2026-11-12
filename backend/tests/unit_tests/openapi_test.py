import os
import subprocess
import sys
from pathlib import Path


def test_openapi_up_to_date(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.json"
    subprocess.run(
        [sys.executable, "cli.py", "generate-openapi", "--output", str(generated)],
        env={**os.environ, "API_PREFIX": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert Path("openapi/openapi.json").read_text() == generated.read_text()
