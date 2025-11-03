#!/usr/bin/env python3
"""
Complete objective script decoder for 5th Fleet scenarios.

Maps opcodes to their handlers and decodes victory conditions.
"""

import struct
import sys
from pathlib import Path
from collections import defaultdict

# Opcode mnemonics discovered from Fleet.exe at offset 0x5c22b
# Format: opcode_number -> (mnemonic, arity, description)
OPCODE_MAP = {
    # These are initial guesses based on patterns and notes
    0x00: ("END", 1, "End of script or end condition check"),
    0x01: ("TURNS", 1, "Set turn limit"),
    0x03: ("SCORE", 1, "Set victory point requirement"),
    0x04: ("CONVOY_RULE", 1, "Convoy delivery rule"),
    0x05: ("SPECIAL_RULE", 1, "Special scenario rule"),
    0x06: ("SHIP_DEST", 1, "Ship must reach destination"),
    0x09: ("ZONE_CONTROL", 1, "Zone control objective"),
    0x0a: ("ZONE_CHECK", 1, "Check zone occupation"),
    0x0c: ("TASK_FORCE", 1, "Task force objective"),
    0x0e: ("BASE_RULE", 1, "Base/airfield objective"),
    0x13: ("PORT_RESTRICT", 1, "Port restriction"),
    0x18: ("CONVOY_PORT", 1, "Convoy destination port"),
    0x1d: ("SHIP_OBJECTIVE", 1, "Ship-specific objective"),
    0x29: ("REGION_RULE", 1, "Region-based rule"),
    0x2d: ("ALT_TURNS", 1, "Alternate turn limit encoding"),
    0x3a: ("CONVOY_FALLBACK", 1, "Convoy fallback port"),
    0x3c: ("DELIVERY_CHECK", 1, "Delivery success check"),
    0x3d: ("PORT_LIST", 1, "Port list reference"),
    0x41: ("FLEET_POSITION", 1, "Fleet positioning requirement"),
    0x6d: ("SUPPLY_LIMIT", 1, "Supply/replenishment restriction"),
    0xbb: ("ZONE_ENTRY", 1, "Zone entry requirement"),
}

# Special operand values
SPECIAL_OPERANDS = {
    0xfe: "PROHIBITED",  # e.g., no cruise missiles
    0xff: "UNLIMITED",
}


def parse_scenario_script(block_data):
    """
    Extract and parse the objective script from a scenario block.

    The script is stored at the end of the block after the difficulty string.
    Format: sequence of little-endian words where high byte = opcode, low byte = operand.
    """
    # Find the difficulty marker ("Low", "Medium", "High")
    difficulty_patterns = [b'Low\x00', b'Medium\x00', b'High\x00']
    script_start = -1

    for pattern in difficulty_patterns:
        idx = block_data.rfind(pattern)
        if idx != -1:
            script_start = idx + len(pattern)
            break

    if script_start == -1:
        # No difficulty found, look for last string before binary data
        # Search backwards for a run of nulls followed by text
        for i in range(len(block_data) - 50, max(len(block_data) - 200, 0), -1):
            if block_data[i] == 0 and block_data[i+1] != 0:
                script_start = i + 1
                break

    if script_start == -1 or script_start >= len(block_data) - 4:
        return []

    # Parse the script as little-endian words
    script_data = block_data[script_start:]
    opcodes = []

    for i in range(0, min(len(script_data) - 1, 32), 2):  # Max ~16 opcodes
        word = struct.unpack_from("<H", script_data, i)[0]
        if word == 0:  # End marker
            break

        opcode = (word >> 8) & 0xFF  # High byte
        operand = word & 0xFF         # Low byte
        opcodes.append((opcode, operand))

    return opcodes


def decode_opcode(opcode, operand, context=None):
    """Decode a single opcode into human-readable form."""
    if opcode in OPCODE_MAP:
        mnemonic, _, description = OPCODE_MAP[opcode]
        operand_str = SPECIAL_OPERANDS.get(operand, f"{operand}")
        return f"{mnemonic}({operand_str})", description
    else:
        return f"OP_{opcode:02x}({operand})", "Unknown opcode"


def decode_script(script, scenario_title=""):
    """Decode an entire objective script into objectives."""
    lines = []
    lines.append(f"Scenario: {scenario_title}")
    lines.append("=" * 70)

    if not script:
        lines.append("  No objective script found")
        return "\n".join(lines)

    lines.append("\nRaw opcodes:")
    for opcode, operand in script:
        code_str, description = decode_opcode(opcode, operand)
        lines.append(f"  0x{opcode:02x}({operand:3}) -> {code_str:20} // {description}")

    # Attempt high-level interpretation
    lines.append("\nInterpreted objectives:")

    i = 0
    while i < len(script):
        opcode, operand = script[i]

        if opcode == 0x01:  # Turn limit
            if operand == 0xfe:
                lines.append("  • Duration: Until objectives complete")
            else:
                lines.append(f"  • Turn limit: {operand} turns")

        elif opcode == 0x05:  # Special rule
            if operand == 0xfe:
                lines.append("  • Special: No cruise missile attacks allowed")
            elif operand == 0x00:
                lines.append("  • Special: Standard engagement rules")
            elif operand == 0x06:
                lines.append("  • Special: Convoy delivery mission active")

        elif opcode == 0x0c:  # Task force objective
            lines.append(f"  • Task force must survive/reach destination (ref: {operand})")

        elif opcode == 0x0a:  # Zone control
            lines.append(f"  • Control or occupy zone (index: {operand})")

        elif opcode == 0x00:  # End/check
            if operand > 0:
                lines.append(f"  • Victory check: Region {operand}")

        elif opcode == 0x03:  # Score
            lines.append(f"  • Score objective (ref: {operand})")

        elif opcode == 0x09:  # Zone control
            lines.append(f"  • Zone control required (index: {operand})")

        elif opcode == 0x06:  # Ship destination
            lines.append(f"  • Ships must reach port (index: {operand})")

        elif opcode == 0x0e:  # Base objective
            lines.append(f"  • Airfield/base objective (ref: {operand})")

        elif opcode == 0x18:  # Convoy port
            lines.append(f"  • Convoy destination (port ref: {operand})")

        elif opcode in OPCODE_MAP:
            _, _, desc = OPCODE_MAP[opcode]
            lines.append(f"  • {desc} (param: {operand})")
        else:
            lines.append(f"  • Unknown: opcode 0x{opcode:02x}, operand {operand}")

        i += 1

    return "\n".join(lines)


def load_all_scenarios(scenario_path):
    """Load all scenario records from SCENARIO.DAT."""
    data = scenario_path.read_bytes()
    count = struct.unpack_from("<H", data, 0)[0]

    payload = data[2:]
    block_len = len(payload) // count

    scenarios = []
    for idx in range(count):
        start = idx * block_len
        block = payload[start : start + block_len]

        # Extract title (first metadata string)
        title = f"Scenario {idx}"
        try:
            # Look for the title after "FORCES" and "OBJECTIVES"
            meta_start = max(
                block.find(b'OBJECTIVES'),
                block.find(b'FORCES')
            ) + 200

            if meta_start > 200:
                for i in range(meta_start, min(meta_start + 1000, len(block))):
                    if block[i] >= 0x20 and block[i] < 0x7F:
                        end = block.find(b'\x00', i)
                        if end > i:
                            candidate = block[i:end].decode('latin1', errors='ignore').strip()
                            if len(candidate) > 5 and ' ' in candidate:
                                title = candidate
                                break
        except:
            pass

        script = parse_scenario_script(block)

        scenarios.append({
            'index': idx,
            'title': title[:60],
            'script': script,
            'raw_tail': block[-50:].hex()
        })

    return scenarios


def analyze_opcode_usage(scenarios):
    """Analyze opcode patterns across all scenarios."""
    opcode_freq = defaultdict(int)
    opcode_operands = defaultdict(list)
    position_map = defaultdict(lambda: defaultdict(int))

    for scenario in scenarios:
        for pos, (opcode, operand) in enumerate(scenario['script']):
            opcode_freq[opcode] += 1
            opcode_operands[opcode].append(operand)
            position_map[pos][opcode] += 1

    return {
        'frequency': opcode_freq,
        'operands': opcode_operands,
        'positions': position_map
    }


def main():
    game_dir = Path("game")
    scenario_path = game_dir / "SCENARIO.DAT"

    if not scenario_path.exists():
        print(f"Error: {scenario_path} not found", file=sys.stderr)
        return 1

    print("=" * 80)
    print("5TH FLEET OBJECTIVE DECODER")
    print("=" * 80)
    print()

    # Load all scenarios
    scenarios = load_all_scenarios(scenario_path)

    # Decode each one
    for scenario in scenarios[:10]:  # First 10 scenarios
        if scenario['script']:
            print(decode_script(scenario['script'], scenario['title']))
            print()

    # Statistical analysis
    print("\n" + "=" * 80)
    print("OPCODE STATISTICS")
    print("=" * 80)

    stats = analyze_opcode_usage(scenarios)

    print("\nMost common opcodes:")
    for opcode, count in sorted(stats['frequency'].items(), key=lambda x: -x[1])[:15]:
        operands = stats['operands'][opcode]
        operand_set = set(operands)
        if opcode in OPCODE_MAP:
            name, _, _ = OPCODE_MAP[opcode]
            print(f"  0x{opcode:02x} {name:15} : {count:2}× - operands: {sorted(operand_set)}")
        else:
            print(f"  0x{opcode:02x} {'UNKNOWN':15} : {count:2}× - operands: {sorted(operand_set)}")

    print("\nOpcode by position:")
    for pos in sorted(stats['positions'].keys())[:8]:
        opcodes = stats['positions'][pos]
        print(f"  Position {pos}: {dict(opcodes)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
