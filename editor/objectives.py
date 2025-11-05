from __future__ import annotations

import struct
from typing import Dict, List, Optional, Sequence, Tuple

DIFFICULTY_TOKENS: Sequence[bytes] = (
    b"ELow\x00",
    b"EMedium\x00",
    b"EHigh\x00",
    b"Low\x00",
    b"Medium\x00",
    b"High\x00",
)

# Objective script metadata shared across tools
MAX_SCRIPT_WORDS = 64

OPCODE_MAP: Dict[int, Tuple[str, str, str]] = {
    0x00: ("END", "Region index", "End-of-script / victory check for region"),
    0x01: ("TURNS", "Side marker", "Player objective delimiter (0x0d=Green, 0x00=Red)"),
    0x03: ("SCORE", "VP ref", "Victory point objective"),
    0x04: ("CONVOY_RULE", "Flags", "Convoy delivery rule flags"),
    0x05: ("SPECIAL_RULE", "Code", "0xfe=no cruise missiles, 0x06=convoy active"),
    0x06: ("SHIP_DEST", "Port idx", "Ships must reach port"),
    0x07: ("UNKNOWN_07", "?", "Unknown (used in setup)"),
    0x08: ("UNKNOWN_08", "?", "Unknown"),
    0x09: ("ZONE_CONTROL", "Zone idx", "Zone must be controlled/occupied"),
    0x0A: ("ZONE_CHECK", "Zone idx", "Check zone status"),
    0x0C: ("TASK_FORCE", "TF ref", "Task force objective"),
    0x0E: ("BASE_RULE", "Base idx", "Airfield/base objective"),
    0x0F: ("UNKNOWN_0F", "?", "Unknown"),
    0x13: ("PORT_RESTRICT", "Flags", "Replenishment port restrictions"),
    0x18: ("CONVOY_PORT", "Port idx", "Convoy destination port"),
    0x1D: ("SHIP_OBJECTIVE", "Ship type", "Ship-specific objective"),
    0x29: ("REGION_RULE", "Region idx", "Region-based victory rule"),
    0x2D: ("ALT_TURNS", "Turn count", "Alternate turn limit"),
    0x3A: ("CONVOY_FALLBACK", "List ref", "Fallback port list"),
    0x3C: ("DELIVERY_CHECK", "Flags", "Delivery success/failure check"),
    0x3D: ("PORT_LIST", "List idx", "Port list (multi-destination)"),
    0x41: ("FLEET_POSITION", "?", "Fleet positioning requirement"),
    0x6D: ("SUPPLY_LIMIT", "Port mask", "Supply port restrictions"),
    0xBB: ("ZONE_ENTRY", "Zone idx", "Zone entry requirement"),
}

SPECIAL_OPERANDS: Dict[int, str] = {
    0x00: "NONE/STANDARD",
    0xFE: "PROHIBITED/ALL",
    0xFF: "UNLIMITED",
}


def _locate_script_start(blob: bytes) -> Optional[int]:
    """Return the byte offset of the objective script within *blob*."""
    if not blob:
        return None

    for token in DIFFICULTY_TOKENS:
        idx = blob.rfind(token)
        if idx != -1:
            return idx + len(token)

    # Fallback: walk backwards looking for the last printable string preceded
    # by a NUL terminator and treat the script as starting immediately after it.
    search_floor = max(len(blob) - 200, 0)
    for i in range(len(blob) - 2, search_floor - 1, -1):
        if blob[i] == 0 and blob[i + 1] >= 0x20:
            return i + 1

    return None


def objective_script_bytes(blob: bytes) -> bytes:
    """Return the slice of *blob* that contains the objective script words."""
    start = _locate_script_start(blob)
    if start is None or start >= len(blob):
        return b""
    return blob[start:]


def parse_objective_script(blob: bytes) -> List[Tuple[int, int]]:
    """Parse objective script words into (opcode, operand) tuples."""
    script_data = objective_script_bytes(blob)
    if len(script_data) < 2:
        return []

    # Ensure we only read full words.
    if len(script_data) % 2 == 1:
        script_data = script_data[:-1]

    script: List[Tuple[int, int]] = []
    consecutive_zeros = 0
    limit = min(len(script_data), MAX_SCRIPT_WORDS * 2)
    for offset in range(0, limit, 2):
        word = struct.unpack_from("<H", script_data, offset)[0]

        # Count consecutive zeros - only stop after 2+ consecutive zeros
        # This allows END(0) opcode (0x0000) to be parsed as a section separator
        if word == 0:
            consecutive_zeros += 1
            if consecutive_zeros >= 2:
                break
        else:
            consecutive_zeros = 0

        opcode = (word >> 8) & 0xFF
        operand = word & 0xFF
        script.append((opcode, operand))

    return script
