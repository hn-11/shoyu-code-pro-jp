"""scripts/harmonize_latin.py: the package job's family-wide win
metrics pass over an assembled dist/."""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import harmonize_latin  # noqa: E402
from conftest import make_font  # noqa: E402


def _face(path, ascent, descent):
    make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600},
              os2={"usWinAscent": ascent, "usWinDescent": descent}).save(path)


def test_main_harmonizes_each_family_and_skips_empty_ones(tmp_path, capsys, monkeypatch):
    latin = tmp_path / "latin"
    nerd = tmp_path / "nerd" / "latin"
    for d in (latin, nerd, tmp_path / "latin" / "term"):
        d.mkdir(parents=True)
    _face(latin / "SumiMoji-Regular.otf", 1000, 300)
    _face(latin / "SumiMoji-Bold.otf", 1100, 250)
    _face(latin / "SumiMoji[wght].otf", 5000, 5000)      # a VF: never touched
    _face(nerd / "SumiMojiNF-Regular.otf", 1200, 200)
    _face(nerd / "SumiMojiNF-Bold.otf", 1000, 400)

    monkeypatch.setattr(sys, "argv", ["harmonize_latin.py", str(tmp_path)])
    harmonize_latin.main()

    def win(p):
        os2 = TTFont(p)["OS/2"]
        return os2.usWinAscent, os2.usWinDescent
    assert win(latin / "SumiMoji-Regular.otf") == win(latin / "SumiMoji-Bold.otf") == (1100, 300)
    assert win(nerd / "SumiMojiNF-Regular.otf") == win(nerd / "SumiMojiNF-Bold.otf") == (1200, 400)
    assert win(latin / "SumiMoji[wght].otf") == (5000, 5000)
    out = capsys.readouterr().out
    assert "latin/SumiMoji: win metrics 1100/300 over 2 faces" in out
    assert "latin/term/SumiMojiTerm: no faces, skipped" in out
    assert "nerd/latin/SumiMojiNF: win metrics 1200/400 over 2 faces" in out
