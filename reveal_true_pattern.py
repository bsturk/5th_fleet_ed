#!/usr/bin/env python3
"""Reveal the TRUE pattern across all scenarios."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from editor.objectives import parse_objective_script, OPCODE_MAP

SCENARIO_DAT = Path(__file__).parent / "game" / "SCENARIO.DAT"
SCENARIO_SIZE = 5883

def get_scenario(index):
    with open(SCENARIO_DAT, 'rb') as f:
        f.seek(index * SCENARIO_SIZE)
        return f.read(SCENARIO_SIZE)

print("="*100)
print("COMPREHENSIVE SCENARIO STRUCTURE ANALYSIS")
print("="*100)

print("\nGROUP 1: Scenarios WITH PLAYER_SECTION markers (0-4)")
print("-"*100)
for i in range(5):
    data = get_scenario(i)
    script = parse_objective_script(data)
    name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')

    print(f"\nScenario {i}: {name[:25]}...")
    for idx, (op, oper) in enumerate(script):
        mnem = OPCODE_MAP.get(op, ("UNK", "?", "?"))[0]
        print(f"  [{idx}] 0x{op:02x}({op:3d}) = {oper:3d}  {mnem:20s}")

print("\n" + "="*100)
print("\nGROUP 2: Scenarios WITHOUT markers, 4 opcodes (5-10, 15-20, 23)")
print("-"*100)
for i in [5, 6, 7, 10, 15, 16, 17, 18, 19, 20, 23]:
    data = get_scenario(i)
    script = parse_objective_script(data)
    name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')

    print(f"\nScenario {i}: {name[:25]}...")
    for idx, (op, oper) in enumerate(script):
        mnem = OPCODE_MAP.get(op, ("UNK", "?", "?"))[0]
        print(f"  [{idx}] 0x{op:02x}({op:3d}) = {oper:3d}  {mnem:20s}")

print("\n" + "="*100)
print("\nGROUP 3: Scenarios WITHOUT markers, 5-6 opcodes (8, 9, 11-13, 21-22)")
print("-"*100)
for i in [8, 9, 11, 12, 13, 21, 22]:
    data = get_scenario(i)
    script = parse_objective_script(data)
    name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')

    print(f"\nScenario {i}: {name[:25]}...")
    for idx, (op, oper) in enumerate(script):
        mnem = OPCODE_MAP.get(op, ("UNK", "?", "?"))[0]
        print(f"  [{idx}] 0x{op:02x}({op:3d}) = {oper:3d}  {mnem:20s}")

print("\n" + "="*100)
print("\nGROUP 4: Campaign marker scenario (14)")
print("-"*100)
data = get_scenario(14)
script = parse_objective_script(data)
name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')

print(f"\nScenario 14: {name[:25]}...")
for idx, (op, oper) in enumerate(script):
    mnem = OPCODE_MAP.get(op, ("UNK", "?", "?"))[0]
    print(f"  [{idx}] 0x{op:02x}({op:3d}) = {oper:3d}  {mnem:20s}")

print("\n" + "="*100)
print("KEY INSIGHT:")
print("="*100)
print("""
The objective opcodes don't always encode player-specific objectives!

- Group 1 (scenarios 0-4): Use PLAYER_SECTION to EXPLICITLY separate Green/Red objectives
- Groups 2-4 (scenarios 5-23): Do NOT separate objectives by player in opcodes

For groups 2-4, the game likely determines which objectives apply to which player through:
1. Unit ownership (Green owns US units, Red owns Russian units)
2. Scenario narrative text
3. Hardcoded game logic

The editor SHOULD NOT try to color scenarios 5-23 as Green/Red sections because
the opcodes don't encode that separation. Instead, display them as unified/neutral.
""")
