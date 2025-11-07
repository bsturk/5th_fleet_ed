#!/usr/bin/env python3
"""
Analyze objective scripts for scenarios 5-23 to understand their structure
and why they aren't being colored correctly.
"""

from pathlib import Path
from editor.data import ScenarioFile
from editor.objectives import parse_objective_script

def main():
    scenario_file_path = Path("game/SCENARIO.DAT")
    scenario_file = ScenarioFile.load(scenario_file_path)

    print("Analyzing scenarios 5-23 objective scripts\n")
    print("=" * 100)

    for idx in range(5, 24):
        if idx >= len(scenario_file.records):
            break

        scenario = scenario_file.records[idx]

        # Get scenario title from metadata
        title = scenario.metadata_entries[0].text if scenario.metadata_entries else "Unknown"

        print(f"\n{'=' * 100}")
        print(f"SCENARIO {idx}: {title}")
        print(f"{'=' * 100}")

        # Parse the objective script
        try:
            objectives = parse_objective_script(scenario.trailing_bytes)

            # Load the opcode map from editor.objectives
            from editor.objectives import OPCODE_MAP

            print(f"\nObjective Script ({len(objectives)} opcodes):")
            print("-" * 100)
            for i, (opcode_val, operand_val) in enumerate(objectives):
                if opcode_val in OPCODE_MAP:
                    mnemonic, param_type, desc = OPCODE_MAP[opcode_val]
                else:
                    mnemonic = f"UNKNOWN_0x{opcode_val:02x}"
                    desc = "Unknown opcode"

                print(f"  [{i}] 0x{opcode_val:02x}({operand_val:3d}) -> {mnemonic:20s} | {desc}")
        except Exception as e:
            print(f"  ERROR parsing objectives: {e}")

        # Show objectives text from scenario
        print(f"\nObjectives Text from SCENARIO.DAT:")
        print("-" * 100)
        if scenario.objectives:
            lines = scenario.objectives.split('\n')
            for line in lines[:15]:  # Show first 15 lines
                print(f"  {line}")
            if len(lines) > 15:
                print(f"  ... ({len(lines) - 15} more lines)")
        else:
            print("  (No objectives text)")

        # Check for player section markers
        has_player_section_0d = any(opcode == 0x01 and operand == 0x0d for opcode, operand in objectives)
        has_player_section_00 = any(opcode == 0x01 and operand == 0x00 for opcode, operand in objectives)
        has_player_section_c0 = any(opcode == 0x01 and operand == 0xc0 for opcode, operand in objectives)

        print(f"\nPlayer Section Markers:")
        print(f"  PLAYER_SECTION(0x0d) [Green]: {has_player_section_0d}")
        print(f"  PLAYER_SECTION(0x00) [Red]:   {has_player_section_00}")
        print(f"  PLAYER_SECTION(0xc0) [Campaign]: {has_player_section_c0}")

        if not (has_player_section_0d or has_player_section_00 or has_player_section_c0):
            print("  ⚠️  NO PLAYER SECTION MARKERS FOUND - This scenario uses implicit player assignment")

if __name__ == "__main__":
    main()
