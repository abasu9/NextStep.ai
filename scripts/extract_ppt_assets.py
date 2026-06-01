#!/usr/bin/env python3
"""Extract slide-mapped images from EvidenceFirst_CAIDF.pptx into docs/assets/deck/."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "EvidenceFirst_CAIDF.pptx"
OUT = ROOT / "docs" / "assets" / "deck"

# ppt/media file → slide meaning (avoid blind fig-N copies; slide 17 has stock headshots)
SLIDE_IMAGES: dict[str, str] = {
    "deck-agentic-loop.png": "ppt/media/image4.png",  # slide 4 — agentic workflow
    "deck-impact.png": "ppt/media/image8.png",  # slide 3 — impact
    "deck-knowledge-graph.png": "ppt/media/image9.png",  # slide 16 — knowledge graph
    "deck-solution.png": "ppt/media/image11.png",  # slide 13 — solution
    "deck-restraint.png": "ppt/media/image16.png",  # slide 7 — restraint hero
}


def main() -> None:
    if not PPTX.exists():
        print(f"Missing {PPTX}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PPTX) as z:
        for dest_name, src in SLIDE_IMAGES.items():
            data = z.read(src)
            path = OUT / dest_name
            path.write_bytes(data)
            print(f"wrote {path.relative_to(ROOT)} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
