#!/usr/bin/env python3
"""Deep dive into scenarios 8, 9, 14 - comparing objective scripts with actual objectives."""

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

# From scenarios.md
ACTUAL_OBJECTIVES = {
    8: {
        "green": [
            "US fast convoy (FC), maritime prepositioning (MPS), and all amphibious assault units (LHD, LPD, LSD, and LHA) must reach Bandar 'Abbas",
            "Failing that, they must attempt to reach Masirah (in Oman), Muscat (in the United Arab Emirates), or Jiwani (in Pakistan)",
            "Destroy as many Russian units as possible"
        ],
        "red": [
            "Destroy as many US and British units as possible"
        ]
    },
    9: {
        "green": [
            "All US amphibious assault units (LHD, LPD, LSD, but not the LHA *Tarawa*) and maritime prepositioning ships (MPS) must reach Socotra island",
            "Failing that, they must reach Raysut or Salalah",
            "US full tanker units (FT) must reach the Strait of Malacca",
            "US empty tanker (ET) units must reach Kuwait, Ras al Mishab, Al Jubayl, Ras Tannurah, or Al Manamah",
            "US fast convoy (FC) and slow convoy (SC) units must reach Diego Garcia",
            "Destroy as many Russian units as possible"
        ],
        "red": [
            "Destroy as many US units as possible"
        ]
    }
}

def analyze_scenario_deep(scenario_num):
    """Deep analysis comparing opcode script with actual objectives."""
    data = get_scenario(scenario_num)
    script = parse_objective_script(data)
    scenario_name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')
    turn_count = data[5761]

    print(f"\n{'='*80}")
    print(f"DEEP DIVE: SCENARIO {scenario_num} (zero-based)")
    print(f"Name: {scenario_name}")
    print(f"Turn Count: {turn_count}")
    print(f"{'='*80}")

    print(f"\nOBJECTIVE SCRIPT ({len(script)} opcodes):")
    for idx, (opcode, operand) in enumerate(script):
        mnemonic = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[0]
        desc = OPCODE_MAP.get(opcode, ("UNKNOWN", "?", "?"))[2]
        print(f"  [{idx}] 0x{opcode:02x}({opcode:3d}) = {operand:3d} (0x{operand:02x}) {mnemonic:20s} - {desc}")

    if scenario_num in ACTUAL_OBJECTIVES:
        print(f"\nACTUAL OBJECTIVES FROM SCENARIOS.MD:")
        print(f"  Green Player:")
        for obj in ACTUAL_OBJECTIVES[scenario_num]["green"]:
            print(f"    - {obj}")
        print(f"  Red Player:")
        for obj in ACTUAL_OBJECTIVES[scenario_num]["red"]:
            print(f"    - {obj}")

    print(f"\nQUESTION: How do these opcodes encode the Green vs Red objectives?")
    print(f"HYPOTHESIS to test:")
    print(f"  1. Maybe the END(region) values indicate which player?")
    print(f"  2. Maybe the objectives apply to BOTH players (no separation)?")
    print(f"  3. Maybe the narrative text is the real source and opcodes are simplified?")
    print(f"  4. Maybe these scenarios use implicit player assignment based on unit ownership?")

def main():
    for scenario_num in [8, 9]:
        analyze_scenario_deep(scenario_num)

    print(f"\n\n{'='*80}")
    print("CRITICAL ANALYSIS")
    print(f"{'='*80}")
    print("""
Looking at scenarios 8 and 9:
- Both have END(109) in first position (109 = 0x6d = SUPPLY_LIMIT opcode)
- No PLAYER_SECTION markers
- Turn count = 0 (special)

Comparing with standard scenarios (0-4):
- They have PLAYER_SECTION(0x0d) for Green, PLAYER_SECTION(0x00) for Red
- Objectives are explicitly separated by these markers
- Turn count > 0

ULTRATHINK QUESTION:
If scenarios 8 and 9 have both Green and Red objectives (per scenarios.md),
but NO player section markers in the opcode script...

WHERE ARE THE GREEN/RED OBJECTIVES ENCODED?

Possibilities:
1. The objectives are NOT in the opcode script - they're hardcoded in the game engine
2. The objectives are determined by unit ownership (Green owns FC/MPS, Red owns whatever they have)
3. The END(region) values somehow encode player assignments
4. The opcodes define SHARED objectives that apply differently based on perspective
5. The narrative text in the scenario data is parsed by the game (not just opcodes)

Let's check the narrative text in the scenario data...
""")

if __name__ == "__main__":
    main()
