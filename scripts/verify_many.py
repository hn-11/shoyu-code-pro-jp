#!/usr/bin/env python3
"""Run the face verifiers over several files at once, one process each:
verify_latin.py for a face under dist/latin/ or dist/nerd/latin/ (a Sumi
Moji face), verify.py for everything else (a JP face), each output
printed whole once its run ends. Exits non-zero if any run did.

Usage:
  python scripts/verify_many.py FONT [FONT ...]   # globs expanded here too
                                                 # (a pattern matching nothing
                                                 # is skipped, not an error;
                                                 # so is a variable font)
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def verifier(path):
    parts = Path(path).resolve().parts
    return "verify_latin.py" if "latin" in parts else "verify.py"


def run(path):
    proc = subprocess.run([sys.executable, str(SCRIPTS / verifier(path)), str(path)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          check=False)
    return path, proc.returncode, proc.stdout


def main():
    paths = [p for arg in sys.argv[1:] for p in (sorted(glob.glob(arg)) or
                                                 ([arg] if Path(arg).exists() else []))]
    # a variable font (SumiMoji[wght].otf) is verify_latin_vf.py's, not a
    # static face's verifier's: a pattern that sweeps one up skips it
    paths = [p for p in paths if "[" not in Path(p).name]
    if not paths:
        sys.exit("usage: verify_many.py FONT [FONT ...] (nothing matched)")
    failed = []
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 2) as pool:
        for path, rc, out in pool.map(run, paths):
            print(f"=== {verifier(path)} {path}: {'ok' if rc == 0 else f'FAILED (exit {rc})'}")
            print(out, end="" if out.endswith("\n") else "\n")
            if rc:
                failed.append(path)
    if failed:
        sys.exit(f"{len(failed)}/{len(paths)} verifications failed: {failed}")
    print(f"all {len(paths)} verifications passed")


if __name__ == "__main__":
    main()
