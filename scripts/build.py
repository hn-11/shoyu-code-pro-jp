#!/usr/bin/env python3
"""Assemble Shoyu Code Pro JP from live upstreams.

Recipe (Source Han Mono's approach, re-executed against latest releases):
  - Japanese / full-width layer: Source Han Sans JP (latest, per weight)
  - Half-width Latin layer:      Source Code Pro VF, scaled 10/9 to 667
                                 (Adobe's own SHCJ derivation, re-run)
  - Ligatures (50):              Monaspace VF (data/mona_ligs.json)
  - Source Han Code JP serves as the PAIRING REFERENCE — each face's '='
    bar thickness decides the SCP/Monaspace wght instance — and as the
    donor for half-width glyphs SCP lacks (half-width kana etc.), plus
    the vertical line metrics, so the rendered result stays continuous
    with what SHCJ users know.

All weight pairing is by measurement (binary search on the VF wght axis),
not by name. Italic faces take SCP Italic VF + upright Japanese, matching
SHCJ's own behavior.

Families (suffix -> half-width cell):
  ""   667  2:3 (SHCJ metrics) — editor AND terminal, as SHCJ always was
  "35"  600  Source Code Pro's native proportion

A 1:2 "Console" variant was built and retired: squeezing SCP's roomy
skeleton into a 500 cell loses too much (25% smaller Latin isotropically,
or ~17% condensation + stroke-contrast skew anisotropically). The
narrow_ambiguous/rescale machinery stays for anyone who wants it back.

Env (all required):
  SHS_DIR  = dir with SourceHanSansJP-<Weight>.otf
  SCP_VF_U = SourceCodeVF-Upright.otf   SCP_VF_I = SourceCodeVF-Italic.otf
  SHCJ_TTC = upstream/SourceHanCodeJP.ttc (default)   MONA_VF = Monaspace VF
"""

import json
import os
import sys
import unicodedata
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.otlLib import builder as otl
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
CELL = 667          # half-width advance of the 2:3 metrics
MONA_CELL = 1240    # Monaspace advance (upm 2000)
MONA_K = CELL / MONA_CELL
SCP_CELL = 600      # Source Code Pro advance (upm 1000)
SCP_K = CELL / SCP_CELL  # 10/9, Adobe's SHCJ scale factor

VARIANTS = {"": 667, "35": 600}

# (output weight name, SHCJ reference face, Source Han Sans static file)
FACES = [
    ("ExtraLight", "Source Han Code JP EL", "SourceHanSansJP-ExtraLight.otf"),
    ("Light", "Source Han Code JP L", "SourceHanSansJP-Light.otf"),
    ("Normal", "Source Han Code JP N", "SourceHanSansJP-Normal.otf"),
    ("Regular", "Source Han Code JP R", "SourceHanSansJP-Regular.otf"),
    ("Medium", "Source Han Code JP M", "SourceHanSansJP-Medium.otf"),
    ("Bold", "Source Han Code JP R Bold", "SourceHanSansJP-Bold.otf"),
    ("Heavy", "Source Han Code JP H", "SourceHanSansJP-Heavy.otf"),
]

LIGATURES = json.load(open(ROOT / "data" / "mona_ligs.json"))


def bar_thickness(font, glyph_name):
    """Height of the top contour of '=' — our stroke-weight probe."""
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    contours, cur = [], []
    for op, args in pen.value:
        if op == "moveTo":
            cur = [args[0]]
        elif op == "closePath":
            contours.append(cur)
            cur = []
        else:
            cur.extend(list(args))
    ys = [p[1] for p in contours[0]]
    return max(ys) - min(ys)


class VFSource:
    """Variable-font instances matched to a target '=' bar thickness.

    Used for both Monaspace (wght/wdth/slnt) and Source Code Pro (wght only)
    — the axes dict template decides which. Matching is a binary search on
    wght so the operator/Latin stroke weight equals the reference face's.
    """

    def __init__(self, vf_path, scale, axes):
        self.vf_path = vf_path
        self.scale = scale        # em scale applied when the glyphs are used
        self.axes = axes          # template; wght filled by the search
        self._cache = {}

    def matched(self, target_units, slant=None):
        key = (round(target_units), slant if slant is None else round(slant))
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / self.scale
        lo, hi = 200.0, 800.0
        inst = None
        for _ in range(9):
            mid = (lo + hi) / 2
            inst = TTFont(self.vf_path)
            axes = dict(self.axes, wght=mid)
            if slant is not None and "slnt" in axes:
                axes["slnt"] = max(-11.0, min(0.0, slant))
            instantiateVariableFont(inst, axes, inplace=True)
            t = bar_thickness(inst, inst.getBestCmap()[ord("=")])
            if t < pre_scale_target:
                lo = mid
            else:
                hi = mid
        self._cache[key] = inst
        return inst


def glyph_vcenter(font, gname, scale=1.0):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[gname].draw(pen)
    return (pen.bounds[1] + pen.bounds[3]) / 2 * scale


def pen_width(private, advance):
    """CFF charstring width operand: omitted when equal to defaultWidthX,
    otherwise encoded relative to nominalWidthX."""
    default = getattr(private, "defaultWidthX", 0)
    nominal = getattr(private, "nominalWidthX", 0)
    return None if advance == default else advance - nominal


def alloc_glyph_name(font):
    """Allocate an unused CID. Subset OTFs have sparse CIDs (SHS JP tops
    out at 65497 with only ~18k glyphs), so len(order) collides with real
    names and max+1 overflows 65534 — walk the gaps instead."""
    used = getattr(font, "_used_cids", None)
    if used is None:
        used = {int(g[3:]) for g in font.getGlyphOrder()
                if g.startswith("cid") and g[3:].isdigit()}
        font._used_cids = used
        font._next_cid = 1
    n = font._next_cid
    while n in used:
        n += 1
    used.add(n)
    font._next_cid = n + 1
    return f"cid{n:05d}"


def append_glyph(font, td, name, cs, fd_index, width, lsb=0):
    order = font.getGlyphOrder()
    order.append(name)
    if td.charset is not order:  # same list object for CFF fonts
        td.charset.append(name)
    td.FDSelect.gidArray.append(fd_index)
    i = len(td.CharStrings.charStringsIndex.items)
    td.CharStrings.charStringsIndex.append(cs)
    td.CharStrings.charStrings[name] = i
    font["hmtx"].metrics[name] = (width, lsb)
    if "vmtx" in font:
        cmap = font.getBestCmap()
        font["vmtx"].metrics[name] = font["vmtx"].metrics[cmap[0x65E5]]
    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)


def graft_halfwidth(base, scp, ref):
    """Give `base` (Source Han Sans JP) its half-width layer.

    Every codepoint SHCJ maps to a 667-advance glyph is re-pointed to a new
    glyph: outline from the SCP instance scaled 10/9 when SCP has it,
    otherwise copied verbatim from the SHCJ reference face (half-width
    kana and a handful of symbols SCP never had).
    """
    ref_cm, ref_hm = ref.getBestCmap(), ref["hmtx"]
    scp_cm = scp.getBestCmap()
    scp_gs, ref_gs = scp.getGlyphSet(), ref.getGlyphSet()
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private

    new_map = {}
    default_map = {}  # scp glyph name -> our glyph name (for variant wiring)
    from_scp = from_ref = 0
    for cp, g in sorted(ref_cm.items()):
        if ref_hm[g][0] != CELL:
            continue
        pen = T2CharStringPen(pen_width(private, CELL), scp_gs)
        if cp in scp_cm:
            scp_gs[scp_cm[cp]].draw(
                TransformPen(pen, (SCP_K, 0, 0, SCP_K, 0, 0)))
            lsb = round(scp["hmtx"][scp_cm[cp]][1] * SCP_K)
            from_scp += 1
        else:
            ref_gs[g].draw(TransformPen(pen, (1, 0, 0, 1, 0, 0)))
            lsb = ref_hm[g][1]
            from_ref += 1
        name = alloc_glyph_name(base)
        append_glyph(base, td, name, pen.getCharString(private=private),
                     fd_index, CELL, lsb)
        new_map[cp] = name
        if cp in scp_cm:
            default_map[scp_cm[cp]] = name

    # Drop legacy non-Unicode subtables (Mac (1,0) format 6): they still
    # point at the old proportional Latin, and FontForge unifies subtables
    # on load — the conflict silently drops ~40 ASCII slots after
    # cidFlatten, which is how the Nerd Font variants lost 'M' et al.
    base["cmap"].tables = [t for t in base["cmap"].tables if t.isUnicode()]
    for table in base["cmap"].tables:
        for cp, name in new_map.items():
            if cp in table.cmap:
                table.cmap[cp] = name
    return from_scp, from_ref, default_map


def _remap_scp_tag(tag):
    """SCP feature tags, shifted around our own: ssNN -> ss(NN+10) because
    ss01-ss08 are the ligature groups; cv/zero/salt keep their names."""
    if tag in ("zero", "salt") or tag.startswith("cv"):
        return tag
    if tag.startswith("ss"):
        return f"ss{int(tag[2:]) + 10:02d}"
    return None


def import_scp_variants(base, scp, default_map):
    """Carry SCP's own character variants (dotted/slashed zero bodies,
    one/two-story a, g shapes, salt...) through the graft. Returns
    {our tag: {our default glyph: our variant glyph}}."""
    gsub = scp["GSUB"].table
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private
    scp_gs = scp.getGlyphSet()

    imported = {}   # scp variant glyph -> our glyph name
    tag_maps = {}
    for fr in gsub.FeatureList.FeatureRecord:
        tag = _remap_scp_tag(fr.FeatureTag)
        if tag is None:
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gsub.LookupList.Lookup[li]
            if lookup.LookupType != 1:
                continue
            for st in lookup.SubTable:
                for src, dst in st.mapping.items():
                    if src not in default_map:
                        continue
                    if dst not in imported:
                        pen = T2CharStringPen(
                            pen_width(private, CELL), scp_gs)
                        scp_gs[dst].draw(
                            TransformPen(pen, (SCP_K, 0, 0, SCP_K, 0, 0)))
                        name = alloc_glyph_name(base)
                        append_glyph(
                            base, td, name,
                            pen.getCharString(private=private),
                            fd_index, CELL,
                            round(scp["hmtx"][dst][1] * SCP_K))
                        imported[dst] = name
                    tag_maps.setdefault(tag, {})[default_map[src]] = imported[dst]
    return tag_maps


def copy_line_metrics(base, ref):
    """Keep SHCJ's vertical rhythm and width metadata — the rendered line
    height and how font pickers classify the font must not change."""
    for tbl, attrs in (
        ("hhea", ("ascent", "descent", "lineGap")),
        ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap",
                  "usWinAscent", "usWinDescent", "xAvgCharWidth")),
        ("post", ("isFixedPitch",)),
    ):
        for a in attrs:
            setattr(base[tbl], a, getattr(ref[tbl], a))
    base["OS/2"].panose = ref["OS/2"].panose


def narrow_ambiguous(font):
    """Console (1:2) only: East-Asian-Width Ambiguous/Narrow codepoints that
    carry full-width (1000) glyphs — … → ≠ Greek etc. — get a half-width
    (500) scaled copy, because terminals allocate them ONE cell by default
    and the full-width ink bleeds into the neighbour (Sarasa Term does the
    same). CJK (W/F) stays two cells; the original glyphs are untouched.
    Must run AFTER rescale, on the 500-cell font."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    fd_index = td.FDSelect[font.getGlyphID(cmap[ord("A")])]
    private = td.FDArray[fd_index].Private
    new_map = {}
    made = {}  # source glyph -> scaled glyph (dedup shared glyphs)
    for cp, g in sorted(cmap.items()):
        if font["hmtx"][g][0] != 1000:
            continue
        if unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            continue
        if g not in made:
            pen = T2CharStringPen(pen_width(private, 500), gs)
            bp = BoundsPen(gs)
            gs[g].draw(bp)
            cy = (bp.bounds[1] + bp.bounds[3]) / 2 if bp.bounds else 0
            # halve about the vertical center so marks don't sink
            gs[g].draw(TransformPen(pen, (0.5, 0, 0, 0.5, 0, round(cy / 2))))
            name = alloc_glyph_name(font)
            append_glyph(font, td, name, pen.getCharString(private=private),
                         fd_index, 500)
            made[g] = name
        new_map[cp] = made[g]
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    return len(new_map)


def set_names(font, suffix, weight, italic):
    """Fresh name table: standard family-per-weight scheme."""
    base_family = ("Shoyu Code Pro JP " + suffix).strip()
    ribbi = weight in ("Regular", "Bold")
    family = base_family if ribbi else f"{base_family} {weight}"
    sub = (weight if ribbi else "Regular") + (" Italic" if italic else "")
    sub = sub.replace("Regular Italic", "Italic")
    psfam = "ShoyuCodeProJP" + suffix
    ps = f"{psfam}-{weight}{'Italic' if italic else ''}"
    full = f"{family} {sub}".replace(" Regular", "").strip()
    name = font["name"]
    name.names = []
    for nid, val in ((1, family), (2, sub), (3, f"{ps};shoyu-code-pro-jp"),
                     (4, full), (6, ps),
                     (16, base_family),
                     (17, (weight + (" Italic" if italic else ""))
                          .replace("Regular Italic", "Italic"))):
        name.setName(val, nid, 3, 1, 0x409)
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    td = cff.topDictIndex.items[0]
    if hasattr(td, "FamilyName"):
        td.FamilyName = family
    if hasattr(td, "FullName"):
        td.FullName = full
    if italic:
        font["post"].italicAngle = -12
        font["head"].macStyle |= 0x2
        font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x40) | 0x1
    return ps


def add_glyphs(font, mona, alts):
    """Append the imported ligature glyphs; return {seq: glyph name}.
    Alternate (.alt) designs are appended too and recorded in `alts`."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    order = font.getGlyphOrder()
    cmap = font.getBestCmap()
    mona_gs = mona.getGlyphSet()
    mona_names = set(mona.getGlyphOrder())

    # baseline correction: align the two fonts' '=' vertical centers
    dy = round(
        glyph_vcenter(font, cmap[ord("=")])
        - glyph_vcenter(mona, mona.getBestCmap()[ord("=")], MONA_K))
    # FD assignment: reuse the FD of an existing symbol glyph
    fd_index = td.FDSelect[font.getGlyphID(cmap[0x2260])]
    private = td.FDArray[fd_index].Private

    added = {}
    for seq, spec in LIGATURES.items():
        if any(g not in mona_names for g in spec["glyphs"]):
            print(f"  skip {seq!r}: donor glyph missing")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        cells = spec["cells"]
        width = CELL * cells
        pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
        if len(spec["glyphs"]) == 1:
            # a single spanning glyph is drawn in its final cell; shift right
            offsets = [(cells - 1) * MONA_CELL * MONA_K]
        else:
            offsets = [i * MONA_CELL * MONA_K for i in range(len(spec["glyphs"]))]
        for gname, dx in zip(spec["glyphs"], offsets):
            mona_gs[gname].draw(
                TransformPen(pen, (MONA_K, 0, 0, MONA_K, dx, dy)))
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, width)
        added[seq] = name

        # alternate design, if Monaspace ships one (cv01 toggles to it)
        alt_src = spec["glyphs"][0] + ".alt"
        if len(spec["glyphs"]) == 1 and alt_src in mona_names:
            pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
            mona_gs[alt_src].draw(TransformPen(
                pen, (MONA_K, 0, 0, MONA_K, (cells - 1) * MONA_CELL * MONA_K, dy)))
            alt_name = alloc_glyph_name(font)
            append_glyph(font, td, alt_name, pen.getCharString(private=private),
                         fd_index, width)
            alts[name] = alt_name

    return added


def _new_lookup(gsub, subtable):
    lookup = otl.buildLookup([subtable])
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount += 1
    return gsub.LookupList.LookupCount - 1


def _new_feature(gsub, tag, lookup_indices):
    fr = otTables.FeatureRecord()
    fr.FeatureTag = tag
    fr.Feature = otTables.Feature()
    fr.Feature.FeatureParams = None
    fr.Feature.LookupListIndex = list(lookup_indices)
    fr.Feature.LookupCount = len(lookup_indices)
    gsub.FeatureList.FeatureRecord.append(fr)
    gsub.FeatureList.FeatureCount += 1
    return gsub.FeatureList.FeatureCount - 1


def add_gsub(font, added, alts, variant_maps=None):
    """calt/liga carry every ligature (default on); each Monaspace-style
    group is additionally exposed as ssNN so users can toggle selectively
    (calt off + ssNN on). cv01 switches to the .alt operator designs."""
    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    groups = {}
    for seq, g in added.items():
        grp = LIGATURES[seq]["group"]
        groups.setdefault(grp, {})[tuple(cmap[ord(c)] for c in seq)] = g

    # calt/liga use ONE combined lookup: LigatureSubst is longest-match only
    # within a single subtable — sequential per-group lookups would let
    # ss01's '>=' eat the tail of '>>=' before ss02 ever sees it.
    combined = {}
    for m in groups.values():
        combined.update(m)
    combined_lookup = _new_lookup(
        gsub, otl.buildLigatureSubstSubtable(combined))

    group_lookups = {}
    for grp in sorted(groups):
        group_lookups[grp] = _new_lookup(
            gsub, otl.buildLigatureSubstSubtable(groups[grp]))

    feature_indices = []
    for tag in ("calt", "liga"):
        feature_indices.append(_new_feature(gsub, tag, [combined_lookup]))
    for grp in sorted(group_lookups):
        feature_indices.append(_new_feature(gsub, grp, [group_lookups[grp]]))
    if alts:
        alt_lookup = _new_lookup(gsub, otl.buildSingleSubstSubtable(alts))
        feature_indices.append(_new_feature(gsub, "cv99", [alt_lookup]))
    for tag in sorted(variant_maps or {}):
        vlookup = _new_lookup(
            gsub, otl.buildSingleSubstSubtable(variant_maps[tag]))
        feature_indices.append(_new_feature(gsub, tag, [vlookup]))

    for script in gsub.ScriptList.ScriptRecord:
        langsys_list = [script.Script.DefaultLangSys] + [
            ls.LangSys for ls in script.Script.LangSysRecord
        ]
        for ls in langsys_list:
            if ls is None:
                continue
            ls.FeatureIndex.extend(feature_indices)
            ls.FeatureCount = len(ls.FeatureIndex)


def rescale(font, cell, ky=None):
    """Rescale half-width glyphs (and ligatures) from 667 to `cell`.
    Isotropic by default — Adobe's own SHCJ recipe. Pass `ky` to keep a
    taller vertical scale (condensed experiment: terminal fonts like
    HackGen/PlemolJP run cap/half ~1.3 vs SCP's roomy 1.09)."""
    scale_map = {667: cell, 1334: 2 * cell, 2001: 3 * cell}
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    k = cell / 667
    ky = k if ky is None else ky
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv not in scale_map:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, scale_map[adv]), gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, ky, 0, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (scale_map[adv], round(lsb * k))
    for name, cs in new_cs.items():  # swap after drawing everything
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
    # the average follows the half-width layer it describes
    font["OS/2"].xAvgCharWidth = round(font["OS/2"].xAvgCharWidth * k)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = {k: os.environ.get(k) for k in
           ("SHS_DIR", "SCP_VF_U", "SCP_VF_I", "MONA_VF")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    shcj_ttc = os.environ.get("SHCJ_TTC", ROOT / "upstream" / "SourceHanCodeJP.ttc")
    mona_src = VFSource(env["MONA_VF"], MONA_K, {"wght": 0, "wdth": 100, "slnt": 0})
    scp_u = VFSource(env["SCP_VF_U"], SCP_K, {"wght": 0})
    scp_i = VFSource(env["SCP_VF_I"], SCP_K, {"wght": 0})

    refs = {f["name"].getDebugName(4): f for f in TTCollection(shcj_ttc).fonts}
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    for suffix, cell in VARIANTS.items():
        for weight, ref_name, shs_file in FACES:
            for italic in (False, True):
                face_label = f"{weight}{' Italic' if italic else ''}"
                if only and only not in face_label:
                    continue
                ref = refs[ref_name + (" Italic" if italic else "")]
                target = bar_thickness(ref, ref.getBestCmap()[ord("=")])
                scp = (scp_i if italic else scp_u).matched(target)
                base = TTFont(Path(env["SHS_DIR"]) / shs_file)
                n_scp, n_ref, default_map = graft_halfwidth(base, scp, ref)
                variant_maps = import_scp_variants(base, scp, default_map)
                copy_line_metrics(base, ref)
                mona = mona_src.matched(
                    target, ref["post"].italicAngle if italic else None)
                alts = {}
                added = add_glyphs(base, mona, alts)
                add_gsub(base, added, alts, variant_maps)
                if cell != CELL:
                    rescale(base, cell)
                if suffix == "Console":
                    narrow_ambiguous(base)
                ps = set_names(base, suffix, weight, italic)
                out = out_dir / f"{ps}.otf"
                base.save(out)
                print(f"{face_label}{f' [{suffix}]' if suffix else ''}: "
                      f"scp={n_scp} shcj={n_ref} ligs={len(added)} -> {out.name}")


if __name__ == "__main__":
    main()
