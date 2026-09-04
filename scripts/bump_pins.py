#!/usr/bin/env python3
"""Move the upstream pins in .github/actions/fetch-upstreams/action.yml forward.

Asks GitHub for each upstream's latest release and rewrites the pin block with
those tags. Prints a markdown summary of what moved on stdout and writes
`changed=true|false` to $GITHUB_OUTPUT; prints nothing when every pin is
already current.

`releases/latest` deliberately ignores prereleases and drafts - source-code-pro
in particular ships prerelease tags between VF drops that we don't chase. It
also, occasionally, ships a one-off hotfix release whose tag has no VF
component at all; when that happens the SCP pins are left at their current
values (a note goes to stderr) while the other upstreams still move.

Every download URL is probed before anything is written. If an upstream
renames an asset, this fails here with the URL in hand instead of opening a
PR whose CI dies twenty minutes later at the fetch step.
"""

import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ACTION = Path(".github/actions/fetch-upstreams/action.yml")

SHS_REPO = "adobe-fonts/source-han-sans"
SCP_REPO = "adobe-fonts/source-code-pro"
MONA_REPO = "githubnext/monaspace"
SHCJ_REPO = "adobe-fonts/source-han-code-jp"

PIN_RE = re.compile(r'(?P<head>echo "(?P<key>[A-Z_]+)=)(?P<val>[^"]*)(?P<tail>")')


def latest_tag(repo: str) -> str:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/latest", "--jq", ".tag_name"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def scp_vf_zip(tag: str) -> str:
    """Derive the VF asset name from source-code-pro's composite release tag.

    The tag is a slash-joined triple, e.g. "2.042R-u/1.062R-i/1.026R-vf"; the
    VF zip is named after the third component alone:
    "VF-source-code-VF-1.026R.zip".

    Raises ValueError when `tag` has no -vf component (a one-off hotfix
    release cut between VF drops) - the caller decides what to do about it.
    """
    for part in tag.split("/"):
        if part.endswith("-vf"):
            return f"VF-source-code-VF-{part[: -len('-vf')]}.zip"
    raise ValueError(f"no -vf component in source-code-pro tag {tag!r}")


def download_urls(pins: dict[str, str]) -> list[str]:
    mona = pins["MONA_TAG"]
    return [
        f"https://github.com/{SHCJ_REPO}/releases/download/"
        f"{pins['SHCJ_TAG']}/SourceHanCodeJP.ttc",
        f"https://github.com/{SHS_REPO}/releases/download/"
        f"{pins['SHS_TAG']}/17_SourceHanSansJP.zip",
        # SCP_TAG is stored %2F-encoded, so it drops into the path as-is.
        f"https://github.com/{SCP_REPO}/releases/download/"
        f"{pins['SCP_TAG']}/{pins['SCP_VF_ZIP']}",
        f"https://github.com/{MONA_REPO}/releases/download/"
        f"{mona}/monaspace-variable-{mona}.zip",
    ]


def probe(url: str) -> None:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status >= 400:
                raise SystemExit(f"HTTP {resp.status} for {url}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach {url}: {exc}") from exc


def emit(changed: bool) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")


def main() -> int:
    text = ACTION.read_text()
    current = {m["key"]: m["val"] for m in PIN_RE.finditer(text)}
    if not current:
        raise SystemExit(f"no pins found in {ACTION}")

    scp_tag = latest_tag(SCP_REPO)
    try:
        scp_pins = {
            "SCP_TAG": scp_tag.replace("/", "%2F"),
            "SCP_VF_ZIP": scp_vf_zip(scp_tag),
        }
    except ValueError:
        print(
            f"note: source-code-pro latest tag {scp_tag!r} has no -vf "
            f"component; keeping SCP_TAG={current['SCP_TAG']}",
            file=sys.stderr,
        )
        scp_pins = {"SCP_TAG": current["SCP_TAG"], "SCP_VF_ZIP": current["SCP_VF_ZIP"]}

    new = {
        "SHS_TAG": latest_tag(SHS_REPO),
        **scp_pins,
        "MONA_TAG": latest_tag(MONA_REPO),
        "SHCJ_TAG": latest_tag(SHCJ_REPO),
    }
    missing = set(new) - set(current)
    if missing:
        raise SystemExit(f"{ACTION} is missing pins: {sorted(missing)}")

    moved = {k: (current[k], v) for k, v in new.items() if current[k] != v}
    if not moved:
        emit(False)
        return 0

    for url in download_urls(new):
        probe(url)

    ACTION.write_text(
        PIN_RE.sub(lambda m: m["head"] + new.get(m["key"], m["val"]) + m["tail"], text)
    )
    emit(True)

    print("| pin | from | to |")
    print("| --- | --- | --- |")
    for key, (old, now) in moved.items():
        print(f"| `{key}` | `{old}` | `{now}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
