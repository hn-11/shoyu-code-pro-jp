"""Unit tests for scripts/verifylib.py (the pieces shared by the verify /
packaging scripts) that need no font files."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verifylib  # noqa: E402


def test_static_faces_skips_variable_fonts_and_sorts(tmp_path):
    for name in ("SumiMoji-Regular.otf", "SumiMoji-Italic[wght].otf", "SumiMoji[wght].otf",
                 "SumiMoji-Bold.otf", "SumiMojiTerm-Regular.otf", "Other-Regular.otf"):
        (tmp_path / name).write_bytes(b"")
    got = [p.name for p in verifylib.static_faces(tmp_path, "SumiMoji")]
    assert got == ["SumiMoji-Bold.otf", "SumiMoji-Regular.otf"]


def test_static_faces_empty_dir(tmp_path):
    assert verifylib.static_faces(tmp_path, "SumiMoji") == []


def test_checker_tallies_and_prints(capsys):
    check = verifylib.Checker()
    assert check(True, "fine") is True
    assert check.failed is False and check.exit_code() == 0
    assert check(False, "broken") is False
    assert check.failed is True and check.exit_code() == 1
    assert check(True, "still fine") is True
    assert check.failed is True      # a later pass does not clear a failure
    out = capsys.readouterr().out.splitlines()
    assert out == ["ok   fine", "FAIL broken", "ok   still fine"]


def test_hint_ops_cover_every_type2_hint_operator():
    want = {"hstem", "vstem", "hstemhm", "vstemhm", "hintmask", "cntrmask"}
    assert set(verifylib.HINT_OPS) == want
