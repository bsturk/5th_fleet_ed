#!/usr/bin/env python3
"""Analyze opcodes in middle positions to identify patterns."""

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

def analyze_middle_positions():
    """Analyze opcodes appearing in middle positions (not first/last)."""
    middle_opcodes = defaultdict(lambda: {"operands": defaultdict(int), "scenarios": []})

    for i in range(24):
        data = get_scenario(i)
        script = parse_objective_script(data)

        if len(script) > 2:
            # Analyze positions 1 through len-2 (middle positions)
            for pos in range(1, len(script) - 1):
                opcode, operand = script[pos]
                middle_opcodes[opcode]["operands"][operand] += 1
                if i not in middle_opcodes[opcode]["scenarios"]:
                    middle_opcodes[opcode]["scenarios"].append(i)

    print("="*80)
    print("MIDDLE POSITION OPCODES (positions 1 through len-2)")
    print("="*80)

    for opcode in sorted(middle_opcodes.keys()):
        info = middle_opcodes[opcode]
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]
        operand_counts = info["operands"]
        scenarios = info["scenarios"]

        print(f"\n0x{opcode:02x}({opcode:3d}) [{mnemonic}]")
        print(f"  Scenarios: {scenarios}")
        print(f"  Total occurrences: {sum(operand_counts.values())}")
        print(f"  Operand distribution:")
        for operand in sorted(operand_counts.keys()):
            count = operand_counts[operand]
            print(f"    operand={operand:3d} (0x{operand:02x}): {count} times")

        # Show example from first scenario
        first_scenario = scenarios[0]
        data = get_scenario(first_scenario)
        script = parse_objective_script(data)

        print(f"\n  Example context (scenario {first_scenario}):")
        for pos, (op, oper) in enumerate(script):
            name = OPCODE_MAP.get(op, ("UNKNOWN", "?", "?"))[0]
            marker = ""
            if op == opcode and pos > 0 and pos < len(script) - 1:
                marker = " <-- THIS OPCODE (middle position)"
            elif pos == 0:
                marker = " <-- first"
            elif pos == len(script) - 1:
                marker = " <-- last"

            print(f"    [{pos}] 0x{op:02x}({op:3d}) = {oper:3d} [{name:20s}]{marker}")

if __name__ == "__main__":
    analyze_middle_positions()
