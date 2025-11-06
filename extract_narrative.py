#!/usr/bin/env python3
"""Extract and analyze the narrative text from scenarios 8, 9, 14."""

import struct
from pathlib import Path

SCENARIO_DAT = Path(__file__).parent / "game" / "SCENARIO.DAT"
SCENARIO_SIZE = 5883

def get_scenario(index):
    """Read a specific scenario from SCENARIO.DAT."""
    with open(SCENARIO_DAT, 'rb') as f:
        f.seek(index * SCENARIO_SIZE)
        return f.read(SCENARIO_SIZE)

def extract_narrative(scenario_num):
    """Extract all narrative/text fields from a scenario."""
    data = get_scenario(scenario_num)

    print(f"\n{'='*80}")
    print(f"SCENARIO {scenario_num} - NARRATIVE TEXT EXTRACTION")
    print(f"{'='*80}")

    # Field 1: Scenario name (bytes 0-30, null-terminated)
    name = data[0:31].decode('ascii', errors='ignore').rstrip('\x00')
    print(f"\nField 1 - Scenario Name (bytes 0-30):")
    print(f"  '{name}'")

    # Field 2: Unknown field (bytes 31-62, null-terminated)
    field2 = data[31:63].decode('ascii', errors='ignore').rstrip('\x00')
    print(f"\nField 2 - Unknown (bytes 31-62):")
    print(f"  '{field2}'")

    # Field 3: Unknown field (bytes 63-94, null-terminated)
    field3 = data[63:95].decode('ascii', errors='ignore').rstrip('\x00')
    print(f"\nField 3 - Unknown (bytes 63-94):")
    print(f"  '{field3}'")

    # Trailing bytes section (bytes 5761-5883 = 122 bytes)
    # First byte is turn count
    turn_count = data[5761]
    print(f"\nTurn count (byte 5761): {turn_count}")

    # Difficulty string (bytes 5762-5800, null-terminated)
    difficulty = data[5762:5801].decode('ascii', errors='ignore').rstrip('\x00')
    print(f"\nDifficulty string (bytes 5762-5800):")
    print(f"  '{difficulty}'")

    # Look for any other text in the data
    print(f"\nSearching for 'Green Player' and 'Red Player' strings:")
    text = data.decode('ascii', errors='ignore')
    if "Green Player" in text:
        idx = text.index("Green Player")
        print(f"  Found 'Green Player' at byte offset {idx}")
        print(f"  Context: ...{text[max(0,idx-20):idx+100]}...")
    if "Red Player" in text:
        idx = text.index("Red Player")
        print(f"  Found 'Red Player' at byte offset {idx}")
        print(f"  Context: ...{text[max(0,idx-20):idx+100]}...")

    # Also check for "Objective" strings
    if "Objective" in text:
        import re
        matches = [(m.start(), m.group()) for m in re.finditer(r'Objective[s]?:', text)]
        if matches:
            print(f"\nFound {len(matches)} 'Objective' markers:")
            for idx, match_text in matches:
                print(f"  At byte {idx}: ...{text[max(0,idx-10):idx+60]}...")

def main():
    for scenario_num in [0, 1, 8, 9, 14]:
        extract_narrative(scenario_num)
        print()

if __name__ == "__main__":
    main()
