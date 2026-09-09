#!/usr/bin/env python3
"""One usWinAscent/Descent pair per Sumi Moji family, over every static
face in the output directories — build_latin.harmonize_win_metrics run
on its own.

build_latin.py harmonizes the faces it finds after a build; the release
workflow builds two weights per job, so no job ever sees its family
whole. The package job runs this over the assembled dist/ before
zipping: Sumi Moji in dist/latin/ and its Nerd Fonts patch in
dist/nerd/latin/ (patched from the unharmonized faces, so it is
harmonized on its own here).

Usage:
  python scripts/harmonize_latin.py [DIST]   # default: dist/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from build_latin import harmonize_win_metrics  # noqa: E402
from verifylib import static_faces  # noqa: E402

# (directory under dist, PostScript family) per family to harmonize
FAMILIES = [
    ("latin", build.LATIN_FAMILY[1]),
    ("nerd/latin", build.LATIN_FAMILY[1] + "NFM"),
]


def main():
    dist = Path(sys.argv[1]) if len(sys.argv) > 1 else build.ROOT / "dist"
    for subdir, ps_family in FAMILIES:
        paths = static_faces(dist / subdir, ps_family)
        if not paths:
            print(f"{subdir}/{ps_family}: no faces, skipped")
            continue
        a, d = harmonize_win_metrics(paths)
        print(f"{subdir}/{ps_family}: win metrics {a}/{d} over {len(paths)} faces")


if __name__ == "__main__":
    main()
