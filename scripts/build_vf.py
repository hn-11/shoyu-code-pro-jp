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
  SCP_VF_U = SourceCodeVF-Upright.otf   SCP_VF_I = SourceCodeVF-Italic.otf
  MONA_VF  = Monaspace VF
  SHCJ_TTC = upstream/SourceHanCodeJP.ttc (default)
  SHMONO_TTC = upstream/SourceHanMono.ttc (default) -- half-width donor
"""

import os
import sys
from pathlib import Path
from typing import NamedTuple

from fontTools import subset
from fontTools.cffLib import specializer
from fontTools.misc.roundTools import otRound
from fontTools.otlLib import builder as otl
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib import builder as varbuilder
from fontTools.varLib.cff import CFF2CharStringMergePen
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.misc.psCharStrings import T2CharString
from fontTools.varLib.models import (VariationModel, normalizeValue,
                                     supportScalar)

from build import (BLOCK_ELEMENTS, BOX_DRAWING, CELL, LIGATURES,
                   MONA_CELL, SCP_CELL, SCP_EM_BOX, VFSource, add_gsub,
                   bar_thickness, copy_line_metrics, line_box_fit,
                   narrow_transform, one_cell_codepoints,
                   _remap_scp_tag)

ROOT = Path(__file__).resolve().parent.parent
# Intermediates go in build/, never in dist/: dist/ is what gets zipped and
# released, and a glob there will happily pick up a half-finished base font.
WORK = ROOT / "build"
DEFAULT_WGHT = 400      # the axis origin: Regular, not Adobe's ExtraLight
# Source Han Code JP declares italicAngle 0 on its italic faces, so the value
# cannot be read off the reference the way the static build tries to. These
# are the angle we declare and the slant we ask Monaspace for, so the
# ligatures lean with the letters instead of standing upright among them.
ITALIC_ANGLE = -12.0
SLANT = -11.0           # Monaspace's slnt axis bottoms out here


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

# (output weight, SHCJ pairing reference, SHS VF named instance, SH Mono face)
MASTERS = [
    ("ExtraLight", "Source Han Code JP EL", "ExtraLight", "Source Han Mono EL"),
    ("Light", "Source Han Code JP L", "Light", "Source Han Mono L"),
    ("Normal", "Source Han Code JP N", "Normal", "Source Han Mono N"),
    ("Regular", "Source Han Code JP R", "Regular", "Source Han Mono"),
    ("Medium", "Source Han Code JP M", "Medium", "Source Han Mono M"),
    ("Bold", "Source Han Code JP R Bold", "Bold", "Source Han Mono Bold"),
    ("Heavy", "Source Han Code JP H", "Heavy", "Source Han Mono H"),
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
    for _, _, instance_name, _ in MASTERS:
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
        self._vsindexes = {}
        self.vsindex = self.vsindex_for(model)
        self._next = 1

    def vsindex_for(self, model):
        """A private VarData for this set of masters.

        The appended layer carries a master per named weight while the CJK
        keeps the two regions it shipped with, which is what CFF2's vsindex
        operator is for. A donor whose static faces do not all interpolate
        gets a second one over the subset that does, so the glyph still
        follows the axis as far as its outlines allow.
        """
        supports = model.supports[1:]
        if not supports:
            return 0                      # single master: nothing to blend
        key = tuple(tuple(sorted(s.items())) for s in supports)
        if key in self._vsindexes:
            return self._vsindexes[key]
        store = self.td.VarStore.otVarStore
        region_list = store.VarRegionList
        indices = []
        for region in varbuilder.buildVarRegionList(supports, ["wght"]).Region:
            region_list.Region.append(region)
            indices.append(region_list.RegionCount)
            region_list.RegionCount += 1
        store.VarData.append(varbuilder.buildVarData(indices, None, False))
        store.VarDataCount += 1
        self._vsindexes[key] = store.VarDataCount - 1
        return self._vsindexes[key]

    def blended(self, name, draw_master, model=None):
        """One charstring holding every master. draw_master(i, pen) draws
        master i; identical outlines across masters simply yield no blend."""
        model = model or self.model
        vsindex = self.vsindex_for(model)
        pen = CFF2CharStringMergePen([], name, len(model.locations), 0)
        for i in range(len(model.locations)):
            if i:
                pen.restart(i)
            draw_master(i, pen)
        cs = pen.getCharString(private=self.private,
                               globalSubrs=self.cff.GlobalSubrs,
                               var_model=model, optimize=True)
        if "blend" in cs.program and vsindex:
            cs.program[:0] = [vsindex, "vsindex"]
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

    def add(self, draw_master, advance, model=None):
        return self.append(self.blended("tmp", draw_master, model), advance)


def draw_from(font, glyph_name, scale, dx=0, dy=0):
    """A draw_master callable that copies one glyph through an affine."""
    glyph_set = font.getGlyphSet()

    def draw(_, pen):
        glyph_set[glyph_name].draw(
            TransformPen(pen, (scale, 0, 0, scale, dx, dy)))
    return draw


def sub_model_for(locations, mask, cache):
    """A model over the masters that agree, with its master order settled.

    The merge pen reads masters positionally with the default first, which
    means the model has to be normalised and the items permuted to match --
    and VariationModel.getSubModel() cannot be used for it: it caches, so
    normalising what it returns leaves the next caller with a permuted model
    and items still in the parent's order. Keep the pair here instead.
    """
    key = tuple(mask)
    if key not in cache:
        model = VariationModel([l for l, keep in zip(locations, mask) if keep],
                               axisOrder=["wght"])
        order = list(model.reverseMapping)
        model.reorderMasters(list(range(len(order))), order)
        cache[key] = (model, order)
    return cache[key]


def outline_signature(font, glyph_name):
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    return tuple(op for op, _ in pen.value)


# --------------------------------------------------------------------------
# the three grafted layers
# --------------------------------------------------------------------------

PROBE_KANA = 0xFF71     # check_masters() watches this one; see build_variant


def graft_halfwidth(target, scps, donors, donor0, V, model, locations):
    """Re-point every half-width codepoint at a new variable glyph.

    Outline from Source Code Pro when it has the codepoint, otherwise from
    Source Han Mono, which defines the repertoire: 590 one-cell codepoints
    where Source Han Code JP has 477, and it is the upstream that fitted the
    half-width kana to the cell instead of leaving them on Source Han Sans's
    500-unit advance.

    Mono ships as static faces, and Adobe removes overlaps per weight, so
    they only interpolate where their outlines happen to agree. Where they
    do not, the default master stands in for all of them and the glyph comes
    out fixed at Regular -- reported, because a glyph that does not follow
    the axis is a real if minor flaw in a variable font.
    """
    ref_cm, ref_hm = donor0.getBestCmap(), donor0["hmtx"]
    scp_cm = scps[0].getBestCmap()
    new_map, default_map = {}, {}
    from_scp = from_mono = partial = 0
    masters, sub_cache = {}, {}
    probe = [True] * len(donors)

    for cp, g in sorted(ref_cm.items()):
        if ref_hm[g][0] != CELL:
            continue
        if cp in scp_cm:
            name = scp_cm[cp]
            draws = [draw_from(s, name, V.scp_draw) for s in scps]
            from_scp += 1
        else:
            # Adobe removes overlaps per weight, so Mono's static faces only
            # interpolate where their outlines happen to agree. Blend over
            # the subset that does rather than freezing the glyph at the
            # default: a partial axis beats none.
            sig0 = outline_signature(donor0, g)
            usable = [d if (cp in d.getBestCmap()
                            and outline_signature(d, d.getBestCmap()[cp]) == sig0)
                      else None for d in donors]
            mask = [u is not None for u in usable]
            if cp == PROBE_KANA:
                probe[:] = mask
            sub_model, sub_order = sub_model_for(locations, mask, sub_cache)
            surviving = [d for d, keep in zip(donors, mask) if keep]
            sub_donors = [surviving[i] for i in sub_order]
            if len(sub_donors) < len(donors):
                partial += 1
                masters[len(sub_donors)] = masters.get(len(sub_donors), 0) + 1
            draws = [draw_from(d, d.getBestCmap()[cp], V.shcj_draw)
                     for d in sub_donors]
            from_mono += 1

            def draw_master(i, pen, draws=draws):
                draws[i](i, pen)

            our = target.add(draw_master, V.cell, sub_model)
            new_map[cp] = our
            continue

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
    print(f"halfwidth: {from_scp} from Source Code Pro, "
          f"{from_mono} from Source Han Mono"
          + (f" ({partial} over a subset of masters: "
             + ", ".join(f"{n}x{k} masters" for k, n in sorted(masters.items()))
             + ")" if partial else ""))
    return default_map, probe


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
# terminal grid
# --------------------------------------------------------------------------

class MasterOutlines:
    """The base font's own glyphs, one master at a time.

    A variable glyph holds every weight at once, so a scaled copy of one
    cannot be made by transforming its charstring -- the deltas would have to
    be transformed too, and the transform here is anisotropic. Folding the
    blends by hand at each master location hands the masters back separately,
    and they can then be merged into a new variable glyph exactly the way the
    grafted layers are.

    Rendering the base at each weight and reading the outlines back does not
    work: at the ends of the axis the interpolated points coincide and a
    rasterizer drops the degenerate segments, so 262 of the 797 glyphs this
    is used for come back with different point counts per weight and nothing
    interpolates.
    """

    def __init__(self, font, locations):
        self.font = font
        self.td = font["CFF2"].cff[font["CFF2"].cff.fontNames[0]]
        store = self.td.VarStore.otVarStore
        regions = store.VarRegionList.Region
        tags = [a.axisTag for a in font["fvar"].axes]
        self.counts = [len(vd.VarRegionIndex) for vd in store.VarData]
        # per VarData, the scalar of each of its regions at each location
        self.scalars = [
            [[supportScalar(loc, {tags[i]: (a.StartCoord, a.PeakCoord, a.EndCoord)
                                  for i, a in enumerate(regions[ri].VarRegionAxis)})
              for ri in vd.VarRegionIndex]
             for loc in locations]
            for vd in store.VarData]

    def _folded(self, name, master):
        cs = self.td.CharStrings[name]
        cs.decompile()
        vsindex = cs.program[1] if len(cs.program) > 1 and cs.program[1] == "vsindex" else 0
        if vsindex:
            vsindex = cs.program[0]
        k = self.counts[vsindex]
        scalars = self.scalars[vsindex][master]
        out = []
        for op, args in specializer.programToCommands(
                cs.program, getNumRegions=lambda vsi: self.counts[vsi or 0]):
            if op == "vsindex":
                continue
            flat = []
            for a in args:
                if isinstance(a, list):
                    n = a[-1]
                    for j in range(n):
                        flat.append(a[j] + sum(a[n + j * k + r] * scalars[r]
                                               for r in range(k)))
                else:
                    flat.append(a)
            out.append((op, flat))
        return out

    def draw(self, name, master, pen, transform=None):
        target = TransformPen(pen, transform) if transform else pen
        T2CharString(
            program=specializer.commandsToProgram(self._folded(name, master)),
            private=self.td.FDArray[0].Private).draw(target)

    def bounds(self, name, master):
        pen = BoundsPen(None)
        self.draw(name, master, pen)
        return pen.bounds


def _region_counts(td):
    store = td.VarStore.otVarStore
    return [len(vd.VarRegionIndex) for vd in store.VarData]


def translate_x(cs, dx, counts):
    """Shift a charstring sideways, blends and all.

    A charstring is relative after its first moveto, so one operand carries
    the whole glyph's position -- and under a blend that operand is the
    default value of the group, with the deltas untouched because every
    master moves by the same amount.
    """
    cs.decompile()
    commands = specializer.generalizeCommands(
        specializer.programToCommands(
            cs.program, getNumRegions=lambda vsi: counts[vsi or 0]))
    for i, (op, args) in enumerate(commands):
        if op != "rmoveto":
            continue
        if args and isinstance(args[0], list):
            args[0][0] += dx        # blend group: first default is x
        else:
            args[0] += dx
        commands[i] = (op, args)
        break
    else:
        return False
    cs.program = specializer.commandsToProgram(
        specializer.specializeCommands(commands, generalizeFirst=False))
    return True


def widen_fullwidth(target, V):
    """Give every full-width glyph two cells, with the ink centred.

    The terminal grid is exact only if CJK is exactly twice the Latin. Source
    Han Sans draws it on a 1000 em, so the advance grows to 2*cell and the
    outline slides half the difference; padding it on one side instead is
    what leaves the gap this variant exists to remove.
    """
    font, td = target.font, target.td
    counts = _region_counts(td)
    shift = (V.full - 1000) // 2
    hmtx = font["hmtx"]
    done = 0
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv != 1000:
            continue
        if translate_x(td.CharStrings[name], shift, counts):
            done += 1
        hmtx.metrics[name] = (V.full, lsb + shift)
    return done


def narrow_ambiguous(target, base_masters, V):
    """One-cell copies of everything the terminal gives one cell.

    Same selection as the static build -- East-Asian-Width is the question
    the terminal is itself answering -- and the same treatment: keep the
    height, give up only the width the cell actually needs. Box drawing and
    block elements are excluded because they are replaced rather than
    shrunk.
    """
    font = target.font
    new_map, made = {}, {}
    for cp, g in one_cell_codepoints(font):
        if g not in made:
            tr = narrow_transform(base_masters.bounds(g, 0), V.cell)

            def draw_master(i, pen, g=g, tr=tr):
                base_masters.draw(g, i, pen, tr)

            made[g] = target.add(draw_master, V.cell)
        new_map[cp] = made[g]
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    return len(new_map)


def graft_box_drawing(target, scps, V, line_top, line_bottom):
    """Rules and blocks from Source Code Pro, fitted to the line box.

    Scaling Source Han Sans's full-width rules down would scale their stroke
    with them, so they would stop matching the text colour and stop meeting
    their neighbours. Source Code Pro draws all 128 box-drawing and 32
    block-element glyphs at its own 600 advance, ink overhanging the cell by
    39 units each side so adjacent cells overlap and rules join cleanly.

    Its own -400..1000 em box is not our line box, though: left alone,
    vertical rules stop short of the row below and full blocks leave a
    stripe of background. One affine over the whole range fixes that and
    keeps every join and half-block boundary in place.
    """
    ky, dy = line_box_fit([c * V.scp_draw for c in SCP_EM_BOX],
                          line_top, line_bottom)
    tr = (V.scp_draw, 0, 0, V.scp_draw * ky, 0, dy)

    scp_cm = scps[0].getBestCmap()
    cmap = target.font.getBestCmap()
    new_map = {}
    for cp in list(BOX_DRAWING) + list(BLOCK_ELEMENTS):
        if cp not in scp_cm or cp not in cmap:
            continue
        def draw_master(i, pen, cp=cp, tr=tr):
            scps[i].getGlyphSet()[scp_cm[cp]].draw(TransformPen(pen, tr))

        new_map[cp] = target.add(draw_master, V.cell)
    for table in target.font["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    return len(new_map)


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


def set_names(font, user_wghts, V, italic):
    family = ("Shoyu Code Pro JP " + V.suffix).strip()
    sub = "Italic" if italic else "Regular"
    ps = "ShoyuCodeProJP" + V.suffix + "-VF" + ("Italic" if italic else "")
    full = f"{family} Italic" if italic else family
    name = font["name"]
    name.names = []
    for nid, value in ((1, family), (2, sub),
                       (3, f"{ps};shoyu-code-pro-jp"), (4, full),
                       (6, ps), (16, family), (17, sub)):
        name.setName(value, nid, 3, 1, 0x409)
    if italic:
        font["post"].italicAngle = ITALIC_ANGLE
        font["head"].macStyle |= 0x2
        font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x40) | 0x1
    # one record per named instance, then re-point fvar at them
    for instance, (weight, _, _, _) in zip(font["fvar"].instances, MASTERS):
        nid = name.addName(weight, platforms=((3, 1, 0x409),))
        instance.subfamilyNameID = nid
        instance.postscriptNameID = 0xFFFF
    cff = font["CFF2"].cff
    cff.fontNames[0] = ps
    top = cff.topDictIndex[0]
    for attr, value in (("FamilyName", family), ("FullName", full)):
        if hasattr(top, attr):
            setattr(top, attr, value)
    otl.buildStatTable(font, [{
        "tag": "wght", "name": "Weight",
        "values": [{"value": w, "name": n,
                    **({"flags": 0x2} if n == "Regular" else {}),
                    **({"linkedValue": 700.0} if n == "Regular" else {})}
                   for w, (n, _, _, _) in zip(user_wghts, MASTERS)],
    }])
    return ps


# --------------------------------------------------------------------------

def check_masters(path, expected):
    """Assert the blend reproduces the masters it was given.

    A variable font can be wrong in a way no single instance reveals: feed
    the merge pen its masters in the wrong order and the deltas still
    interpolate smoothly, just around the wrong origin. Measuring the '=' bar
    at each named weight catches it.

    The comparison is against the donor instances this build actually
    selected, not against the Source Han Code JP target. Where a donor's axis
    cannot reach the target the matcher has already said so out loud, and
    re-reporting it here would only bury the thing this check exists for.
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
    for weight, (want_bar, want_kana) in expected.items():
        font = hb.Font(face)
        font.set_variations({"wght": named[weight]})
        points = []
        font.draw_glyph(font.get_nominal_glyph(ord("=")), draw, points)
        first = points[:points.index(None)]
        got = max(y for _, y in first) - min(y for _, y in first)
        worst = max(worst, abs(got - want_bar))
        if abs(got - want_bar) > 1.5:
            failed.append(f"{weight}: '=' bar {got:.0f}, master has {want_bar:.0f}")
        # a half-width kana too: those come from a donor whose faces do not
        # all interpolate, so they ride a sub-model, which is its own chance
        # to get the master order wrong
        points = []
        font.draw_glyph(font.get_nominal_glyph(0xFF71), draw, points)
        xs = [x for p in points if p for x, _ in [p]]
        got = max(xs) - min(xs)
        worst = max(worst, abs(got - want_kana))
        if abs(got - want_kana) > 2.5:
            failed.append(f"{weight}: kana width {got:.0f}, "
                          f"master has {want_kana:.0f}")
    if failed:
        sys.exit("master check FAILED\n  " + "\n  ".join(failed))
    print(f"master check: '=' bar and half-width kana within {worst:.1f} "
          f"units of their masters at all {len(expected)} named weights")


def build_variant(V, italic, env, shcj, shmono, base_path, out_dir):
    """One family, one style. Italic is a separate file, not an axis: Source
    Code Pro's upright and italic are different designs -- one-story a, and
    so on -- so there are no compatible masters to interpolate between. The
    Japanese stays upright either way, as it does in Source Han Code JP."""
    style = " Italic" if italic else ""
    font = TTFont(base_path)
    locs, user_wghts = master_locations(font)
    model = VariationModel(locs, axisOrder=["wght"])

    # One matched donor instance per master, by the same measurement rule
    # build.py uses: Source Han Code JP's '=' bar decides the wght.
    scp_src = VFSource(env["SCP_VF_I" if italic else "SCP_VF_U"],
                       V.scp_draw / V.bar_scale, {"wght": 0})
    mona_src = VFSource(env["MONA_VF"], V.mona_draw / V.bar_scale,
                        {"wght": 0, "wdth": 100, "slnt": 0}, extrapolate=True)
    refs, scps, monas, donors, labels, expected = [], [], [], [], [], {}
    for weight, ref_name, _, mono_name in MASTERS:
        ref = shcj[ref_name + style]
        target_bar = bar_thickness(ref, ref.getBestCmap()[ord("=")])
        refs.append(ref)
        donors.append(shmono[mono_name + style])
        scp = scp_src.matched(target_bar)
        scps.append(scp)
        monas.append(mona_src.matched(target_bar, SLANT if italic else None))
        kana = BoundsPen(shmono[mono_name].getGlyphSet())
        shmono[mono_name].getGlyphSet()[
            shmono[mono_name].getBestCmap()[0xFF71]].draw(kana)
        labels.append(weight)
        expected[weight] = (
            round(bar_thickness(scp, scp.getBestCmap()[ord("=")]) * V.scp_draw),
            round((kana.bounds[2] - kana.bounds[0]) * V.shcj_draw))

    # The merge pen reads its masters positionally, with the default first --
    # varLib reorders them into the model's own order before handing them
    # over, and getDeltas is an identity permutation afterwards. Skipping this
    # silently stores the wrong master as the charstring's default value.
    regular_ref = refs[[w for w, _, _, _ in MASTERS].index("Regular")]
    order = list(model.reverseMapping)
    scps = model.reorderMasters(scps, order)
    monas = [monas[i] for i in order]
    refs = [refs[i] for i in order]
    donors = [donors[i] for i in order]
    labels = [labels[i] for i in order]
    locations = [locs[i] for i in order]

    # before anything is drawn: the box-drawing fit needs the final line box
    copy_line_metrics(font, regular_ref)

    target = Cff2Target(font, model)
    default_map, kana_masters = graft_halfwidth(
        target, scps, donors, donors[0], V, model, locations)
    # A donor glyph that does not interpolate everywhere rides a sub-model and
    # simply stops following the axis past its last master. Check it only
    # where it has one.
    kept = {labels[i] for i, keep in enumerate(kana_masters) if keep}
    expected = {w: v for w, v in expected.items() if w in kept}
    variant_maps = import_scp_variants(target, scps, default_map, V)
    if V.term:
        n_box = graft_box_drawing(target, scps, V,
                                  font["hhea"].ascent, font["hhea"].descent)
        print(f"box drawing: {n_box} rules and blocks from Source Code Pro")
    added, alts = add_ligatures(target, monas, scps, V)
    add_gsub(font, added, alts, variant_maps)
    if V.term:
        # ambiguous first: it probes for the 1000-unit advance that widening
        # is about to replace
        masters = MasterOutlines(font, [locs[i] for i in order])
        n_amb = narrow_ambiguous(target, masters, V)
        n_wide = widen_fullwidth(target, V)
        print(f"terminal grid: {n_amb} narrowed to one cell, "
              f"{n_wide} widened to {V.full}")
    strip_advance_variation(font)
    ps = set_names(font, user_wghts, V, italic)

    out = out_dir / f"{ps}.otf"
    font.save(out)
    print(f"-> {out.name}  ({font['maxp'].numGlyphs} glyphs, "
          f"cell {V.cell}:{V.full})")
    check_masters(out, expected)
    return out


def main():
    want = sys.argv[1:] or list(VARIANTS)
    unknown = [v for v in want if v not in VARIANTS]
    if unknown:
        sys.exit(f"unknown variant(s) {unknown}; choose from {list(VARIANTS)!r}")
    env = {k: os.environ.get(k) for k in
           ("SHS_VF", "SHS_DIR", "SCP_VF_U", "SCP_VF_I", "MONA_VF")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    shcj_ttc = os.environ.get("SHCJ_TTC", ROOT / "upstream" / "SourceHanCodeJP.ttc")
    shmono_ttc = os.environ.get("SHMONO_TTC", ROOT / "upstream" / "SourceHanMono.ttc")

    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    base_path = WORK / "shs-vf-jp.base.otf"
    prepare_base(env["SHS_VF"],
                 Path(env["SHS_DIR"]) / "SourceHanSansJP-Regular.otf",
                 base_path, DEFAULT_WGHT)
    shcj = {f["name"].getDebugName(4): f for f in TTCollection(shcj_ttc).fonts}
    shmono = {f["name"].getDebugName(4): f for f in TTCollection(shmono_ttc).fonts}

    for suffix in want:
        V = VARIANTS[suffix]
        for italic in (False, True):
            print(f"\n=== Shoyu Code Pro JP {V.suffix} ({suffix})"
                  f"{' Italic' if italic else ''} ===")
            build_variant(V, italic, env, shcj, shmono, base_path, out_dir)


if __name__ == "__main__":
    main()
