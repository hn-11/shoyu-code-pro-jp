"""Unit tests for scripts/build_latin_vf.py that need no font files: the
wght axis plumbing (SCP's avar-bent axis made linear, our usWeightClass
user axis composed onto it, master placement) and the STAT/GDEF touches.
"""

import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.models import piecewiseLinearMap

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin_vf as vf  # noqa: E402
from conftest import make_font  # noqa: E402

# Source Code Pro's own upright VF, as shipped: wght 200-900 with the
# default at 200 and an avar that bends user 300 to only ~10% of the way
# up the normalized axis (its 400 master sits at 0.368).
SCP_AVAR = {-1.0: -1.0, 0.0: 0.0, 0.142883: 0.099976, 0.285706: 0.367981,
            0.428589: 0.486023, 0.571411: 0.599976, 0.714294: 0.823974, 1.0: 1.0}
POS = {"Light": 317.0, "Normal": 374.0, "Regular": 406.0,
       "Medium": 546.0, "Bold": 669.0, "Heavy": 857.0}


def _vf_meta(avar=SCP_AVAR, lo=200, default=200, hi=900):
    """A TTFont carrying just fvar (+ avar): what scp_design_axis reads."""
    font = make_font([".notdef"], {}, {".notdef": 500}, family="T", style="R")
    FontBuilder(font=font).setupFvar([("wght", lo, default, hi, "Weight")], [])
    if avar:
        table = newTable("avar")
        table.segments = {"wght": dict(avar)}
        font["avar"] = table
    return font


# --- scp_design_axis --------------------------------------------------------

def test_scp_design_axis_is_identity_without_avar():
    design, breaks = vf.scp_design_axis(_vf_meta(avar=None, default=400))
    for u in (200, 300, 400, 650, 900):
        assert design(u) == pytest.approx(u)
    assert breaks == [200.0, 400.0, 900.0]


def test_scp_design_axis_follows_avar_and_lists_its_breaks():
    design, breaks = vf.scp_design_axis(_vf_meta())
    assert design(200) == pytest.approx(200)
    assert design(900) == pytest.approx(900)
    # user 400 = SCP's middle master: post-avar 0.368 of the 200..900 span
    assert design(400) == pytest.approx(200 + 700 * 0.367981, abs=0.05)
    # user 300 lands only ~10% up: far below the linear 300
    assert design(300) == pytest.approx(200 + 700 * 0.099976, abs=0.05)
    assert breaks == pytest.approx([200, 300, 400, 500, 600, 700, 900], abs=0.05)


def test_scp_design_axis_is_monotonic():
    design, _ = vf.scp_design_axis(_vf_meta())
    vals = [design(u) for u in range(200, 901, 7)]
    assert all(a < b for a, b in zip(vals, vals[1:]))


# --- user_axis --------------------------------------------------------------

def test_user_axis_range_and_default_are_usweightclass():
    design, breaks = vf.scp_design_axis(_vf_meta())
    lo, default, hi, mapping, _ = vf.user_axis(POS, design, breaks, 200)
    assert (lo, default, hi) == (200, 400, 900)
    assert default == build.WEIGHT_CLASS["Regular"]
    assert hi == build.WEIGHT_CLASS["Heavy"]


def test_user_axis_map_hits_every_named_weight_exactly():
    design, breaks = vf.scp_design_axis(_vf_meta())
    _, _, _, mapping, to_scp = vf.user_axis(POS, design, breaks, 200)
    m = dict(mapping)
    for weight, scp_wght in POS.items():
        u = build.WEIGHT_CLASS[weight]
        assert to_scp(u) == scp_wght
        assert u in m
        assert m[u] == pytest.approx(design(scp_wght))


def test_user_axis_map_reproduces_scp_between_the_named_weights():
    """The composed map must equal design(to_scp(U)) at EVERY U, i.e. it
    must carry SCP's own avar breakpoints — a map through only the six
    named weights would cut those corners."""
    design, breaks = vf.scp_design_axis(_vf_meta())
    _, _, _, mapping, to_scp = vf.user_axis(POS, design, breaks, 200)
    m = dict(mapping)
    for u in range(200, 901):
        assert piecewiseLinearMap(u, m) == pytest.approx(design(to_scp(u)), abs=1e-6)


def test_user_axis_map_is_monotonic_and_ends_at_heavy():
    design, breaks = vf.scp_design_axis(_vf_meta())
    _, _, _, mapping, _ = vf.user_axis(POS, design, breaks, 200)
    us = [u for u, _ in mapping]
    ds = [d for _, d in mapping]
    assert us == sorted(us) and ds == sorted(ds)
    assert mapping[0] == (200, pytest.approx(200))
    assert mapping[-1][0] == 900 and mapping[-1][1] == pytest.approx(design(857))


def test_user_axis_rejects_non_monotonic_pairing():
    design, breaks = vf.scp_design_axis(_vf_meta())
    bad = dict(POS, Medium=680.0)   # Medium heavier than Bold
    with pytest.raises(RuntimeError, match="monotonic"):
        vf.user_axis(bad, design, breaks, 200)


# --- master_scp_wghts -------------------------------------------------------

def test_masters_are_scp_masters_in_range_plus_regular_and_heavy():
    design, breaks = vf.scp_design_axis(_vf_meta())
    _, default, hi, _, to_scp = vf.user_axis(POS, design, breaks, 200)
    assert vf.master_scp_wghts([200, 400, 900], to_scp, 200, default, hi) == \
        [200.0, 400.0, 406.0, 857.0]


def test_masters_drop_scp_masters_above_heavy_and_dedupe():
    design, breaks = vf.scp_design_axis(_vf_meta())
    pos = dict(POS, Regular=400.0, Heavy=900.0)
    _, default, hi, _, to_scp = vf.user_axis(pos, design, breaks, 200)
    assert vf.master_scp_wghts([200, 400, 900], to_scp, 200, default, hi) == \
        [200.0, 400.0, 900.0]


def test_masters_take_extra_positions_inside_the_range_only():
    design, breaks = vf.scp_design_axis(_vf_meta())
    _, default, hi, _, to_scp = vf.user_axis(POS, design, breaks, 200)
    got = vf.master_scp_wghts([200, 400, 900], to_scp, 200, default, hi,
                              extra=[366.123, 150, 880, 400.2])
    # 366.12 kept (rounded), 150/880 outside, 400.2 within 0.5 of 400 dropped
    assert got == [200.0, 366.12, 400.0, 406.0, 857.0]


# --- name_default_instance_by_font ---------------------------------------

def _vf_with_instances(default=400):
    font = _vf_meta(avar=None, default=default)
    name = font["name"]
    name.setName("SumiMoji-Roman", 6, 3, 1, 0x409)
    name.setName("Regular", 2, 3, 1, 0x409)
    ids = {}
    for i, (style, wght) in enumerate((("Light", 300), ("Regular", 400), ("Bold", 700))):
        sid, pid = 256 + 2 * i, 257 + 2 * i
        name.setName(style, sid, 3, 1, 0x409)
        name.setName(f"SumiMoji-{style}", pid, 3, 1, 0x409)
        ids[style] = (sid, pid, wght)
    from fontTools.ttLib.tables._f_v_a_r import NamedInstance
    for style, (sid, pid, wght) in ids.items():
        inst = NamedInstance()
        inst.subfamilyNameID, inst.postscriptNameID = sid, pid
        inst.coordinates = {"wght": wght}
        font["fvar"].instances.append(inst)
    return font, ids


def test_default_instance_takes_name_id_6_and_drops_its_private_record():
    font, ids = _vf_with_instances()
    vf.name_default_instance_by_font(font)
    insts = {i.coordinates["wght"]: i for i in font["fvar"].instances}
    assert insts[400].postscriptNameID == 6
    assert font["name"].getDebugName(ids["Regular"][1]) is None
    # the others keep their own names
    assert insts[300].postscriptNameID == ids["Light"][1]
    assert font["name"].getDebugName(ids["Bold"][1]) == "SumiMoji-Bold"


def test_default_instance_missing_raises():
    font, _ = _vf_with_instances(default=350)
    with pytest.raises(RuntimeError, match="axis default"):
        vf.name_default_instance_by_font(font)


# --- build.add_stat (family form, as the VF uses it) -------------------------------------------------------------

def _stat_values(font):
    stat = font["STAT"].table
    name = font["name"]
    out = {}
    for av in stat.AxisValueArray.AxisValue:
        tag = stat.DesignAxisRecord.Axis[av.AxisIndex].AxisTag
        out.setdefault(tag, []).append((name.getDebugName(av.ValueNameID), av.Value,
                                        av.Flags, getattr(av, "LinkedValue", None)))
    return out


def test_add_stat_family_form_uses_usweightclass_values():
    font = _vf_meta()
    build.add_stat(font, [w for w, _, _ in build.FACES], italic=False)
    vals = _stat_values(font)
    assert [(n, v) for n, v, _, _ in vals["wght"]] == \
        [(w, build.WEIGHT_CLASS[w]) for w, _, _ in build.FACES]
    regular = next(x for x in vals["wght"] if x[0] == "Regular")
    assert regular[2] & 0x2 and regular[3] == build.WEIGHT_CLASS["Bold"]
    assert vals["ital"] == [("Regular", 0, 0x2, 1)]


def test_add_stat_family_form_italic_file_declares_ital_1():
    font = _vf_meta()
    build.add_stat(font, [w for w, _, _ in build.FACES], italic=True)
    assert _stat_values(font)["ital"] == [("Italic", 1, 0, None)]


# --- build.classify_unicode_marks -------------------------------------------

def _font_with_gdef(cmap, classes):
    order = [".notdef", *sorted(set(cmap.values()))]
    font = make_font(order, cmap, dict.fromkeys(order, 600), family="T", style="R")
    gdef = newTable("GDEF")
    gdef.table = otTables.GDEF()
    gdef.table.Version = 0x00010000
    gdef.table.GlyphClassDef = otTables.GlyphClassDef()
    gdef.table.GlyphClassDef.classDefs = dict(classes)
    gdef.table.AttachList = gdef.table.LigCaretList = gdef.table.MarkAttachClassDef = None
    font["GDEF"] = gdef
    return font


def test_classify_unicode_marks_marks_only_unclassified_mn():
    font = _font_with_gdef({0x41: "A", 0x300: "grave", 0x35F: "dblmacronbelow",
                            0x361: "dblinvbreve", 0x20DD: "enclcircle"},
                           {"A": 1, "grave": 3})
    fixed = build.classify_unicode_marks(font)
    assert sorted(fixed) == ["dblinvbreve", "dblmacronbelow"]
    defs = font["GDEF"].table.GlyphClassDef.classDefs
    assert defs["A"] == 1 and defs["grave"] == 3
    assert defs["dblmacronbelow"] == 3 and defs["dblinvbreve"] == 3
    assert "enclcircle" not in defs   # Me (enclosing) is left alone


def test_classify_unicode_marks_noop_without_gdef():
    font = _font_with_gdef({0x300: "grave"}, {})
    del font["GDEF"]
    assert build.classify_unicode_marks(font) == []
