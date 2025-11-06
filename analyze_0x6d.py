#!/usr/bin/env python3
"""Analyze scenarios that use opcode 0x6d(117) to understand the pattern."""

import struct
from pathlib import Path

# Import from editor
import sys
sys.path.insert(0, str(Path(__file__).parent))
from editor.objectives import parse_objective_script

SCENARIO_DAT = Path(__file__).parent / "game" / "SCENARIO.DAT"
SCENARIO_SIZE = 5883

def get_scenario(index):
    """Read a specific scenario from SCENARIO.DAT."""
    with open(SCENARIO_DAT, 'rb') as f:
        f.seek(index * SCENARIO_SIZE)
        return f.read(SCENARIO_SIZE)

def analyze_6d_scenarios():
    """Find and analyze all scenarios using opcode 0x6d(117)."""
    scenarios_with_6d = []

    for i in range(24):
        data = get_scenario(i)
        script = parse_objective_script(data)

        # Check if 0x6d appears
        if any(opcode == 0x6d for opcode, operand in script):
            scenarios_with_6d.append(i)

            print(f"\n{'='*70}")
            print(f"SCENARIO {i}")
            print(f"{'='*70}")

            # Print full script with position markers
            for pos, (opcode, operand) in enumerate(script):
                marker = ""
                if opcode == 0x6d:
                    marker = " <-- OPCODE 0x6D"
                elif pos == 0:
                    marker = " <-- FIRST POSITION"
                elif pos == len(script) - 1:
                    marker = " <-- LAST POSITION"

                print(f"  [{pos:2d}] 0x{opcode:02x}({opcode:3d}) operand={operand:3d} (0x{operand:02x}){marker}")

            # Look for the pattern around 0x6d
            for pos, (opcode, operand) in enumerate(script):
                if opcode == 0x6d:
                    print(f"\n  Context around 0x6d at position {pos}:")
                    start = max(0, pos - 2)
                    end = min(len(script), pos + 8)
                    for i in range(start, end):
                        op, oper = script[i]
                        prefix = "  >>> " if i == pos else "      "
                        print(f"{prefix}[{i}] 0x{op:02x}({op:3d}) = {oper:3d}")

    print(f"\n\nSCENARIOS WITH 0x6d: {scenarios_with_6d}")
    return scenarios_with_6d

if __name__ == "__main__":
    analyze_6d_scenarios()
