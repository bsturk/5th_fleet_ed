#!/usr/bin/env python3
"""Analyze all opcodes that appear in first position."""

import struct
from pathlib import Path
from collections import defaultdict

# Import from editor
import sys
sys.path.insert(0, str(Path(__file__).parent))
from editor.objectives import parse_objective_script, OPCODE_MAP

SCENARIO_DAT = Path(__file__).parent / "game" / "SCENARIO.DAT"
SCENARIO_SIZE = 5883

def get_scenario(index):
    """Read a specific scenario from SCENARIO.DAT."""
    with open(SCENARIO_DAT, 'rb') as f:
        f.seek(index * SCENARIO_SIZE)
        return f.read(SCENARIO_SIZE)

def analyze_first_position():
    """Analyze all opcodes appearing in first position."""
    first_pos_opcodes = defaultdict(list)

    for i in range(24):
        data = get_scenario(i)
        script = parse_objective_script(data)

        if script:
            first_opcode, first_operand = script[0]
            first_pos_opcodes[(first_opcode, first_operand)].append(i)

    print("="*80)
    print("FIRST POSITION OPCODES ACROSS ALL SCENARIOS")
    print("="*80)

    for (opcode, operand), scenarios in sorted(first_pos_opcodes.items()):
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]
        print(f"\n0x{opcode:02x}({opcode:3d}) operand={operand:3d} (0x{operand:02x}) [{mnemonic}]")
        print(f"  Scenarios: {scenarios}")
        print(f"  Count: {len(scenarios)}")

        # Show the structure of first scenario with this opcode
        first_scenario = scenarios[0]
        data = get_scenario(first_scenario)
        script = parse_objective_script(data)

        print(f"\n  Example structure (scenario {first_scenario}):")
        for pos in range(min(10, len(script))):
            op, oper = script[pos]
            name = OPCODE_MAP.get(op, ("UNKNOWN", "?", "?"))[0]
            marker = " <-- FIRST" if pos == 0 else (" <-- LAST" if pos == len(script) - 1 else "")
            print(f"    [{pos:2d}] 0x{op:02x}({op:3d}) = {oper:3d} [{name}]{marker}")

        # Count total opcodes in this scenario
        print(f"  Total opcodes in scenario {first_scenario}: {len(script)}")

if __name__ == "__main__":
    analyze_first_position()
