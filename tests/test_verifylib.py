"""Unit tests for scripts/verifylib.py (the pieces shared by the verify /
packaging scripts) that need no font files."""

import sys
from pathlib import Path

from fontTools.misc.psCharStrings import T2CharString

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


# --- glyph_has_hint ----------------------------------------------------------

class _Private:
    def __init__(self, subrs):
        self.Subrs = subrs


def _cs(program, private=None, global_subrs=None):
    cs = T2CharString(program=list(program), private=private,
                      globalSubrs=global_subrs if global_subrs is not None else [])
    return cs


def test_glyph_has_hint_sees_a_direct_hint_and_a_bare_outline():
    assert verifylib.glyph_has_hint(_cs([10, 20, "hstem", 0, 0, "rmoveto", "endchar"]))
    assert not verifylib.glyph_has_hint(_cs([0, 0, "rmoveto", 100, "hlineto", "endchar"]))


def test_glyph_has_hint_follows_local_and_global_subroutines():
    # bias 107 for small subr indexes: operand -107 -> subr 0
    local = [_cs([10, 20, "vstem", "return"])]
    glob = [_cs(["hintmask", "return"])]
    via_local = _cs([-107, "callsubr", "endchar"], private=_Private(local), global_subrs=glob)
    via_global = _cs([-107, "callgsubr", "endchar"], private=_Private(local), global_subrs=glob)
    plain = _cs(["endchar"], private=_Private(local), global_subrs=glob)
    assert verifylib.glyph_has_hint(via_local)
    assert verifylib.glyph_has_hint(via_global)
    assert not verifylib.glyph_has_hint(plain)


def test_glyph_has_hint_does_not_loop_on_a_recursive_subroutine():
    local = [_cs([-107, "callsubr", "return"])]      # subr 0 calls itself
    cs = _cs([-107, "callsubr", "endchar"], private=_Private(local))
    assert not verifylib.glyph_has_hint(cs)


def test_hmtx_mismatches_reports_widths_and_bearings():
    from test_build import _extents_font
    font, _ = _extents_font()
    assert verifylib.hmtx_mismatches(font) == ([], [])
    font["hmtx"].metrics["A"] = (650, 0)       # width off by 50, lsb off by 20
    font["hmtx"].metrics["B"] = (700, -41)     # a rounding hair off: fine
    widths, bearings = verifylib.hmtx_mismatches(font)
    assert widths == [("A", 600, 650)]
    assert bearings == [("A", 20, 0)]
