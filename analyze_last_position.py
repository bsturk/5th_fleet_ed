#!/usr/bin/env python3
"""Analyze all opcodes that appear in last position (victory modifiers)."""

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

def analyze_last_position():
    """Analyze all opcodes appearing in last position."""
    last_pos_opcodes = defaultdict(list)

    for i in range(24):
        data = get_scenario(i)
        script = parse_objective_script(data)

        if script and len(script) > 0:
            last_opcode, last_operand = script[-1]
            last_pos_opcodes[(last_opcode, last_operand)].append(i)

    print("="*80)
    print("LAST POSITION OPCODES (Victory Modifiers)")
    print("="*80)

    for (opcode, operand), scenarios in sorted(last_pos_opcodes.items()):
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]
        print(f"\n0x{opcode:02x}({opcode:3d}) operand={operand:3d} (0x{operand:02x}) [{mnemonic}]")
        print(f"  Scenarios: {scenarios}")
        print(f"  Count: {len(scenarios)}")

        # Show full context for one scenario
        first_scenario = scenarios[0]
        data = get_scenario(first_scenario)
        script = parse_objective_script(data)

        print(f"\n  Full structure (scenario {first_scenario}, {len(script)} opcodes):")
        for pos, (op, oper) in enumerate(script):
            name = OPCODE_MAP.get(op, ("UNKNOWN", "?", "?"))[0]
            marker = ""
            if pos == 0:
                marker = " <-- FIRST (setup)"
            elif pos == len(script) - 1:
                marker = " <-- LAST (victory modifier)"
            elif op == 0x00 and oper == 0:
                marker = " <-- Section delimiter"
            elif op == 0x01 and oper in (0x00, 0x0d):
                marker = f" <-- Player section ({'Green' if oper == 0x0d else 'Red'})"

            print(f"    [{pos:2d}] 0x{op:02x}({op:3d}) = {oper:3d} (0x{oper:02x}) [{name:20s}]{marker}")

    # Group by opcode to see operand ranges
    print("\n" + "="*80)
    print("VICTORY MODIFIER OPCODES - OPERAND RANGES")
    print("="*80)

    opcode_operands = defaultdict(list)
    for (opcode, operand), scenarios in last_pos_opcodes.items():
        opcode_operands[opcode].append((operand, scenarios))

    for opcode in sorted(opcode_operands.keys()):
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]
        operands = opcode_operands[opcode]
        operand_values = [op for op, _ in operands]
        print(f"\n0x{opcode:02x} [{mnemonic}]:")
        print(f"  Operand range: {min(operand_values)} - {max(operand_values)}")
        print(f"  Operand values: {sorted(operand_values)}")

        # Count scenarios
        total_scenarios = sum(len(scens) for _, scens in operands)
        print(f"  Used in {total_scenarios} scenarios")

if __name__ == "__main__":
    analyze_last_position()
