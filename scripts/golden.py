#!/usr/bin/env python3
"""Golden-file regression tool for font builds.

Compares two directories holding builds of the *same* font faces — a
"golden" directory (built before a refactor) and a "candidate" directory
(built after) — and reports whether each pair of same-named ``*.otf``
files is functionally equivalent. It is meant to catch a refactor that
silently changes cmap coverage, metrics, shaping behaviour, outlines,
metadata or CFF hinting, even though glyph *indices* are free to differ
between the two builds (a rebuild routinely renumbers glyphs).

Checks per pair, in order:
  1. cmap: identical codepoint coverage.
  2. hmtx: identical advance width for every shared codepoint.
  3. glyph count within +/-5% (informational only) plus identical GSUB
     and GPOS feature-tag sets.
  4. Shaping equivalence via uharfbuzz across a text corpus (verify.py's
     CASES, every ligature in data/mona_ligs.json, and a few extra
     strings) under several feature-flag combinations, comparing
     (cluster, x_advance, x_offset, y_offset) — never glyph ids.
  5. Outline equivalence (bounding box within --tolerance units, equal
     contour count) for every shared codepoint and every glyph reached
     while shaping the corpus.
  6. Metadata: OS/2, post, hhea, head and name-table fields.
  7. CFF hinting: 'A' 'a' 'x' '=' '日' each carry at least one hint
     operator, resolved recursively through local/global subroutines.

Usage:
    python scripts/golden.py GOLDEN_DIR CANDIDATE_DIR \
        [--tolerance 2] [--only NAMEPATTERN] [--map G=C] [--ignore-names]
"""

import argparse
import fnmatch
import json
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from verifylib import glyph_has_hint, make_shaper  # noqa: E402

HINT_CHARS = "Aax=日"

FEATURE_SETS = [
    ("calt+liga", {"calt": True, "liga": True}),
    ("calt/liga off", {"calt": False, "liga": False}),
    ("ss02 only", {"calt": False, "liga": False, "ss02": True}),
    ("hwid", {"hwid": True}),
    ("fwid", {"fwid": True}),
    ("zero", {"zero": True}),
    ("cv01", {"cv01": True}),
]

METADATA_FIELDS = [
    ("OS/2.usWeightClass", lambda tf: tf["OS/2"].usWeightClass),
    ("OS/2.fsSelection", lambda tf: tf["OS/2"].fsSelection),
    ("OS/2.sxHeight", lambda tf: tf["OS/2"].sxHeight),
    ("OS/2.sCapHeight", lambda tf: tf["OS/2"].sCapHeight),
    ("OS/2.xAvgCharWidth", lambda tf: tf["OS/2"].xAvgCharWidth),
    ("OS/2.panose.bProportion", lambda tf: tf["OS/2"].panose.bProportion),
    ("post.isFixedPitch", lambda tf: tf["post"].isFixedPitch),
    ("post.italicAngle", lambda tf: tf["post"].italicAngle),
    ("hhea.ascent", lambda tf: tf["hhea"].ascent),
    ("hhea.descent", lambda tf: tf["hhea"].descent),
    ("hhea.lineGap", lambda tf: tf["hhea"].lineGap),
    ("OS/2.sTypoAscender", lambda tf: tf["OS/2"].sTypoAscender),
    ("OS/2.sTypoDescender", lambda tf: tf["OS/2"].sTypoDescender),
    ("OS/2.sTypoLineGap", lambda tf: tf["OS/2"].sTypoLineGap),
    ("OS/2.usWinAscent", lambda tf: tf["OS/2"].usWinAscent),
    ("OS/2.usWinDescent", lambda tf: tf["OS/2"].usWinDescent),
    ("head.unitsPerEm", lambda tf: tf["head"].unitsPerEm),
]
NAME_IDS = [1, 2, 4, 6, 16, 17]


class Reporter:
    """Tracks and prints ok/FAIL lines in verify.py's style."""

    def __init__(self):
        self.checks = 0
        self.failures = 0

    def line(self, ok, msg, informational=False):
        self.checks += 1
        if not ok and not informational:
            self.failures += 1
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")
        return ok

    def tally(self, total, fails):
        """Record `total` items examined, `fails` of which failed,
        without printing anything (caller prints its own summary)."""
        self.checks += total
        self.failures += fails


def build_corpus():
    from verify import CASES

    with open(ROOT / "data" / "mona_ligs.json", encoding="utf-8") as f:
        ligatures = json.load(f)
    corpus = [text for text, _ in CASES]
    corpus += [f"a {seq} b" for seq in ligatures]
    corpus += ["日本語 → 次へ", "x ?? y", "a <-> b", "&&= ~~> <!--", "ｱｲｳ①"]
    corpus += ["←", "→", "↑", "↓", "⇐", "⇒", "⇔", "≠", "≤", "≥", "…"]
    seen, uniq = set(), []
    for s in corpus:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def feature_tags(tf, table_tag):
    if table_tag not in tf:
        return None
    table = tf[table_tag].table
    if table.FeatureList is None:
        return set()
    return {fr.FeatureTag for fr in table.FeatureList.FeatureRecord}


def check_cmap(rep, cmap_g, cmap_c):
    cps_g, cps_c = set(cmap_g), set(cmap_c)
    diff = sorted(cps_g ^ cps_c)
    rep.tally(1, 1 if diff else 0)
    if diff:
        sample = ", ".join(f"{chr(cp)!r}(U+{cp:04X})" for cp in diff[:20])
        more = f" ...and {len(diff) - 20} more" if len(diff) > 20 else ""
        print(f"FAIL cmap differs: {len(cps_g - cps_c)} only-golden, "
              f"{len(cps_c - cps_g)} only-candidate; {sample}{more}")
    else:
        print(f"ok   cmap identical ({len(cps_g)} codepoints)")
    return cps_g & cps_c


def check_advances(rep, common_cps, cmap_g, cmap_c, hmtx_g, hmtx_c):
    diffs = []
    for cp in sorted(common_cps):
        ag, ac = hmtx_g[cmap_g[cp]][0], hmtx_c[cmap_c[cp]][0]
        if ag != ac:
            diffs.append(f"{chr(cp)!r}(U+{cp:04X}) golden={ag} candidate={ac}")
    rep.tally(len(common_cps), len(diffs))
    if diffs:
        more = f" ...and {len(diffs) - 20} more" if len(diffs) > 20 else ""
        print("FAIL advances differ: " + "; ".join(diffs[:20]) + more)
    else:
        print(f"ok   advances identical ({len(common_cps)} codepoints)")


def check_glyph_count(rep, go_g, go_c):
    ng, nc = len(go_g), len(go_c)
    pct = abs(ng - nc) / max(ng, 1) * 100
    rep.line(pct <= 5, f"glyph count golden={ng} candidate={nc} "
             f"(delta {pct:.1f}%)", informational=True)


def check_feature_tags(rep, tf_g, tf_c, table_tag):
    tg, tc = feature_tags(tf_g, table_tag), feature_tags(tf_c, table_tag)
    if tg is None and tc is None:
        rep.line(True, f"{table_tag} absent in both")
    elif tg is None or tc is None:
        rep.line(False, f"{table_tag} present in one only "
                  f"(golden={tg is not None} candidate={tc is not None})")
    elif tg == tc:
        rep.line(True, f"{table_tag} feature tags identical ({len(tg)} tags)")
    else:
        rep.line(False, f"{table_tag} feature tags differ: "
                  f"only-golden={sorted(tg - tc)} only-candidate={sorted(tc - tg)}")


def check_shaping(rep, shape_g, shape_c, corpus):
    mismatches = []
    total = 0
    for s in corpus:
        for label, feats in FEATURE_SETS:
            total += 1
            ig, pg = shape_g(s, feats)
            ic, pc = shape_c(s, feats)
            seq_g = [(i.cluster, p.x_advance, p.x_offset, p.y_offset)
                     for i, p in zip(ig, pg)]
            seq_c = [(i.cluster, p.x_advance, p.x_offset, p.y_offset)
                     for i, p in zip(ic, pc)]
            if seq_g != seq_c:
                mismatches.append(f"shape {s!r} [{label}]: "
                                   f"golden={seq_g} candidate={seq_c}")
    rep.tally(total, len(mismatches))
    if mismatches:
        for line in mismatches:
            print(f"FAIL {line}")
    else:
        print(f"ok   shaping equivalent ({len(corpus)} strings x "
              f"{len(FEATURE_SETS)} feature sets = {total} combos)")


def collect_glyph_pairs(cmap_g, cmap_c, go_g, go_c, shape_g, shape_c, corpus):
    """golden glyph name -> (candidate glyph name, human label)."""
    pairs = {}
    for cp in sorted(set(cmap_g) & set(cmap_c)):
        pairs.setdefault(cmap_g[cp], (cmap_c[cp], f"U+{cp:04X} {chr(cp)!r}"))
    feats = {"calt": True, "liga": True}
    for s in corpus:
        ig, _ = shape_g(s, feats)
        ic, _ = shape_c(s, feats)
        if len(ig) != len(ic):
            continue  # already reported by check_shaping
        for idx, (a, b) in enumerate(zip(ig, ic)):
            gname, cname = go_g[a.codepoint], go_c[b.codepoint]
            pairs.setdefault(gname, (cname, f"shaped {s!r}[{idx}]"))
    return pairs


def glyph_metrics(glyphset, cache, name):
    if name not in cache:
        bp = BoundsPen(glyphset)
        glyphset[name].draw(bp)
        rp = RecordingPen()
        glyphset[name].draw(rp)
        cache[name] = (bp.bounds, sum(1 for op, _ in rp.value if op == "moveTo"))
    return cache[name]


def check_outlines(rep, tf_g, tf_c, pairs, tolerance):
    gs_g, gs_c = tf_g.getGlyphSet(), tf_c.getGlyphSet()
    cache_g, cache_c = {}, {}
    offenders = []
    for gname, (cname, label) in pairs.items():
        try:
            bounds_g, nc_g = glyph_metrics(gs_g, cache_g, gname)
            bounds_c, nc_c = glyph_metrics(gs_c, cache_c, cname)
        except KeyError as e:
            offenders.append(f"{label}: glyph missing ({e})")
            continue
        if bounds_g is None or bounds_c is None:
            if bounds_g != bounds_c:
                offenders.append(f"{label} ({gname!r}/{cname!r}): "
                                  f"bounds golden={bounds_g} candidate={bounds_c}")
            continue
        delta = [abs(a - b) for a, b in zip(bounds_g, bounds_c)]
        if max(delta) > tolerance or nc_g != nc_c:
            offenders.append(
                f"{label} ({gname!r}/{cname!r}): golden={bounds_g} "
                f"candidate={bounds_c} delta={tuple(round(d, 1) for d in delta)} "
                f"contours golden={nc_g} candidate={nc_c}")
    rep.tally(len(pairs), len(offenders))
    if offenders:
        for line in offenders[:30]:
            print(f"FAIL outline {line}")
        if len(offenders) > 30:
            print(f"...and {len(offenders) - 30} more outline offenders")
    else:
        print(f"ok   outlines equivalent ({len(pairs)} glyphs compared, "
              f"tolerance={tolerance})")


def check_metadata(rep, tf_g, tf_c, ignore_names):
    diffs = []
    for label, fn in METADATA_FIELDS:
        vg, vc = fn(tf_g), fn(tf_c)
        if vg != vc:
            diffs.append(f"{label} golden={vg} candidate={vc}")
    n_name_checks = 0
    if not ignore_names:
        n_name_checks = len(NAME_IDS)
        for nid in NAME_IDS:
            ng = tf_g["name"].getDebugName(nid)
            nc = tf_c["name"].getDebugName(nid)
            if ng != nc:
                diffs.append(f"name.{nid} golden={ng!r} candidate={nc!r}")
    rep.tally(len(METADATA_FIELDS) + n_name_checks, len(diffs))
    if diffs:
        print("FAIL metadata differs: " + "; ".join(diffs))
    else:
        print("ok   metadata identical")


def check_hints(rep, tf_g, tf_c, cmap_g, cmap_c):
    if "CFF " not in tf_g or "CFF " not in tf_c:
        print("skip  hint check (non-CFF font)")
        return
    td_g = tf_g["CFF "].cff[tf_g["CFF "].cff.fontNames[0]]
    td_c = tf_c["CFF "].cff[tf_c["CFF "].cff.fontNames[0]]
    for ch in HINT_CHARS:
        cp = ord(ch)
        if cp not in cmap_g or cp not in cmap_c:
            continue
        hg = glyph_has_hint(td_g.CharStrings[cmap_g[cp]])
        hc = glyph_has_hint(td_c.CharStrings[cmap_c[cp]])
        rep.line(hg and hc, f"hinted {ch!r} (golden={hg} candidate={hc})")


def compare_pair(golden_path, candidate_path, args, corpus):
    rep = Reporter()
    tf_g, tf_c = TTFont(str(golden_path)), TTFont(str(candidate_path))
    cmap_g, cmap_c = tf_g.getBestCmap(), tf_c.getBestCmap()
    hmtx_g, hmtx_c = tf_g["hmtx"], tf_c["hmtx"]
    go_g, go_c = tf_g.getGlyphOrder(), tf_c.getGlyphOrder()

    common_cps = check_cmap(rep, cmap_g, cmap_c)
    check_advances(rep, common_cps, cmap_g, cmap_c, hmtx_g, hmtx_c)
    check_glyph_count(rep, go_g, go_c)
    check_feature_tags(rep, tf_g, tf_c, "GSUB")
    check_feature_tags(rep, tf_g, tf_c, "GPOS")

    shape_g, shape_c = make_shaper(golden_path), make_shaper(candidate_path)
    check_shaping(rep, shape_g, shape_c, corpus)

    pairs = collect_glyph_pairs(cmap_g, cmap_c, go_g, go_c, shape_g, shape_c, corpus)
    check_outlines(rep, tf_g, tf_c, pairs, args.tolerance)

    check_metadata(rep, tf_g, tf_c, args.ignore_names)
    check_hints(rep, tf_g, tf_c, cmap_g, cmap_c)
    return rep


def name_matches(stem, pattern):
    if pattern is None:
        return True
    if any(c in pattern for c in "*?["):
        return fnmatch.fnmatch(stem, pattern)
    return pattern in stem


def find_pairs(args):
    golden = {p.name for p in args.golden_dir.glob("*.otf")}
    candidate = {p.name for p in args.candidate_dir.glob("*.otf")}
    golden = {n for n in golden if name_matches(Path(n).stem, args.only)}
    candidate = {n for n in candidate if name_matches(Path(n).stem, args.only)}

    map_dict = {}
    for m in args.map:
        g, sep, c = m.partition("=")
        if not sep:
            raise SystemExit(f"--map must be GOLDEN=CANDIDATE, got {m!r}")
        map_dict[g] = c

    pairs, unmatched_c = [], set(candidate)
    unmatched_g = set(golden)
    for g in sorted(golden):
        c = map_dict.get(g, g)
        if c in candidate:
            pairs.append((g, c))
            unmatched_g.discard(g)
            unmatched_c.discard(c)
    return pairs, sorted(unmatched_g), sorted(unmatched_c)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("golden_dir", type=Path)
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--tolerance", type=float, default=2,
                         help="max outline bbox delta in units (default 2)")
    parser.add_argument("--only", default=None,
                         help="only compare files whose basename matches "
                         "this substring or glob pattern")
    parser.add_argument("--map", action="append", default=[],
                         metavar="GOLDEN=CANDIDATE",
                         help="pair a golden filename with a differently "
                         "named candidate file; repeatable")
    parser.add_argument("--ignore-names", action="store_true",
                         help="skip name IDs 1/2/4/6/16/17 (renamed families)")
    args = parser.parse_args()

    corpus = build_corpus()
    pairs, only_golden, only_candidate = find_pairs(args)

    total = Reporter()
    for name in only_golden:
        print(f"FAIL {name}: present in golden dir only, no candidate match")
        total.tally(1, 1)
    for name in only_candidate:
        print(f"FAIL {name}: present in candidate dir only, no golden match")
        total.tally(1, 1)

    for golden_name, candidate_name in pairs:
        print(f"== {golden_name} vs {candidate_name} ==")
        rep = compare_pair(args.golden_dir / golden_name,
                            args.candidate_dir / candidate_name, args, corpus)
        print(f"-- {golden_name}: {rep.checks} checks, {rep.failures} failures --")
        total.tally(rep.checks, rep.failures)

    n_files = len(pairs) + len(only_golden) + len(only_candidate)
    print(f"GOLDEN: {n_files} files, {total.checks} checks, "
          f"{total.failures} failures")
    if total.failures:
        sys.exit(1)
    # a gate that compared nothing is not a pass: a typo in --only, a
    # wrong directory or an empty one printed the same '0 failures' as a
    # clean run and exited 0
    if not total.checks:
        sys.exit("GOLDEN: nothing was compared — check the directories "
                 "and --only")


if __name__ == "__main__":
    main()
