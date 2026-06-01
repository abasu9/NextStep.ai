#!/usr/bin/env python3
"""Extract images from EvidenceFirst_CAIDF.pptx into docs/assets/ppt/."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "EvidenceFirst_CAIDF.pptx"
OUT = ROOT / "docs" / "assets" / "ppt"
SKIP_OVER_KB = 800  # skip huge slides for web


def main() -> None:
    if not PPTX.exists():
        print(f"Missing {PPTX}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PPTX) as z:
        for name in z.namelist():
            if not name.startswith("ppt/media/"):
                continue
            data = z.read(name)
            dest = OUT / Path(name).name
            if len(data) > SKIP_OVER_KB * 1024:
                print(f"skip {dest.name} ({len(data) // 1024} KB)")
                continue
            dest.write_bytes(data)
            print(f"wrote {dest.name} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
