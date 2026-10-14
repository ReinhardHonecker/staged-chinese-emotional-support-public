import subprocess
import sys
from pathlib import Path


def test_teacher_label_cli_uses_getpass_instead_of_api_key_argument():
    script = Path(__file__).resolve().parents[1] / "scripts" / "label_soulchat.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--provider" in completed.stdout
    assert "--base-url" in completed.stdout
    assert "--model" in completed.stdout
    assert "--api-key" not in completed.stdout
