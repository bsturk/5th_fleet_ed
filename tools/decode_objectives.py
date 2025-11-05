#!/usr/bin/env python3
"""
Complete objective script decoder for 5th Fleet scenarios.

Maps opcodes to their handlers and decodes victory conditions.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import struct
from collections import defaultdict

from editor.objectives import (
    OPCODE_MAP,
    SPECIAL_OPERANDS,
    parse_objective_script as shared_parse_objective_script,
)


def parse_scenario_script(block_data):
    """
    Extract and parse the objective script from a scenario block.

    The script is stored at the end of the block after the difficulty string.
    Format: sequence of little-endian words where high byte = opcode, low byte = operand.
    """
    return shared_parse_objective_script(block_data)


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
    current_player = None
    while i < len(script):
        opcode, operand = script[i]

        if opcode == 0x01:  # TURNS - player objective delimiter
            if operand == 0x0d:
                lines.append("")
                lines.append("GREEN PLAYER OBJECTIVES:")
                current_player = "Green"
            elif operand == 0x00:
                lines.append("")
                lines.append("RED PLAYER OBJECTIVES:")
                current_player = "Red"
            elif operand == 0xfe:
                lines.append("  • Duration: Until objectives complete")
            else:
                lines.append(f"  • Player objective delimiter: {operand}")

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
