"""Parser for Genus Microprogramming GXL archive files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class GXLEntry:
    """An entry in a GXL archive."""

    name: str
    offset: int
    size: int
    data: bytes


def load_gxl_archive(path: Path) -> List[GXLEntry]:
    """
    Load a GXL archive and return all entries.

    GXL format (Genus Microprogramming):
    - Copyright header (variable length)
    - Directory entries with metadata before each filename
    - Each entry: [metadata bytes] filename (null-terminated) offset (4 bytes LE) size (4 bytes LE)
    - Data follows directory
    """
    blob = path.read_bytes()

    entries: List[GXLEntry] = []
    pos = 0x80  # Skip copyright header

    while pos < len(blob) - 30:
        # Look for .PCX extension as a reliable marker
        # Search forward for ".PCX\0" pattern
        pcx_pos = blob.find(b'.PCX\x00', pos, pos + 100)
        if pcx_pos == -1:
            # Try to find end of directory - look for large block of non-ASCII
            pos += 1
            if pos > 10000:  # Reasonable limit for directory size
                break
            continue

        # Work backwards to find start of filename
        # Filenames start after some metadata bytes
        name_start = pcx_pos
        while name_start > pos and blob[name_start - 1] != 0:
            name_start -= 1
            # Filenames are max ~20 chars
            if pcx_pos - name_start > 20:
                break

        # Skip if we went too far back
        if pcx_pos - name_start > 20 or name_start <= pos:
            pos = pcx_pos + 5
            continue

        # Extract filename
        name = blob[name_start:pcx_pos + 4].decode('ascii', errors='ignore').strip()

        # Check if this looks like a valid filename
        if not name or len(name) < 4:
            pos = pcx_pos + 5
            continue

        # Read offset and size after null terminator
        data_pos = pcx_pos + 5  # After .PCX\0

        if data_pos + 8 > len(blob):
            break

        offset = int.from_bytes(blob[data_pos:data_pos+4], 'little')
        size = int.from_bytes(blob[data_pos+4:data_pos+8], 'little')

        # Sanity check - size and offset should be reasonable
        if size == 0 or size > 1000000 or offset > len(blob) or offset + size > len(blob):
            pos = pcx_pos + 5
            continue

        # Extract data
        data = blob[offset:offset+size]

        # Verify it starts with PCX magic bytes (0x0A = ZSoft PCX format)
        if len(data) > 0 and data[0] == 0x0A:
            entries.append(GXLEntry(name=name, offset=offset, size=size, data=data))

        # Move past this entry
        pos = data_pos + 8

    return entries
