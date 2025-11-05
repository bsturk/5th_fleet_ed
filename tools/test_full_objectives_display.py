#!/usr/bin/env python3
"""
Test script to show the complete objectives display as it will appear in the editor.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from editor.data import ScenarioFile
from editor.objectives import parse_objective_script, OPCODE_MAP, SPECIAL_OPERANDS

def display_scenario_objectives(scenario_index: int = 0):
    """Display objectives as they will appear in the editor."""
    scenario_file = ScenarioFile.load(Path("game/SCENARIO.DAT"))

    if scenario_index >= len(scenario_file.records):
        print(f"ERROR: Scenario {scenario_index} not found")
        return

    record = scenario_file.records[scenario_index]

    print("=" * 80)
    print(f"SCENARIO {scenario_index + 1} - OBJECTIVES DISPLAY")
    print("=" * 80)
    print()

    # This is what will now be displayed in the Objectives tab
    print("═══════════════════════════════════════════════════")
    print("SCENARIO OBJECTIVES (Descriptive Text)")
    print("═══════════════════════════════════════════════════")
    print()
    print(record.objectives.strip())
    print()
    print("═══════════════════════════════════════════════════")
    print("BINARY OPCODE IMPLEMENTATION")
    print("═══════════════════════════════════════════════════")
    print()

    # Parse and display opcodes
    script = parse_objective_script(record.trailing_bytes)

    if not script:
        print("No objective script found")
        return

    # Display turn limit
    if len(record.trailing_bytes) > 45:
        turn_count = record.trailing_bytes[45]
        print(f"**Turn Limit: {turn_count} turns**")
        print()

    # Display opcodes
    for opcode, operand in script:
        if opcode == 0x01:  # TURNS - player delimiter
            if operand == 0x0d:
                print()
                print("═══ GREEN PLAYER OBJECTIVES ═══")
            elif operand == 0x00:
                print()
                print("═══ RED PLAYER OBJECTIVES ═══")

        elif opcode == 0x05:  # SPECIAL_RULE
            if operand == 0xfe:
                print("• Special: No cruise missile attacks allowed")
            elif operand == 0x06:
                print("• Special: Convoy delivery mission active")

        elif opcode == 0x0e:  # BASE_RULE
            # In the actual editor, this will try to look up the base name
            print(f"• Airfield/base objective (base ID: {operand})")
            print("  [Note: Editor will look up base name from MAP.DAT pointer section 9]")

        elif opcode == 0x03:  # SCORE
            print(f"• Victory points objective (ref: {operand})")
            print("  [This represents: 'Destroy as many enemy units as possible']")

        elif opcode == 0x00:  # END
            if operand > 0:
                print(f"• Victory check: region {operand}")
                print("  [Note: Editor will look up region name from MAP.DAT]")

        elif opcode in OPCODE_MAP:
            mnemonic, _, description = OPCODE_MAP[opcode]
            print(f"• {description} (param: {operand})")

    print()
    print("=" * 80)

if __name__ == "__main__":
    display_scenario_objectives(0)
