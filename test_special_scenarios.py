#!/usr/bin/env python3
"""Test the coloring logic for special scenarios 8, 9, and 14."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from editor.objectives import parse_objective_script, OPCODE_MAP

SCENARIO_DAT = Path(__file__).parent / "game" / "SCENARIO.DAT"
SCENARIO_SIZE = 5883

def get_scenario(index):
    """Read a specific scenario from SCENARIO.DAT."""
    with open(SCENARIO_DAT, 'rb') as f:
        f.seek(index * SCENARIO_SIZE)
        return f.read(SCENARIO_SIZE)

def test_coloring_logic(scenario_num):
    """Test the coloring logic for a specific scenario."""
    data = get_scenario(scenario_num)
    script = parse_objective_script(data)
    scenario_name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')

    print(f"\n{'='*80}")
    print(f"TESTING SCENARIO {scenario_num}: {scenario_name}")
    print(f"{'='*80}")

    # Replicate the editor's detection logic
    has_explicit_red_marker = any(op == 0x01 and oper == 0x00 for op, oper in script)
    has_explicit_green_marker = any(op == 0x01 and oper == 0x0d for op, oper in script)
    has_campaign_marker = any(op == 0x01 and oper == 0xc0 for op, oper in script)

    print(f"Detection Results:")
    print(f"  Green marker (0x01/0x0d):    {has_explicit_green_marker}")
    print(f"  Red marker (0x01/0x00):      {has_explicit_red_marker}")
    print(f"  Campaign marker (0x01/0xc0): {has_campaign_marker}")

    # Determine scenario type
    if has_campaign_marker:
        current_player = "Campaign"
        print(f"\n→ SCENARIO TYPE: CAMPAIGN MODE")
        print(f"   Initial coloring: {current_player}")
    elif not has_explicit_green_marker and not has_explicit_red_marker:
        current_player = "Neutral"
        print(f"\n→ SCENARIO TYPE: SINGLE-PLAYER (No player markers)")
        print(f"   Initial coloring: {current_player}")
    else:
        current_player = None
        print(f"\n→ SCENARIO TYPE: STANDARD TWO-PLAYER")
        print(f"   Initial coloring: None (will be set by markers)")

    print(f"\nOpcode-by-opcode coloring:")
    for idx, (opcode, operand) in enumerate(script):
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]

        # Simulate the editor's coloring logic
        if opcode == 0x01:  # PLAYER_SECTION
            if operand == 0x0d:
                current_player = "Green"
                color = "green_header_row"
            elif operand == 0x00:
                current_player = "Red"
                color = "red_header_row"
            elif operand == 0xc0:
                current_player = "Campaign"
                color = "campaign_header_row"
        else:
            if current_player == "Green":
                color = "green_row"
            elif current_player == "Red":
                color = "red_row"
            elif current_player == "Campaign":
                color = "campaign_row"
            elif current_player == "Neutral":
                color = "neutral_row"
            else:
                color = "no_color"

        print(f"  [{idx:2d}] 0x{opcode:02x}({opcode:3d}) = {operand:3d} [{mnemonic:20s}] → {color:20s}")

def main():
    """Test all three special scenarios."""
    for scenario_num in [8, 9, 14]:
        test_coloring_logic(scenario_num)

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print("""
Expected Results:
- Scenario 8:  All opcodes should be colored with 'neutral_row'
- Scenario 9:  All opcodes should be colored with 'neutral_row'
- Scenario 14: All opcodes should be colored with 'campaign_row'
               (except the PLAYER_SECTION marker which gets 'campaign_header_row')

These colors will make the scenarios visually distinct from standard two-player
scenarios and properly indicate their special nature.
""")

if __name__ == "__main__":
    main()
