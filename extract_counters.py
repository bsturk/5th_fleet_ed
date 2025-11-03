#!/usr/bin/env python3
"""
Extract the full unit counter sprite sheet from MAINLIB.GXL and slice it
into individual 32x32 images.

How to use:
1. Ensure Pillow is installed (pip install pillow).
2. Run this script from the repository root:
       python extract_counters.py
3. The script writes the extracted sheet to `counters/sheet.pcx` and saves
   cropped 32x32 PNG tiles under `counters/tiles/`.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image

MAINLIB_PATH = Path("game/MAINLIB.GXL")
OUTPUT_ROOT = Path("counters")
SHEET_OUTPUT = OUTPUT_ROOT / "sheet.pcx"
TILE_OUTPUT_DIR = OUTPUT_ROOT / "tiles"
SHEET_RESOURCE_NAME = "TRM     .PCX"
TILE_SIZE = 32  # counters are arranged on a 32x32 grid


def load_resource_table(blob: bytes) -> Dict[str, Tuple[int, int]]:
    """
    Scan MAINLIB.GXL for PCX entries.

    Each entry is stored as an ASCII name terminated by 0x00, followed by
    two little-endian 32-bit integers (offset, length).
    """
    entries: Dict[str, Tuple[int, int]] = {}
    idx = 0
    blob_len = len(blob)

    while idx < blob_len:
        terminator = blob.find(b"\x00", idx)
        if terminator == -1:
            break
        name = blob[idx:terminator].decode("latin1", errors="ignore")
        next_idx = terminator + 1
        if name.endswith(".PCX"):
            offset = struct.unpack_from("<I", blob, next_idx)[0]
            length = struct.unpack_from("<I", blob, next_idx + 4)[0]
            entries[name.strip()] = (offset, length)
            next_idx += 8  # skip past the offset/length pair
        idx = next_idx

    return entries


def extract_trm_sheet(mainlib_path: Path) -> Image.Image:
    """Return the TRM sprite sheet as a Pillow Image."""
    blob = mainlib_path.read_bytes()
    resources = load_resource_table(blob)
    if SHEET_RESOURCE_NAME not in resources:
        raise FileNotFoundError(f"{SHEET_RESOURCE_NAME} not found in {mainlib_path}")

    offset, length = resources[SHEET_RESOURCE_NAME]
    slice_bytes = blob[offset : offset + length]
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SHEET_OUTPUT.write_bytes(slice_bytes)
    return Image.open(SHEET_OUTPUT).convert("RGBA")


def slice_tiles(sheet: Image.Image) -> None:
    """Cut the 32x32 tiles out of the sheet and save them as PNGs."""
    width, height = sheet.size
    cols = width // TILE_SIZE
    rows = height // TILE_SIZE

    TILE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tile_index = 0
    for row in range(rows):
        for col in range(cols):
            left = col * TILE_SIZE
            top = row * TILE_SIZE
            box = (left, top, left + TILE_SIZE, top + TILE_SIZE)
            tile = sheet.crop(box)

            # Skip tiles that are completely blank.
            if tile.getbbox() is None:
                continue

            filename = TILE_OUTPUT_DIR / f"tile_{row:02d}_{col:02d}.png"
            tile.save(filename)
            tile_index += 1

    print(f"Extracted {tile_index} tiles to {TILE_OUTPUT_DIR}")


def main() -> None:
    if not MAINLIB_PATH.exists():
        raise FileNotFoundError(
            f"MAINLIB.GXL not found at {MAINLIB_PATH}. "
            "Run this script from the repository root."
        )

    print("Extracting counter sheet…")
    sheet = extract_trm_sheet(MAINLIB_PATH)
    print(f"Sheet size: {sheet.size}, saved to {SHEET_OUTPUT}")
    print("Slicing into 32x32 tiles…")
    slice_tiles(sheet)


if __name__ == "__main__":
    main()
