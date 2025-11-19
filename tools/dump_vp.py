#!/usr/bin/env python3
"""Utility to dump victory point values from the template library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable

sys.path.append(str(Path(__file__).resolve().parents[1]))

from editor.data import TemplateRecord, load_template_library


def _format_rows(records: Iterable[TemplateRecord]) -> str:
    lines = []
    for rec in sorted(records, key=lambda r: (r.victory_points or -1, r.name.lower())):
        vp = rec.victory_points if rec.victory_points is not None else "?"
        lines.append(f"  {rec.name:<24} {vp}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump template victory point values.")
    parser.add_argument(
        "--game-dir",
        type=Path,
        default=Path("game"),
        help="Path to the original game directory (default: ./game)",
    )
    args = parser.parse_args()

    library: Dict[str, list[TemplateRecord]] = load_template_library(args.game_dir)

    for kind in ("air", "surface", "sub"):
        records = library.get(kind, [])
        if not records:
            continue
        values = [r.victory_points for r in records if r.victory_points is not None]
        vp_summary = "n/a"
        if values:
            vp_summary = f"min={min(values)} max={max(values)}"
        print(f"{kind.title()} templates ({len(records)} entries) — {vp_summary}")
        print(_format_rows(records))
        print()


if __name__ == "__main__":
    main()
