#!/usr/bin/env python3
"""Deep investigation of scenarios 8, 9, and 14 that have unusual player section handling."""

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

def analyze_special_scenario(scenario_num):
    """Detailed analysis of a specific scenario."""
    data = get_scenario(scenario_num)
    script = parse_objective_script(data)

    # Get scenario name and metadata
    scenario_name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')
    turn_count = data[5761]  # trailing_bytes[0]

    print(f"\n{'='*80}")
    print(f"SCENARIO {scenario_num}: {scenario_name}")
    print(f"{'='*80}")
    print(f"Turn count: {turn_count}")
    print(f"Total opcodes: {len(script)}")
    print(f"\nObjective Script Structure:")
    print(f"{'='*80}")

    # Analyze structure
    has_player_section_0d = False
    has_player_section_00 = False
    has_player_section_c0 = False
    has_end_delimiter = False

    for pos, (opcode, operand) in enumerate(script):
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]
        desc = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[2]

        # Check for player section markers
        marker = ""
        if opcode == 0x01:  # PLAYER_SECTION
            if operand == 0x0d:
                has_player_section_0d = True
                marker = " ← GREEN PLAYER SECTION MARKER"
            elif operand == 0x00:
                has_player_section_00 = True
                marker = " ← RED PLAYER SECTION MARKER"
            elif operand == 0xc0:  # 192
                has_player_section_c0 = True
                marker = " ← CAMPAIGN MODE MARKER (0xc0)"
            else:
                marker = f" ← UNKNOWN PLAYER_SECTION OPERAND: {operand}"
        elif opcode == 0x00 and operand == 0:
            has_end_delimiter = True
            marker = " ← SECTION DELIMITER (END with operand 0)"
        elif opcode == 0x00 and pos == 0:
            marker = f" ← SPECIAL: END in FIRST POSITION (operand={operand}=0x{operand:02x})"
        elif pos == 0:
            marker = " ← FIRST POSITION (scenario initialization)"
        elif pos == len(script) - 1:
            marker = " ← LAST POSITION (victory modifier)"

        print(f"[{pos:2d}] 0x{opcode:02x}({opcode:3d}) operand={operand:3d} (0x{operand:02x}) "
              f"[{mnemonic:20s}]{marker}")

    print(f"\n{'='*80}")
    print(f"STRUCTURE ANALYSIS:")
    print(f"{'='*80}")
    print(f"Has GREEN marker (0x01/0x0d):      {has_player_section_0d}")
    print(f"Has RED marker (0x01/0x00):        {has_player_section_00}")
    print(f"Has CAMPAIGN marker (0x01/0xc0):   {has_player_section_c0}")
    print(f"Has END(0) section delimiter:      {has_end_delimiter}")

    # Determine scenario type
    print(f"\nSCENARIO TYPE:")
    if has_player_section_0d or has_player_section_00:
        print(f"  → STANDARD TWO-PLAYER SCENARIO")
        if has_player_section_0d and not has_player_section_00:
            print(f"     WARNING: Has Green marker but no Red marker!")
        elif has_player_section_00 and not has_player_section_0d:
            print(f"     WARNING: Has Red marker but no Green marker!")
    elif has_player_section_c0:
        print(f"  → CAMPAIGN MODE SCENARIO (operand 0xc0 = 192)")
        print(f"     This is likely a single-player campaign scenario")
        print(f"     The 0xc0 marker indicates special campaign rules")
    else:
        print(f"  → NO PLAYER SECTION MARKERS FOUND")
        print(f"     This is likely a RED-ONLY or SINGLE-PLAYER scenario")
        print(f"     Player plays as Red (defender) with specific objectives")

    # Special case for END(109)
    if len(script) > 0 and script[0][0] == 0x00:
        first_operand = script[0][1]
        if first_operand == 109:
            print(f"\n  SPECIAL INITIALIZATION: END(109) in first position")
            print(f"     Operand 109 = 0x6d = SUPPLY_LIMIT opcode number!")
            print(f"     This might be a reference/pointer to supply system")
            print(f"     OR it could indicate a special scenario mode")
        elif first_operand == 25:
            print(f"\n  SPECIAL INITIALIZATION: END(25) found")
            print(f"     Operand 25 might be a region index or mode flag")

    return script

def compare_scenarios():
    """Compare the three problem scenarios."""
    print("\n" + "="*80)
    print("COMPARATIVE ANALYSIS OF SCENARIOS 8, 9, and 14")
    print("="*80)

    for scenario_num in [8, 9, 14]:
        analyze_special_scenario(scenario_num)

    print("\n" + "="*80)
    print("RECOMMENDATIONS FOR EDITOR:")
    print("="*80)
    print("""
1. SCENARIO 8 & 9 (No player section markers):
   - These are single-player scenarios (player controls Red/defender)
   - Should display with NEUTRAL or SINGLE color (not split Green/Red)
   - All objectives should be shown as one unified list
   - Consider displaying "Single Player Mode" label

2. SCENARIO 14 (PLAYER_SECTION with operand 0xc0):
   - This is a CAMPAIGN MODE scenario
   - Operand 0xc0 (192 decimal) is a special campaign marker
   - Should be colored differently than standard Green/Red
   - Consider using YELLOW, ORANGE, or CAMPAIGN-specific color
   - Label it as "Campaign Mode" in the UI

3. General Pattern Recognition:
   - Standard: PLAYER_SECTION(0x0d) followed by PLAYER_SECTION(0x00)
   - Campaign: PLAYER_SECTION(0xc0) - single unified objectives
   - Single-player: No PLAYER_SECTION at all - unified objectives

4. Coloring Logic Update:
   if has PLAYER_SECTION(0x0d) and PLAYER_SECTION(0x00):
       color as GREEN and RED sections
   elif has PLAYER_SECTION(0xc0):
       color as CAMPAIGN (yellow/orange)
   else:
       color as SINGLE-PLAYER (neutral gray or unified color)
""")

if __name__ == "__main__":
    compare_scenarios()
