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
    # Runtime objectives (0x00-0x0f): Evaluated during gameplay
    0x00: ("END", "Region/Marker", "Section delimiter (op=0) or region victory check (op>0)"),
    0x01: ("PLAYER_SECTION", "Side marker", "Player section delimiter: 0x0d=Green, 0x00=Red, 0xc0=Campaign"),
    0x02: ("ZONE_OBJECTIVE", "Zone idx", "Zone-based objective (middle pos) or victory modifier (last pos)"),
    0x03: ("SCORE", "VP threshold", "Victory point objective/threshold"),
    0x04: ("CONVOY_RULE", "Value", "Convoy delivery rule (middle) or victory parameter (last)"),
    0x05: ("SPECIAL_RULE", "Code", "Special rules: 0x00=flag, 0x06=convoy active, 0xfe=prohibited"),
    0x06: ("SHIP_DEST", "Port idx", "Ships must reach port (middle) or victory parameter (last)"),
    0x07: ("CAMPAIGN_INIT", "Region/Flag", "Campaign scenario setup: first=region init, middle=flag"),
    0x08: ("SCENARIO_FLAG", "Always 0", "Scenario configuration flag (operand always 0)"),
    0x09: ("ZONE_CONTROL", "Zone idx", "Zone control objective: 0=generic, N=zone, 0xfe=all"),
    0x0A: ("ZONE_CHECK", "Zone idx", "Zone status check: 0xfe=all zones"),
    0x0B: ("CAMPAIGN_FLAG", "Always 0", "Campaign mode flag (operand always 0)"),
    0x0C: ("TASK_FORCE", "TF ref", "Task force objective: 0xfe=all task forces"),
    0x0E: ("BASE_RULE", "Base idx", "Airfield/base control objective"),
    0x0F: ("SPECIAL_OBJ", "Value", "Special objective type (operand 0 or specific value)"),

    # Setup/initialization opcodes (0x10-0xbb): Processed during scenario load
    0x10: ("SCENARIO_INIT_10", "Value", "Scenario initialization (first pos, operand 12)"),
    0x11: ("SCENARIO_INIT_11", "Value", "Scenario initialization (first pos, operand 5)"),
    0x13: ("PORT_RESTRICT", "Flags", "Replenishment port restrictions (middle pos)"),
    0x14: ("SCENARIO_INIT_14", "Value", "Scenario/campaign initialization (first/middle pos)"),
    0x17: ("VICTORY_MOD_17", "VP value", "Victory modifier (last pos, operand 24)"),
    0x18: ("CONVOY_PORT", "Port idx", "Convoy destination port (first/middle pos)"),
    0x19: ("VICTORY_MOD_19", "VP value", "Victory modifier (last pos, operand 12)"),
    0x1D: ("SHIP_OBJECTIVE", "Ship type", "Ship-specific objective (middle pos)"),
    0x1E: ("VICTORY_MOD_1E", "VP value", "Victory modifier (last pos, operands 32-46)"),
    0x20: ("VICTORY_MOD_20", "VP value", "Victory modifier (last pos, operand 40)"),
    0x23: ("VICTORY_MOD_23", "VP value", "Victory modifier (middle/last pos, operand 0 or 23)"),
    0x26: ("VICTORY_MOD_26", "VP value", "Victory modifier (last pos, operand 32)"),
    0x29: ("REGION_RULE", "Region idx", "Region-based victory rule (middle pos)"),
    0x2B: ("VICTORY_MOD_2B", "VP value", "Victory modifier (last pos, operands 9-49)"),
    0x2D: ("ALT_TURNS", "Turn count", "Alternate turn limit (first pos, operand = turns)"),
    0x30: ("VICTORY_MOD_30", "VP value", "Victory modifier (last pos, operand 37)"),
    0x34: ("VICTORY_MOD_34", "VP value", "Victory modifier (last pos, operand 20)"),
    0x35: ("SETUP_PARAM", "Value", "Setup parameter (middle pos, operand 15)"),
    0x3A: ("CONVOY_FALLBACK", "List ref", "Fallback port list (middle/last pos)"),
    0x3C: ("DELIVERY_CHECK", "Flags", "Delivery success/failure check"),
    0x3D: ("PORT_LIST", "List idx", "Port list for multi-destination objectives"),
    0x41: ("FLEET_POSITION", "Value", "Fleet positioning requirement"),
    0x5A: ("SETUP_5A", "Value", "Setup opcode (middle pos, operand 10)"),
    0x5F: ("VICTORY_MOD_5F", "VP value", "Victory modifier (last pos, operand 56)"),
    0x6D: ("SUPPLY_LIMIT", "Port mask", "Supply port restrictions (first pos, operand 117=0x75)"),
    0x6E: ("SETUP_6E", "Value", "Setup opcode (middle pos, operand 14)"),
    0x86: ("VICTORY_MOD_86", "VP value", "Victory modifier (last pos, operand 98)"),
    0x96: ("SETUP_96", "Value", "Setup opcode (middle pos, operand 5)"),
    0xBB: ("ZONE_ENTRY", "Zone idx", "Zone entry requirement (middle pos)"),
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
