"""scripts/nerdpatch.py: the Nerd Fonts naming, the symbols graft and
the face selection — no font files needed."""

import io
import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import nerdpatch  # noqa: E402


@pytest.mark.parametrize("name, want", [
    ("Sumi Moji JP", "Sumi Moji JP Nerd Font Mono"),
    ("Sumi Moji JP Term", "Sumi Moji JP Term Nerd Font Mono"),
    ("Sumi Moji JP Term SemiBold Italic", "Sumi Moji JP Term Nerd Font Mono SemiBold Italic"),
    ("SumiMojiJPTerm-BoldItalic", "SumiMojiJPTermNFM-BoldItalic"),
    ("SumiMojiJP-Light", "SumiMojiJPNFM-Light"),
    ("Sumi Moji", "Sumi Moji Nerd Font Mono"),
    ("SumiMoji-RegularItalic", "SumiMojiNFM-RegularItalic"),
    ("5.0.0;SUMI;SumiMojiJP-Regular", "5.0.0;SUMI;SumiMojiJPNFM-Regular"),
    ("Version 5.0.0;Sumi Moji JP;SHS 2.005", "Version 5.0.0;Sumi Moji JP Nerd Font Mono;SHS 2.005"),
    ("Source Han Sans", "Source Han Sans"),
])
def test_nf_name(name, want):
    assert nerdpatch.nf_name(name) == want


def _rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()


def _face(family="Sumi Moji JP", ps="SumiMojiJP-Regular", win=(1160, 288)):
    """A plain CFF face like ours in the parts that matter: 'A' in a 600
    cell, Source Code Pro's line box, a BMP-only cmap."""
    charstrings = {}
    pen = T2CharStringPen(600, None)
    charstrings[".notdef"] = pen.getCharString()
    pen = T2CharStringPen(600, None)
    _rect(pen, 50, 0, 550, 655)
    charstrings["A"] = pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({ord("A"): "A"})
    fb.setupCFF(ps, {"FullName": ps}, charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 50)})
    fb.setupHorizontalHeader(ascent=984, descent=-273)
    fb.setupNameTable({"familyName": family, "styleName": "Regular", "psName": ps,
                       "uniqueFontIdentifier": f"5.0.0;SUMI;{ps}"})
    fb.setupOS2(usWinAscent=win[0], usWinDescent=win[1])
    fb.setupPost()
    buf = io.BytesIO()
    fb.font.save(buf)
    buf.seek(0)
    return TTFont(buf)


def _symbols():
    """A Symbols Nerd Font Mono in miniature: a 2048 em, the 1638/-410
    line box, every glyph in a 2048 cell — an icon filling the em box at
    U+E000, a Powerline separator filling the line box at U+E0B0, a
    supplementary-plane icon at U+F0001, and 'A', which a face already
    has."""
    fb = FontBuilder(2048, isTTF=True)
    glyphs, cmap, metrics = {}, {}, {".notdef": (2048, 0)}
    boxes = {"icon": (0, 0, 2048, 2048), "pl": (0, -410, 2048, 1638),
             "far": (512, 0, 1536, 1024), "A": (0, 0, 1000, 1000)}
    for name, box in boxes.items():
        pen = TTGlyphPen(None)
        _rect(pen, *box)
        glyphs[name] = pen.glyph()
        metrics[name] = (2048, box[0])
    pen = TTGlyphPen(None)
    glyphs[".notdef"] = pen.glyph()
    cmap = {0xE000: "icon", 0xE0B0: "pl", 0xF0001: "far", ord("A"): "A"}
    fb.setupGlyphOrder([".notdef", *boxes])
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=1638, descent=-410)
    fb.setupNameTable({"familyName": "Symbols Nerd Font Mono", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


def _bounds(font, name):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.bounds


def test_icon_transforms_fit_the_cell_and_centre_the_line_box():
    uniform, powerline = nerdpatch.icon_transforms(_face(), _symbols())
    k = 600 / 2048
    assert uniform[0] == uniform[3] == pytest.approx(k)
    # the symbols' line box centre (614) lands on ours (355.5)
    assert k * 614 + uniform[5] == pytest.approx(355.5)
    assert powerline[0] == pytest.approx(k)
    assert -410 * powerline[3] + powerline[5] == pytest.approx(-273)
    assert 1638 * powerline[3] + powerline[5] == pytest.approx(984)


def test_graft_symbols_appends_one_cell_icons_the_face_lacks():
    face = _face()
    assert nerdpatch.graft_symbols(face, _symbols()) == 3       # not 'A'
    cmap = face.getBestCmap()
    assert cmap[ord("A")] == "A"
    icon, pl, far = cmap[0xE000], cmap[0xE0B0], cmap[0xF0001]
    assert {face["hmtx"][g][0] for g in (icon, pl, far)} == {600}
    x0, y0, x1, y1 = _bounds(face, icon)
    assert (x0, x1) == (0, 600)
    assert y0 == pytest.approx(176, abs=1) and y1 == pytest.approx(776, abs=1)
    assert _bounds(face, pl) == (0, -273, 600, 984)             # stretched to the line
    x0, y0, x1, y1 = _bounds(face, far)
    assert x1 - x0 == pytest.approx(300, abs=1)                # half the em, half the cell
    # the supplementary-plane icon needed a format 12 subtable
    assert any(t.format == 12 and 0xF0001 in t.cmap for t in face["cmap"].tables)
    assert face["maxp"].numGlyphs == 5


def test_rename_splices_the_marker_into_every_family_name():
    face = _face()
    assert nerdpatch.rename(face) == "SumiMojiJPNFM-Regular"
    name = face["name"]
    assert name.getDebugName(1) == "Sumi Moji JP Nerd Font Mono"
    assert name.getDebugName(3) == "5.0.0;SUMI;SumiMojiJPNFM-Regular"
    assert name.getDebugName(6) == "SumiMojiJPNFM-Regular"
    assert face["CFF "].cff.fontNames[0] == "SumiMojiJPNFM-Regular"


def test_sources_for_paths_names_and_everything(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    latin = dist / "latin"
    latin.mkdir(parents=True)
    for name in ("SumiMojiJP-Light.otf", "SumiMojiJPTerm-Light.otf"):
        (dist / name).write_bytes(b"")
    for name in ("SumiMoji-Light.otf", "SumiMoji-LightItalic.otf", "SumiMoji[wght].otf"):
        (latin / name).write_bytes(b"")
    monkeypatch.setattr(nerdpatch, "DIST", dist)
    monkeypatch.setattr(nerdpatch, "LATIN_DIR", latin)
    monkeypatch.setattr(nerdpatch, "OUT", dist / "nerd")
    monkeypatch.setattr(nerdpatch, "LATIN_OUT", dist / "nerd" / "latin")

    everything = nerdpatch.sources_for([])
    assert [p.name for p, _ in everything] == [
        "SumiMojiJP-Light.otf", "SumiMojiJPTerm-Light.otf",
        "SumiMoji-Light.otf", "SumiMoji-LightItalic.otf"]      # no VF
    assert [out.name for _, out in everything] == ["nerd", "nerd", "latin", "latin"]
    assert [p.name for p, _ in nerdpatch.sources_for(["Term"])] == ["SumiMojiJPTerm-Light.otf"]
    assert [p.name for p, _ in nerdpatch.sources_for(["Term", "Italic"])] == [
        "SumiMojiJPTerm-Light.otf", "SumiMoji-LightItalic.otf"]
    explicit = nerdpatch.sources_for([str(latin / "SumiMoji-Light.otf"),
                                      str(dist / "SumiMojiJP-Light.otf")])
    assert [(p.name, out.name) for p, out in explicit] == [
        ("SumiMoji-Light.otf", "latin"), ("SumiMojiJP-Light.otf", "nerd")]
    assert nerdpatch.sources_for(["nothing-like-this"]) == []


def test_powerline_range_is_the_two_powerline_blocks():
    assert 0xE0A0 in nerdpatch.POWERLINE and 0xE0D7 in nerdpatch.POWERLINE
    assert 0xE0D8 not in nerdpatch.POWERLINE and 0xE09F not in nerdpatch.POWERLINE
    assert build.CELL == 600
