import subprocess
import sys


def test_import_twyf_works() -> None:
    import twyf

    assert twyf.__version__ == "2.0.0a1"


def test_twyf_help_exits_zero() -> None:
    result = subprocess.run([sys.executable, "-m", "twyf.cli", "--help"], check=False, capture_output=True, text=True)
    assert result.returncode == 0
    assert "twyf" in result.stdout
