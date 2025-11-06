#!/usr/bin/env python3
"""Check turn counts and player section markers across ALL scenarios."""

import struct
from pathlib import Path
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

def analyze_all_scenarios():
    """Check turn counts and markers for all 24 scenarios."""
    print(f"{'Scenario':<10} {'Turn Count':<12} {'Has 0x0d':<10} {'Has 0x00':<10} {'Has 0xc0':<10} {'Script Len':<12}")
    print(f"{'='*10} {'='*12} {'='*10} {'='*10} {'='*10} {'='*12}")

    for i in range(24):
        data = get_scenario(i)
        script = parse_objective_script(data)

        # Get turn count from trailing_bytes[0]
        turn_count = data[5761]

        # Check for player markers
        has_0d = any(op == 0x01 and oper == 0x0d for op, oper in script)
        has_00 = any(op == 0x01 and oper == 0x00 for op, oper in script)
        has_c0 = any(op == 0x01 and oper == 0xc0 for op, oper in script)

        print(f"{i:<10} {turn_count:<12} {str(has_0d):<10} {str(has_00):<10} {str(has_c0):<10} {len(script):<12}")

    print(f"\n{'='*80}")
    print("PATTERN ANALYSIS:")
    print(f"{'='*80}")

    # Re-run with grouping
    with_markers = []
    without_markers = []
    with_c0 = []

    for i in range(24):
        data = get_scenario(i)
        script = parse_objective_script(data)

        has_0d = any(op == 0x01 and oper == 0x0d for op, oper in script)
        has_00 = any(op == 0x01 and oper == 0x00 for op, oper in script)
        has_c0 = any(op == 0x01 and oper == 0xc0 for op, oper in script)

        if has_c0:
            with_c0.append(i)
        elif has_0d or has_00:
            with_markers.append(i)
        else:
            without_markers.append(i)

    print(f"\nScenarios WITH standard markers (0x0d/0x00): {with_markers}")
    print(f"  Count: {len(with_markers)}")

    print(f"\nScenarios WITHOUT any player markers: {without_markers}")
    print(f"  Count: {len(without_markers)}")

    print(f"\nScenarios WITH campaign marker (0xc0): {with_c0}")
    print(f"  Count: {len(with_c0)}")

if __name__ == "__main__":
    analyze_all_scenarios()
