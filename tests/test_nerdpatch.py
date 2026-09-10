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
from fontTools.ttLib import TTFont, newTable

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
    cell, Source Code Pro's own Powerline separator at U+E0B0 (taller
    than the line box, as Source Code Pro draws it), Source Code Pro's
    line box, a BMP-only cmap."""
    charstrings = {}
    pen = T2CharStringPen(600, None)
    charstrings[".notdef"] = pen.getCharString()
    pen = T2CharStringPen(600, None)
    _rect(pen, 50, 0, 550, 655)
    charstrings["A"] = pen.getCharString()
    pen = T2CharStringPen(600, None)
    _rect(pen, 0, -280, 600, 1040)
    charstrings["uniE0B0"] = pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A", "uniE0B0"])
    fb.setupCharacterMap({ord("A"): "A", 0xE0B0: "uniE0B0"})
    fb.setupCFF(ps, {"FullName": ps}, charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 50), "uniE0B0": (600, 0)})
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
    narrow Powerline symbol (a git branch) at U+E0A0, a
    supplementary-plane icon at U+F0001, and 'A', which a face already
    has."""
    fb = FontBuilder(2048, isTTF=True)
    glyphs, cmap, metrics = {}, {}, {".notdef": (2048, 0)}
    boxes = {"icon": (0, 0, 2048, 2048), "pl": (0, -410, 2048, 1638),
             "branch": (608, -410, 1440, 1638),
             "far": (512, 0, 1536, 1024), "A": (0, 0, 1000, 1000)}
    for name, box in boxes.items():
        pen = TTGlyphPen(None)
        _rect(pen, *box)
        glyphs[name] = pen.glyph()
        metrics[name] = (2048, box[0])
    pen = TTGlyphPen(None)
    glyphs[".notdef"] = pen.glyph()
    cmap = {0xE000: "icon", 0xE0B0: "pl", 0xE0A0: "branch",
            0xF0001: "far", ord("A"): "A"}
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


def _place(xform, ink):
    """The box `ink` lands in once `xform` is applied."""
    a, _b, _c, d, e, f = xform
    x0, y0, x1, y1 = ink
    return a * x0 + e, d * y0 + f, a * x1 + e, d * y1 + f


def test_icon_transform_scales_an_icon_by_the_cell_over_the_em():
    ctx = nerdpatch.icon_context(_face(), _symbols())
    k = 600 / 2048
    xform = nerdpatch.icon_transform(0xE000, None, ctx)
    assert xform[0] == xform[3] == pytest.approx(k)
    # the symbols' line box centre (614) lands on ours (355.5)
    assert k * 614 + xform[5] == pytest.approx(355.5)


def test_icon_transform_keeps_an_icon_that_lands_outside_the_cell_inside_it():
    """Nerd Fonts draws a few icons past its own cell, and the test is
    where the ink LANDS, not how wide it is: the ends of the progress bar
    are narrower than the cell and still sit 30u beyond its edge."""
    ctx = nerdpatch.icon_context(_face(), _symbols())
    k = 600 / 2048
    fits = (0, 0, 2048, 2048)
    assert _place(nerdpatch.icon_transform(0xE100, fits, ctx), fits)[2] \
        == pytest.approx(2048 * k)                    # the flat scale
    small = (512, 0, 1536, 1024)
    box = _place(nerdpatch.icon_transform(0xE100, small, ctx), small)
    assert box[2] - box[0] == pytest.approx(1024 * k)  # small stays small
    assert box[0] == pytest.approx(512 * k)            # and stays put
    over = (-102, -410, 2150, 1638)                    # 2252 wide
    box = _place(nerdpatch.icon_transform(0xE100, over, ctx), over)
    assert box[2] - box[0] == pytest.approx(600)       # fitted to the cell
    assert box[0] + box[2] == pytest.approx(600)       # and centred in it
    # 1955 wide — inside the cell — but drawn 102u past its right edge
    beyond = (195, -410, 2150, 1638)
    box = _place(nerdpatch.icon_transform(0xE100, beyond, ctx), beyond)
    assert box[2] <= 600 + 0.5 and box[0] >= -0.5


def test_icon_transform_keeps_both_bleeds_on_a_progress_middle():
    """font-patcher's align 'c' with an overlap: the middle of a progress
    bar has a neighbour on each side, so both bleeds have to survive the
    fit or a seam shows at every join."""
    ctx = nerdpatch.icon_context(_face(), _symbols())
    mid = (-101, -410, 2151, 1638)                # U+EE01's own box
    box = _place(nerdpatch.icon_transform(0xEE01, mid, ctx), mid)
    assert box[0] == pytest.approx(-101 / 2048 * 600, abs=0.5)
    assert box[2] == pytest.approx(600 + 103 / 2048 * 600, abs=0.5)
    assert (box[1], box[3]) == pytest.approx((-273, 984))    # the whole line
    # and an end keeps its one bleed, as a Powerline separator does
    end = (195, -410, 2150, 1638)                 # U+EE00's, bleeding right
    box = _place(nerdpatch.icon_transform(0xEE00, end, ctx), end)
    assert box[0] == pytest.approx(0, abs=0.5)
    assert box[2] == pytest.approx(600 + 102 / 2048 * 600, abs=0.5)


def test_icon_transform_stretches_a_separator_to_the_cell_and_the_line():
    ctx = nerdpatch.icon_context(_face(), _symbols())
    # a separator that fills its own cell and line box fills ours
    box = _place(nerdpatch.icon_transform(0xE0B0, (0, -410, 2048, 1638), ctx),
                 (0, -410, 2048, 1638))
    assert box == pytest.approx((0, -273, 600, 984))
    # the real one: 1447u of the symbols' 2048 cell (font-patcher's
    # xy-ratio capped it there in a square cell) bleeding 6% past the
    # left edge. The bleed rides along in proportion and the other edge
    # reaches ours, so two cells tile
    bled = (-122, -420, 1325, 1648)
    assert _place(nerdpatch.icon_transform(0xE0B0, bled, ctx), bled) == \
        pytest.approx((-35.7, -279, 600, 990), abs=0.6)


def test_icon_transform_aligns_on_the_edge_that_bleeds():
    """font-patcher's overlap is a bleed past the symbols' own cell, and
    the fit has to keep it — even when the other edge sits exactly on
    its cell edge and is therefore 'nearer'."""
    ctx = nerdpatch.icon_context(_face(), _symbols())
    ink = (0, -420, 2170, 1648)              # flush left, bleeding right
    box = _place(nerdpatch.icon_transform(0xE0B2, ink, ctx), ink)
    assert box[0] == pytest.approx(0)
    assert box[2] == pytest.approx(600 + 122 / 2048 * 600, abs=0.5)


def test_icon_transform_keeps_the_aspect_of_a_powerline_symbol():
    """U+E0A0-E0A3 are symbols, not separators: they fill the line box
    with their aspect kept, never stretched to the cell."""
    ctx = nerdpatch.icon_context(_face(), _symbols())
    ink = (608, -410, 1440, 1638)
    box = _place(nerdpatch.icon_transform(0xE0A0, ink, ctx), ink)
    assert box[3] - box[1] == pytest.approx(1257)            # the whole line
    assert (box[2] - box[0]) / (box[3] - box[1]) == pytest.approx(832 / 2048)
    assert box[0] + box[2] == pytest.approx(600)             # centred in the cell


def test_graft_symbols_appends_one_cell_icons_the_face_lacks(monkeypatch):
    # the fixtures share 'A', where a real face and the symbols font
    # share U+2665: pin that instead of editing the fixtures
    monkeypatch.setattr(nerdpatch, "TEXT_OVER_ICON", frozenset({ord("A")}))
    face = _face()
    assert _bounds(face, "uniE0B0") == (0, -280, 600, 1040)     # Source Code Pro's
    a_before = _bounds(face, "A")
    grafted, rehint = nerdpatch.graft_symbols(face, _symbols())
    assert _bounds(face, "A") == a_before        # text, not Nerd Fonts' icon
    assert (grafted, rehint) == (4, ["uniE0B0"])                # not 'A'
    cmap = face.getBestCmap()
    assert cmap[ord("A")] == "A"
    icon, pl, far = cmap[0xE000], cmap[0xE0B0], cmap[0xF0001]
    assert pl == "uniE0B0"                                      # redrawn in place
    assert {face["hmtx"][g][0] for g in (icon, pl, far)} == {600}
    x0, y0, x1, y1 = _bounds(face, icon)
    assert (x0, x1) == (0, 600)
    assert y0 == pytest.approx(176, abs=1) and y1 == pytest.approx(776, abs=1)
    assert _bounds(face, pl) == (0, -273, 600, 984)             # stretched to the line
    assert face["hmtx"][pl] == (600, 0)
    x0, y0, x1, y1 = _bounds(face, far)
    assert x1 - x0 == pytest.approx(300, abs=1)                # half the em, half the cell
    # the supplementary-plane icon needed a format 12 subtable
    assert any(t.format == 12 and 0xF0001 in t.cmap for t in face["cmap"].tables)
    assert face["maxp"].numGlyphs == 6


def test_graft_symbols_keeps_every_glyph_on_one_vertical_origin(monkeypatch):
    """A top side bearing is measured DOWN from the glyph's own yMax. The
    separator drawn over Source Code Pro's own is a different height, and
    an appended icon has no bearing at all, so both have to be derived
    from the origin the rest of the face uses — a vertical run laid out
    from vmtx rather than VORG reads exactly this."""
    monkeypatch.setattr(nerdpatch, "TEXT_OVER_ICON", frozenset({ord("A")}))
    face, symbols = _face(), _symbols()
    tops = {g: (_bounds(face, g) or (0, 0, 0, 0))[3] for g in face.getGlyphOrder()}
    face["vmtx"] = newTable("vmtx")                # every glyph at 880
    face["vmtx"].metrics = {g: (1000, 880 - top) for g, top in tops.items()}
    assert face["vmtx"].metrics["uniE0B0"] == (1000, 880 - 1040)

    nerdpatch.graft_symbols(face, symbols)

    def origin(name):
        box = _bounds(face, name)
        return (box[3] if box else 0) + face["vmtx"].metrics[name][1]

    assert origin("uniE0B0") == 880                # redrawn in place
    cmap = face.getBestCmap()
    assert origin(cmap[0xE000]) == 880             # appended icon
    assert origin(cmap[0xF0001]) == 880
    assert origin("A") == 880                      # untouched


def test_rename_splices_the_marker_and_credits_nerd_fonts():
    face = _face()
    assert nerdpatch.rename(face) == "SumiMojiJPNFM-Regular"
    name = face["name"]
    assert "Nerd Fonts" in name.getDebugName(0)                 # the icons' donor
    assert "LICENSE-NerdFonts" in name.getDebugName(0)
    nerdpatch.rename(face)                                      # idempotent
    assert name.getDebugName(0).count("Nerd Fonts:") == 1
    assert name.getDebugName(1) == "Sumi Moji JP Nerd Font Mono"
    assert name.getDebugName(3) == "5.0.0;SUMI;SumiMojiJPNFM-Regular"
    assert name.getDebugName(6) == "SumiMojiJPNFM-Regular"
    cff = face["CFF "].cff
    assert cff.fontNames[0] == "SumiMojiJPNFM-Regular"
    assert cff["SumiMojiJPNFM-Regular"].FullName == "Sumi Moji JP Nerd Font Mono"


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


def test_separators_are_font_patchers_own_stretched_set():
    """SEPARATORS is transcribed from font-patcher v3.4.0's
    SYM_ATTR_POWERLINE — every entry whose 'stretch' is '^xy' or '^xy2'.
    Pinned here so a change to it is a deliberate one: icon_checks can
    only tell whether a glyph got the treatment its group asks for, not
    whether the group is right."""
    assert (
        set(range(0xE0B0, 0xE0C9)) | {0xE0CA, 0xE0CC, 0xE0CD,
                                      0xE0D2, 0xE0D4, 0xE0D6, 0xE0D7}) == nerdpatch.SEPARATORS
    assert len(nerdpatch.SEPARATORS) == 32
    # the four Powerline symbols keep their aspect ('^pa'), as do E0CE-E0D1
    assert not nerdpatch.SEPARATORS & {0xE0A0, 0xE0A1, 0xE0A2, 0xE0A3,
                                       0xE0CE, 0xE0CF, 0xE0D0, 0xE0D1}


def test_graft_symbols_will_not_let_an_icon_take_a_character_unpinned():
    """TEXT_OVER_ICON is the whole of the overlap outside Powerline, and
    a wider one is a decision for a maintainer: font-patcher's default
    would redraw the character as an icon, and that has to be chosen,
    not inherited from an upstream release."""
    with pytest.raises(ValueError, match=r"outside Powerline at \['0x41'\]"):
        nerdpatch.graft_symbols(_face(), _symbols())


def _checks(font, symbols=None):
    return dict((msg.split(" (")[0], ok) for ok, msg in nerdpatch.icon_checks(font, symbols))


def _grafted(monkeypatch):
    monkeypatch.setattr(nerdpatch, "TEXT_OVER_ICON", frozenset({ord("A")}))
    face, symbols = _face(), _symbols()
    nerdpatch.graft_symbols(face, symbols)
    return face, symbols


def test_icon_checks_passes_a_good_graft(monkeypatch):
    face, symbols = _grafted(monkeypatch)
    assert all(ok for ok, _ in nerdpatch.icon_checks(face, symbols))
    assert all(ok for ok, _ in nerdpatch.icon_checks(face))     # no NF_SYMBOLS


def test_icon_checks_faults_a_powerline_glyph_with_no_ink(monkeypatch):
    """A blank separator draws nothing, so it has no box to be short or
    to spill — every geometry check below would pass it."""
    face, symbols = _grafted(monkeypatch)
    cff = face["CFF "].cff
    cs = cff[cff.fontNames[0]].CharStrings["uniE0B0"]
    cs.decompile()
    cs.program = ["endchar"]                     # keeps its Private, draws nothing
    ink, tiles = [(ok, msg) for ok, msg in nerdpatch.icon_checks(face, symbols)
                  if "draws ink" in msg or "tiles the cell" in msg]
    assert (ink[0], "U+E0B0" in ink[1]) == (False, True)
    assert tiles[0] is True                      # no box to be short: hence the check


def test_icon_checks_faults_a_two_cell_or_blank_icon(monkeypatch):
    """Ten thousand icons that nothing measured: blanking every one of
    them, or re-encoding them all two cells wide, passed the whole
    suite."""
    face, symbols = _grafted(monkeypatch)
    icon = face.getBestCmap()[0xE000]
    face["hmtx"].metrics[icon] = (1200, face["hmtx"].metrics[icon][1])
    got = _checks(face, symbols)
    assert got["every icon is one cell wide — a Nerd Font MONO"] is False
    assert got["every icon the symbols font draws draws in the face"] is True

    face, symbols = _grafted(monkeypatch)
    cff = face["CFF "].cff
    cs = cff[cff.fontNames[0]].CharStrings[face.getBestCmap()[0xE000]]
    cs.decompile()
    cs.program = ["endchar"]
    got = _checks(face, symbols)
    assert got["every icon the symbols font draws draws in the face"] is False
    assert got["every icon fits the cell and the line"] is True   # no box to fault


def test_icon_checks_faults_an_icon_that_never_reached_the_face(monkeypatch):
    """Not just the Powerline ones: a graft that dropped a whole icon
    set would have nothing left to measure and would otherwise pass."""
    face, symbols = _grafted(monkeypatch)
    for table in face["cmap"].tables:
        table.cmap.pop(0xF0001, None)
    assert _checks(face, symbols)["every codepoint the symbols font has is in the face"] is False
    # and with no symbols font at hand there is nothing to compare against
    assert _checks(face)["every codepoint the symbols font has is in the face"] is True
