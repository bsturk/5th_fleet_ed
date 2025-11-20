#!/usr/bin/env python3
"""Check which side values are actually used in all scenarios."""

import struct
from pathlib import Path
from collections import Counter

def analyze_scenario_sides(dat_path):
    """Analyze side values in a scenario DAT file."""
    data = Path(dat_path).read_bytes()

    # Read region count
    region_count = struct.unpack_from("<H", data, 0)[0]

    # Skip to pointer table
    offset = 2 + (region_count * 65)

    # Read pointer table
    pointer_table = []
    for i in range(16):
        ptr_offset = struct.unpack_from("<H", data, offset + i*4)[0]
        ptr_size = struct.unpack_from("<H", data, offset + i*4 + 2)[0]
        pointer_table.append((ptr_offset, ptr_size))

    # Pointer data starts after the table
    pointer_base = offset + 16 * 4

    sides = Counter()

    # Check all three unit types (air=5, surface=8, sub=11)
    for ptr_idx in [5, 8, 11]:
        ptr_offset, ptr_size = pointer_table[ptr_idx]
        if ptr_size == 0:
            continue

        unit_start = pointer_base + ptr_offset
        num_units = ptr_size // 32

        for i in range(num_units):
            unit_offset = unit_start + (i * 32)
            word0 = struct.unpack_from("<H", data, unit_offset)[0]
            owner_raw = (word0 >> 8) & 0xFF
            side = owner_raw & 0x03
            sides[side] += 1

    return sides

# Analyze all scenario files
game_dir = Path("game")
scenario_files = sorted(game_dir.glob("*.DAT"))

total_sides = Counter()
scenario_results = []

for dat_file in scenario_files:
    if dat_file.name == "SCENARIO.DAT":
        continue

    try:
        sides = analyze_scenario_sides(dat_file)
        total_sides.update(sides)
        scenario_results.append((dat_file.name, sides))
    except Exception as e:
        print(f"Error analyzing {dat_file.name}: {e}")

print("=" * 70)
print("Side Value Analysis Across All Scenarios")
print("=" * 70)
print()

for filename, sides in scenario_results:
    if sum(sides.values()) > 0:
        print(f"{filename:20s} -> {dict(sides)}")

print()
print("=" * 70)
print("TOTALS:")
print("=" * 70)
for side in sorted(total_sides.keys()):
    side_names = {0: "Green-A", 1: "Green-B", 2: "Red-A", 3: "Red-B"}
    print(f"  Side {side} ({side_names.get(side, 'Unknown'):8s}): {total_sides[side]:4d} units")
print()
print(f"Total units: {sum(total_sides.values())}")
print()

if total_sides[2] == 0 and total_sides[3] == 0:
    print("✓ CONCLUSION: Only sides 0 (Green-A) and 1 (Green-B) are actually used!")
    print("  The data format supports 4 sides, but the game only uses 2 Green player sides.")
elif total_sides[2] > 0 or total_sides[3] > 0:
    print("✓ CONCLUSION: All 4 side values ARE used in the data!")
    print(f"  This is a 2-player game: Green player (sides 0-1) vs Red player (sides 2-3)")
    print(f"  Green-A (0): {total_sides.get(0, 0)} units")
    print(f"  Green-B (1): {total_sides.get(1, 0)} units")
    print(f"  Red-A (2): {total_sides[2]} units")
    print(f"  Red-B (3): {total_sides[3]} units")
