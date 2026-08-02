#!/usr/bin/env python3
"""Assemble the variable Shoyu Code Pro JP 35 from live upstreams.

Same recipe as build.py, executed one axis up: instead of one static face
per weight, a single wght-variable font.

Why the 35 proportion is the one that goes variable first
---------------------------------------------------------
build.py reaches 35 by drawing Source Code Pro at 10/9 into a 667 cell and
then rescaling the whole half-width layer back down to 600. The round trip
is the identity, so it costs a rounding pass for nothing -- and rescale()
rewrites finished charstrings, which a variable font cannot do (a CFF2
charstring holds every weight at once; an affine transform would have to
carry the deltas too). Drawing Source Code Pro at its native 600 skips both
problems: no transform pass to make blend-aware, and the Latin outlines are
Source Code Pro's own integers rather than a 10/9 -> 9/10 round trip.

Why Source Han Sans's VARIABLE release is the base
--------------------------------------------------
Its static per-weight OTFs are not interpolation-compatible with each other
(Adobe removes overlaps per weight: 'あ' is 50/49/49/49/46/46/45 points
across the seven), so they cannot be merged into a variable font at all.
The variable release is one font whose CJK already varies, so the job is to
graft a Latin layer onto it rather than to build a CJK layer.

The graft carries its own masters. Source Han Sans VF declares a single
region -- two CJK masters, ExtraLight and Heavy, with the middle shaped by
avar -- but Source Code Pro's weight progression is its own, and pairing is
by measurement at each named weight. CFF2's vsindex operator exists exactly
for this: the appended glyphs point at a private VarData with a master per
named weight, while the CJK keeps the two it came with.

Env (all required):
  SHS_VF   = Variable/OTC/SourceHanSans-VF.otf.ttc   (the JP face is [0])
  SHS_DIR  = dir with SourceHanSansJP-<Weight>.otf   (defines the repertoire)
  SCP_VF_U = SourceCodeVF-Upright.otf
  MONA_VF  = Monaspace VF
  SHCJ_TTC = upstream/SourceHanCodeJP.ttc (default)
"""

import os
import sys
from pathlib import Path
from typing import NamedTuple

from fontTools import subset
from fontTools.misc.roundTools import otRound
from fontTools.otlLib import builder as otl
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib import builder as varbuilder
from fontTools.varLib.cff import CFF2CharStringMergePen
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import VariationModel, normalizeValue

from build import (CELL, LIGATURES, MONA_CELL, MONA_K, SCP_CELL, SCP_K,
                   VFSource, add_gsub, bar_thickness, copy_line_metrics,
                   _remap_scp_tag)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WGHT = 400      # the axis origin: Regular, not Adobe's ExtraLight


class Variant(NamedTuple):
    """Everything that differs between the families, derived from the cell.

    Each donor is drawn at the ratio between our cell and its own, so the
    outlines arrive at their native size wherever the two agree -- notably
    Source Code Pro at 1:1 in the 600 cell.

    `bar_scale` is the pairing rule: what the Source Han Code JP reference
    bar becomes in this family. The editor families keep Source Code Pro's
    NATIVE weight, so a smaller cell means a proportionally lighter bar; the
    terminal family compensates back to the CJK it stands beside.

    A donor is then matched at `draw / bar_scale`, which lands its own bar on
    `target / bar_scale * draw` = `target * bar_scale` once drawn.
    """
    suffix: str
    cell: int
    comp: bool          # weight-compensate to the CJK rather than stay native
    term: bool          # terminal grid: two-cell CJK, one-cell everything else

    @property
    def scp_draw(self):
        return self.cell / SCP_CELL

    @property
    def mona_draw(self):
        return self.cell / MONA_CELL

    @property
    def shcj_draw(self):
        return self.cell / CELL

    @property
    def bar_scale(self):
        return 1.0 if self.comp else self.cell / CELL

    @property
    def full(self):
        return 2 * self.cell if self.term else 1000


# Keyed by the name you type on the command line. The default family ships
# without a suffix, as it always has, but "23" is what it actually is and
# what everyone calls it.
VARIANTS = {
    "23": Variant("", CELL, False, False),          # 2:3, the SHCJ look
    "35": Variant("35", SCP_CELL, False, False),    # SCP native size + weight
    "Term": Variant("Term", SCP_CELL, True, True),  # 1:2 terminal grid
}

# (output weight, SHCJ reference face, name of the SHS VF named instance)
MASTERS = [
    ("ExtraLight", "Source Han Code JP EL", "ExtraLight"),
    ("Light", "Source Han Code JP L", "Light"),
    ("Normal", "Source Han Code JP N", "Normal"),
    ("Regular", "Source Han Code JP R", "Regular"),
    ("Medium", "Source Han Code JP M", "Medium"),
    ("Bold", "Source Han Code JP R Bold", "Bold"),
    ("Heavy", "Source Han Code JP H", "Heavy"),
]


# --------------------------------------------------------------------------
# base font: the JP face of Source Han Sans VF, subset to free glyph slots
# --------------------------------------------------------------------------

def prepare_base(shs_vf, repertoire, cache, default_wght):
    """Extract the JP face, subset it, and move its axis origin to Regular.

    Two things have to happen before a single glyph can be grafted on.

    The OTC faces carry all 65535 glyphs the collection shares, which is the
    OpenType maximum -- not one more glyph can be appended until the font is
    cut down to the language it is actually for.

    And Source Han Sans's wght axis defaults to its lightest master, so
    anything that loads the font without asking for a weight renders
    ExtraLight. Re-origining recomputes and re-rounds every delta, so it must
    happen HERE, while the font is still only Adobe's: run it afterwards and
    the same rounding walks over the grafted Latin, which otherwise carries
    Source Code Pro's own integers exactly.
    """
    if cache.exists():
        print(f"base: reusing {cache}")
        return TTFont(cache)
    print("base: extracting the JP face from the VF collection")
    jp = TTCollection(shs_vf).fonts[0]
    full = cache.with_suffix(".full.otf")
    jp.save(full)
    # Cover what the static build ships, not what the pan-CJK VF happens to
    # carry: its own cmap is 44853 codepoints and subsetting to that removes
    # almost nothing, leaving the font at the 65535 ceiling with no room to
    # graft into.
    unis = sorted(TTFont(repertoire).getBestCmap())
    print(f"base: subsetting {jp['maxp'].numGlyphs} glyphs to the "
          f"{len(unis)} codepoints the static build covers")
    subset.main([str(full),
                 "--unicodes=" + ",".join(f"{u:04X}" for u in unis),
                 "--layout-features=*", "--notdef-outline", "--name-IDs=*",
                 f"--output-file={cache}"])
    full.unlink()
    font = TTFont(cache)
    axis = font["fvar"].axes[0]
    print(f"base: re-origining {axis.axisTag} {axis.defaultValue:.0f} "
          f"-> {default_wght}")
    instantiateVariableFont(
        font, {axis.axisTag: (axis.minValue, default_wght, axis.maxValue)},
        inplace=True)
    font["OS/2"].usWeightClass = int(default_wght)
    font.save(cache)
    font = TTFont(cache)
    print(f"base: {font['maxp'].numGlyphs} glyphs, "
          f"{65535 - font['maxp'].numGlyphs} slots free")
    return font


def avar_map(font, tag, value):
    """Apply the font's avar warp to an already linearly normalized value."""
    seg = font["avar"].segments.get(tag) if "avar" in font else None
    if not seg:
        return value
    keys = sorted(seg)
    for lo, hi in zip(keys, keys[1:]):
        if lo <= value <= hi:
            if hi == lo:
                return seg[lo]
            return seg[lo] + (value - lo) / (hi - lo) * (seg[hi] - seg[lo])
    return value


def master_locations(font):
    """Where each named weight sits in the axis space the deltas live in."""
    axis = {a.axisTag: a for a in font["fvar"].axes}["wght"]
    named = {font["name"].getDebugName(i.subfamilyNameID): i.coordinates["wght"]
             for i in font["fvar"].instances}
    locs, user = [], []
    for _, _, instance_name in MASTERS:
        w = named[instance_name]
        n = avar_map(font, "wght",
                     normalizeValue(w, (axis.minValue, axis.defaultValue,
                                        axis.maxValue)))
        locs.append({} if abs(n) < 1e-9 else {"wght": round(n, 6)})
        user.append(w)
    return locs, user


# --------------------------------------------------------------------------
# CFF2 surgery
# --------------------------------------------------------------------------

class Cff2Target:
    """Append blend-bearing glyphs to a CFF2 variable font."""

    def __init__(self, font, model):
        self.font = font
        self.model = model
        self.cff = font["CFF2"].cff
        self.td = self.cff[self.cff.fontNames[0]]
        # reuse the FD (and so the hinting parameters) of an existing Latin
        # glyph; the appended layer is Latin
        self.fd_index = self.td.FDSelect[font.getGlyphID(
            font.getBestCmap()[ord("A")])]
        self.private = self.td.FDArray[self.fd_index].Private
        self.vsindex = self._add_regions()
        self._next = 1

    def _add_regions(self):
        """Give the appended layer its own VarData, so it can carry a master
        per named weight while the CJK keeps the two regions it shipped with.
        """
        store = self.td.VarStore.otVarStore
        region_list = store.VarRegionList
        before = region_list.RegionCount
        indices = []
        for region in varbuilder.buildVarRegionList(
                self.model.supports[1:], ["wght"]).Region:
            region_list.Region.append(region)
            indices.append(region_list.RegionCount)
            region_list.RegionCount += 1
        store.VarData.append(varbuilder.buildVarData(indices, None, False))
        store.VarDataCount += 1
        print(f"varstore: regions {before} -> {region_list.RegionCount}, "
              f"vsindex {store.VarDataCount - 1} for the grafted layer")
        return store.VarDataCount - 1

    def blended(self, name, draw_master):
        """One charstring holding every master. draw_master(i, pen) draws
        master i; identical outlines across masters simply yield no blend."""
        pen = CFF2CharStringMergePen([], name, len(self.model.locations), 0)
        for i in range(len(self.model.locations)):
            if i:
                pen.restart(i)
            draw_master(i, pen)
        cs = pen.getCharString(private=self.private,
                               globalSubrs=self.cff.GlobalSubrs,
                               var_model=self.model, optimize=True)
        if "blend" in cs.program and self.vsindex:
            cs.program[:0] = [self.vsindex, "vsindex"]
        return cs

    def append(self, cs, advance):
        """Add a glyph. CFF2 has no charset and no width in the charstring:
        the name is fontTools bookkeeping and hmtx alone carries the advance.
        """
        font, td = self.font, self.td
        name = f"shoyu{self._next:05d}"
        self._next += 1
        order = font.getGlyphOrder()
        order.append(name)
        if td.charset is not order:
            td.charset.append(name)
        td.FDSelect.gidArray.append(self.fd_index)
        index = len(td.CharStrings.charStringsIndex.items)
        td.CharStrings.charStringsIndex.append(cs)
        td.CharStrings.charStrings[name] = index
        font["hmtx"].metrics[name] = (advance, 0)
        if "vmtx" in font:
            font["vmtx"].metrics[name] = font["vmtx"].metrics[
                font.getBestCmap()[0x65E5]]
        font.setGlyphOrder(order)
        if hasattr(font, "_reverseGlyphOrderDict"):
            del font._reverseGlyphOrderDict
        font["maxp"].numGlyphs = len(order)
        return name

    def add(self, draw_master, advance):
        return self.append(self.blended("tmp", draw_master), advance)


def draw_from(font, glyph_name, scale, dx=0, dy=0):
    """A draw_master callable that copies one glyph through an affine."""
    glyph_set = font.getGlyphSet()

    def draw(_, pen):
        glyph_set[glyph_name].draw(
            TransformPen(pen, (scale, 0, 0, scale, dx, dy)))
    return draw


def outline_signature(font, glyph_name):
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    return tuple(op for op, _ in pen.value)


# --------------------------------------------------------------------------
# the three grafted layers
# --------------------------------------------------------------------------

def graft_halfwidth(target, scps, refs, ref0, V):
    """Re-point every half-width codepoint at a new variable glyph.

    Outline from Source Code Pro when it has the codepoint, otherwise from
    Source Han Code JP (half-width kana and a few symbols SCP never had).
    The SHCJ donors come from static faces, which only interpolate where
    their outlines happen to agree; where they do not, the Regular face
    stands in for every master.
    """
    ref_cm, ref_hm = ref0.getBestCmap(), ref0["hmtx"]
    scp_cm = scps[0].getBestCmap()
    new_map, default_map = {}, {}
    from_scp = from_shcj = frozen = 0

    for cp, g in sorted(ref_cm.items()):
        if ref_hm[g][0] != CELL:
            continue
        if cp in scp_cm:
            name = scp_cm[cp]
            draws = [draw_from(s, name, V.scp_draw) for s in scps]
            from_scp += 1
        else:
            sigs = {outline_signature(r, ref_cm[cp]) for r in refs
                    if cp in r.getBestCmap()}
            if len(sigs) == 1 and all(cp in r.getBestCmap() for r in refs):
                draws = [draw_from(r, r.getBestCmap()[cp], V.shcj_draw)
                         for r in refs]
            else:                       # incompatible across weights
                draws = [draw_from(ref0, g, V.shcj_draw)] * len(refs)
                frozen += 1
            from_shcj += 1

        def draw_master(i, pen, draws=draws):
            draws[i](i, pen)

        our = target.add(draw_master, V.cell)
        new_map[cp] = our
        if cp in scp_cm:
            default_map[scp_cm[cp]] = our

    # Legacy non-Unicode subtables still point at the old proportional Latin
    # and FontForge unifies subtables on load, silently dropping ASCII slots.
    font = target.font
    font["cmap"].tables = [t for t in font["cmap"].tables if t.isUnicode()]
    for table in font["cmap"].tables:
        for cp, name in new_map.items():
            if cp in table.cmap:
                table.cmap[cp] = name
    print(f"halfwidth: {from_scp} from Source Code Pro, {from_shcj} from SHCJ"
          + (f" ({frozen} could not interpolate, frozen at Regular)"
             if frozen else ""))
    return default_map


def import_scp_variants(target, scps, default_map, V):
    """Carry Source Code Pro's own character variants (slashed zero, one-story
    a, g shapes, salt...) across the graft, as variable glyphs."""
    gsub = scps[0]["GSUB"].table
    imported, tag_maps = {}, {}
    for record in gsub.FeatureList.FeatureRecord:
        tag = _remap_scp_tag(record.FeatureTag)
        if tag is None:
            continue
        for li in record.Feature.LookupListIndex:
            lookup = gsub.LookupList.Lookup[li]
            if lookup.LookupType != 1:
                continue
            for sub in lookup.SubTable:
                for src, dst in sub.mapping.items():
                    if src not in default_map:
                        continue
                    if dst not in imported:
                        draws = [draw_from(s, dst, V.scp_draw) for s in scps]

                        def draw_master(i, pen, draws=draws):
                            draws[i](i, pen)

                        imported[dst] = target.add(draw_master, V.cell)
                    tag_maps.setdefault(tag, {})[default_map[src]] = imported[dst]
    print(f"variants: {len(imported)} alternates over {len(tag_maps)} features")
    return tag_maps


def add_ligatures(target, monas, scps, V):
    """Append the Monaspace ligature glyphs, one master per named weight.

    The baseline correction is per master: Monaspace and Source Code Pro
    place the '=' bar at slightly different heights, and the offset that
    lines them up changes with weight.
    """
    mona_names = set(monas[0].getGlyphOrder())
    cmap = target.font.getBestCmap()

    def vcenter(font, name, scale):
        pen = BoundsPen(font.getGlyphSet())
        font.getGlyphSet()[name].draw(pen)
        return (pen.bounds[1] + pen.bounds[3]) / 2 * scale

    dys = [otRound(vcenter(s, s.getBestCmap()[ord("=")], V.scp_draw)
                   - vcenter(m, m.getBestCmap()[ord("=")], V.mona_draw))
           for s, m in zip(scps, monas)]

    added, alts = {}, {}
    for seq, spec in LIGATURES.items():
        if any(g not in mona_names for g in spec["glyphs"]):
            print(f"  skip {seq!r}: donor glyph missing")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        cells = spec["cells"]
        width = V.cell * cells
        step = MONA_CELL * V.mona_draw
        if len(spec["glyphs"]) == 1:
            offsets = [(cells - 1) * step]          # a spanning glyph sits last
        else:
            offsets = [i * step for i in range(len(spec["glyphs"]))]

        def draw_master(i, pen, spec=spec, offsets=offsets):
            glyph_set = monas[i].getGlyphSet()
            for name, dx in zip(spec["glyphs"], offsets):
                glyph_set[name].draw(TransformPen(
                    pen, (V.mona_draw, 0, 0, V.mona_draw, dx, dys[i])))

        added[seq] = target.add(draw_master, width)

        alt_src = spec["glyphs"][0] + ".alt"
        if len(spec["glyphs"]) == 1 and alt_src in mona_names:
            def draw_alt(i, pen, alt_src=alt_src, offsets=offsets):
                monas[i].getGlyphSet()[alt_src].draw(TransformPen(
                    pen, (V.mona_draw, 0, 0, V.mona_draw, offsets[0], dys[i])))
            alts[added[seq]] = target.add(draw_alt, width)

    print(f"ligatures: {len(added)} imported, {len(alts)} alternate designs")
    return added, alts


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------

def strip_advance_variation(font):
    """Drop HVAR/VVAR. Every advance in a monospace font is constant by
    definition, and the static build has no advance variation at all -- but
    Source Han Sans's Latin is proportional and varies ('A' 574, 'i' 245),
    so the inherited tables would otherwise apply deltas to appended gids."""
    for tag in ("HVAR", "VVAR"):
        if tag in font:
            del font[tag]


def set_names(font, user_wghts, V):
    family = ("Shoyu Code Pro JP " + V.suffix).strip()
    ps = "ShoyuCodeProJP" + V.suffix + "-VF"
    name = font["name"]
    name.names = []
    for nid, value in ((1, family), (2, "Regular"),
                       (3, f"{ps};shoyu-code-pro-jp"), (4, family),
                       (6, ps), (16, family), (17, "Regular")):
        name.setName(value, nid, 3, 1, 0x409)
    # one record per named instance, then re-point fvar at them
    for instance, (weight, _, _) in zip(font["fvar"].instances, MASTERS):
        nid = name.addName(weight, platforms=((3, 1, 0x409),))
        instance.subfamilyNameID = nid
        instance.postscriptNameID = 0xFFFF
    cff = font["CFF2"].cff
    cff.fontNames[0] = ps
    top = cff.topDictIndex[0]
    for attr, value in (("FamilyName", family), ("FullName", family)):
        if hasattr(top, attr):
            setattr(top, attr, value)
    otl.buildStatTable(font, [{
        "tag": "wght", "name": "Weight",
        "values": [{"value": w, "name": n,
                    **({"flags": 0x2} if n == "Regular" else {}),
                    **({"linkedValue": 700.0} if n == "Regular" else {})}
                   for w, (n, _, _) in zip(user_wghts, MASTERS)],
    }])
    return ps


# --------------------------------------------------------------------------

def check_masters(path, shcj, V):
    """Assert the pairing survived the blend, at every named instance.

    A variable font can be wrong in a way no single instance reveals -- feed
    the merge pen its masters in the wrong order and the deltas still
    interpolate smoothly, just around the wrong origin. Measuring the '=' bar
    at each named weight against the Source Han Code JP face it was paired
    with is the same check the static build gets for free.
    """
    import uharfbuzz as hb

    face = hb.Face(hb.Blob.from_file_path(str(path)))
    draw = hb.DrawFuncs()
    draw.set_move_to_func(lambda x, y, c: c.append((x, y)))
    draw.set_line_to_func(lambda x, y, c: c.append((x, y)))
    draw.set_cubic_to_func(lambda a, b, cc, dd, e, g, c: c.append((e, g)))
    draw.set_quadratic_to_func(lambda a, b, cc, dd, c: c.append((cc, dd)))
    draw.set_close_path_func(lambda c: c.append(None))

    built = TTFont(path)
    named = {built["name"].getDebugName(i.subfamilyNameID): i.coordinates["wght"]
             for i in built["fvar"].instances}
    worst, failed = 0.0, []
    for weight, ref_name, _ in MASTERS:
        font = hb.Font(face)
        font.set_variations({"wght": named[weight]})
        points = []
        font.draw_glyph(font.get_nominal_glyph(ord("=")), draw, points)
        first = points[:points.index(None)]
        got = max(y for _, y in first) - min(y for _, y in first)
        ref = shcj[ref_name]
        want = bar_thickness(ref, ref.getBestCmap()[ord("=")]) * V.bar_scale
        worst = max(worst, abs(got - want))
        if abs(got - want) > 1.5:
            failed.append(f"{weight}: bar {got:.0f}, expected {want:.0f}")
    if failed:
        sys.exit("master check FAILED\n  " + "\n  ".join(failed))
    print(f"master check: '=' bar within {worst:.1f} units of the SHCJ pairing "
          f"at all {len(MASTERS)} named weights")


def build_variant(V, env, shcj, base_path, out_dir):
    font = TTFont(base_path)
    locs, user_wghts = master_locations(font)
    model = VariationModel(locs, axisOrder=["wght"])

    # One matched donor instance per master, by the same measurement rule
    # build.py uses: Source Han Code JP's '=' bar decides the wght.
    scp_src = VFSource(env["SCP_VF_U"], V.scp_draw / V.bar_scale, {"wght": 0})
    mona_src = VFSource(env["MONA_VF"], V.mona_draw / V.bar_scale,
                        {"wght": 0, "wdth": 100, "slnt": 0}, extrapolate=True)
    refs, scps, monas, labels = [], [], [], []
    for weight, ref_name, _ in MASTERS:
        ref = shcj[ref_name]
        target_bar = bar_thickness(ref, ref.getBestCmap()[ord("=")])
        refs.append(ref)
        scps.append(scp_src.matched(target_bar))
        monas.append(mona_src.matched(target_bar))
        labels.append(weight)

    # The merge pen reads its masters positionally, with the default first --
    # varLib reorders them into the model's own order before handing them
    # over, and getDeltas is an identity permutation afterwards. Skipping this
    # silently stores the wrong master as the charstring's default value.
    regular_ref = refs[[w for w, _, _ in MASTERS].index("Regular")]
    order = list(model.reverseMapping)
    scps = model.reorderMasters(scps, order)
    monas = [monas[i] for i in order]
    refs = [refs[i] for i in order]

    target = Cff2Target(font, model)
    default_map = graft_halfwidth(target, scps, refs, regular_ref, V)
    variant_maps = import_scp_variants(target, scps, default_map, V)
    added, alts = add_ligatures(target, monas, scps, V)
    add_gsub(font, added, alts, variant_maps)
    copy_line_metrics(font, regular_ref)
    strip_advance_variation(font)
    ps = set_names(font, user_wghts, V)

    out = out_dir / f"{ps}.otf"
    font.save(out)
    print(f"-> {out.name}  ({font['maxp'].numGlyphs} glyphs, "
          f"cell {V.cell}:{V.full})")
    check_masters(out, shcj, V)
    return out


def main():
    want = sys.argv[1:] or list(VARIANTS)
    unknown = [v for v in want if v not in VARIANTS]
    if unknown:
        sys.exit(f"unknown variant(s) {unknown}; choose from {list(VARIANTS)!r}")
    env = {k: os.environ.get(k) for k in
           ("SHS_VF", "SHS_DIR", "SCP_VF_U", "MONA_VF")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    shcj_ttc = os.environ.get("SHCJ_TTC", ROOT / "upstream" / "SourceHanCodeJP.ttc")

    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    base_path = out_dir / "shs-vf-jp.base.otf"
    prepare_base(env["SHS_VF"],
                 Path(env["SHS_DIR"]) / "SourceHanSansJP-Regular.otf",
                 base_path, DEFAULT_WGHT)
    shcj = {f["name"].getDebugName(4): f for f in TTCollection(shcj_ttc).fonts}

    for suffix in want:
        V = VARIANTS[suffix]
        print(f"\n=== Shoyu Code Pro JP {V.suffix} ({suffix}) ===")
        build_variant(V, env, shcj, base_path, out_dir)


if __name__ == "__main__":
    main()
