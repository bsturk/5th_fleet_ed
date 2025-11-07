#!/usr/bin/env python3
"""
Test script to verify player objectives parsing for scenarios 5-23.
"""

from pathlib import Path
from editor.data import ScenarioFile
import re

def parse_player_objectives(objectives_text: str) -> dict:
    """Extract Green and Red player objectives from narrative text."""
    green_objectives = ""
    red_objectives = ""

    # Look for "Green Player:" and "Red Player:" markers (case-insensitive)
    green_match = re.search(
        r'Green\s+Player:\s*(.+?)(?=Red\s+Player:|$)',
        objectives_text,
        re.DOTALL | re.IGNORECASE
    )
    red_match = re.search(
        r'Red\s+Player:\s*(.+?)$',
        objectives_text,
        re.DOTALL | re.IGNORECASE
    )

    if green_match:
        green_objectives = green_match.group(1).strip()
    if red_match:
        red_objectives = red_match.group(1).strip()

    return {"green": green_objectives, "red": red_objectives}

def main():
    scenario_file_path = Path("game/SCENARIO.DAT")
    scenario_file = ScenarioFile.load(scenario_file_path)

    print("Testing Player Objectives Parsing\n")
    print("=" * 80)

    # Test scenarios 5-10 (representative sample)
    for idx in range(5, 11):
        if idx >= len(scenario_file.records):
            break

        scenario = scenario_file.records[idx]
        title = scenario.metadata_entries[0].text if scenario.metadata_entries else "Unknown"

        print(f"\n{'=' * 80}")
        print(f"SCENARIO {idx}: {title}")
        print(f"{'=' * 80}")

        if scenario.objectives and scenario.objectives.strip():
            player_objs = parse_player_objectives(scenario.objectives)

            print("\n✅ GREEN PLAYER OBJECTIVES:")
            print("-" * 80)
            if player_objs["green"]:
                print(player_objs["green"])
            else:
                print("  (None found)")

            print("\n✅ RED PLAYER OBJECTIVES:")
            print("-" * 80)
            if player_objs["red"]:
                print(player_objs["red"])
            else:
                print("  (None found)")

            # Verify both were found
            if player_objs["green"] and player_objs["red"]:
                print("\n✅ PARSING STATUS: SUCCESS - Both players' objectives extracted")
            elif player_objs["green"] or player_objs["red"]:
                print("\n⚠️  PARSING STATUS: PARTIAL - Only one player's objectives found")
            else:
                print("\n❌ PARSING STATUS: FAILED - No player objectives found")
                print("\n   Raw objectives text:")
                print("   " + scenario.objectives[:200].replace('\n', '\n   '))
        else:
            print("\n❌ No objectives text in scenario data")

if __name__ == "__main__":
    main()
