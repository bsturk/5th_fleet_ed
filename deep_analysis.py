#!/usr/bin/env python3
"""
Deep analysis of pointer sections to understand base and ship data structures.
"""

import struct
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from editor.data import MapFile, SCENARIO_TEXT_ENCODING


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def extract_strings_with_positions(data: bytes) -> List[Tuple[int, str]]:
    """Extract all null-terminated strings with their byte positions"""
    strings = []
    i = 0
    while i < len(data):
        if data[i] == 0:
            i += 1
            continue

        # Find the null terminator
        end = data.find(b'\x00', i)
        if end == -1:
            end = len(data)

        segment = data[i:end]

        # Try to decode as string
        try:
            text = segment.decode(SCENARIO_TEXT_ENCODING, errors='replace')
            # Only include if it has printable characters
            if any(c.isprintable() and c not in '\x00\xff' for c in text):
                strings.append((i, text))
        except:
            pass

        i = end + 1

    return strings


def analyze_pointer_section_9():
    """Detailed analysis of pointer section 9 (base names)"""
    print_section("DEEP DIVE: Pointer Section 9 (Base Names)")

    game_dir = Path("game")
    map_path = game_dir / "MALDIVE.DAT"

    if not map_path.exists():
        print(f"ERROR: {map_path} not found")
        return

    map_file = MapFile.load(map_path)
    ptr_9 = map_file.pointer_entries[9]

    print(f"\nPointer Section 9 Details:")
    print(f"  Start offset: {ptr_9.start}")
    print(f"  Count field: {ptr_9.count}")
    print(f"  Data length: {ptr_9.length} bytes")

    # Extract strings with positions
    strings = extract_strings_with_positions(ptr_9.data)

    print(f"\n\nAll strings in pointer section 9 ({len(strings)} total):")
    print(f"{'Idx':>4} {'Offset':>6} {'String':>20} {'Length':>6}")
    print("-" * 80)

    for idx, (offset, text) in enumerate(strings):
        print(f"{idx:4} {offset:6} {repr(text):>20} {len(text):6}")

    # Now let's try a different parsing approach
    # Maybe the strings aren't all counted, just the meaningful ones?
    print("\n\nAttempting to find 'Male Atoll' and its index:")

    for idx, (offset, text) in enumerate(strings):
        if 'Male' in text:
            print(f"  Found at string index {idx}, byte offset {offset}: {repr(text)}")
            print(f"  BASE_RULE(?) would need operand = {idx + 1} to reach this")

    # Let's also look at the raw hex around Male Atoll
    male_pos = ptr_9.data.find(b'Male Atoll')
    if male_pos >= 0:
        print(f"\n\nRaw hex context around 'Male Atoll' (at byte {male_pos}):")
        start = max(0, male_pos - 30)
        end = min(len(ptr_9.data), male_pos + 50)
        for i in range(start, end, 16):
            hex_bytes = ' '.join(f'{b:02x}' for b in ptr_9.data[i:i+16])
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ptr_9.data[i:i+16])
            print(f"  [{i:3}] {hex_bytes:48}  {ascii_repr}")

    # Check what Cochin looks like too
    cochin_pos = ptr_9.data.find(b'Cochin')
    if cochin_pos >= 0:
        print(f"\n\nRaw hex context around 'Cochin' (at byte {cochin_pos}):")
        start = max(0, cochin_pos - 30)
        end = min(len(ptr_9.data), cochin_pos + 50)
        for i in range(start, end, 16):
            hex_bytes = ' '.join(f'{b:02x}' for b in ptr_9.data[i:i+16])
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ptr_9.data[i:i+16])
            print(f"  [{i:3}] {hex_bytes:48}  {ascii_repr}")

    # Try to interpret as structured data
    print("\n\nAttempting to parse section 9 as structured records:")
    print("  Hypothesis: Could be base records with embedded strings")

    # Look for patterns
    # Common base record size might be 42 bytes (observed in similar games)
    record_size = 42
    num_records = len(ptr_9.data) // record_size

    print(f"\n  If records are {record_size} bytes each: {num_records} records")

    for i in range(min(6, num_records)):  # Show first 6 records
        start = i * record_size
        end = start + record_size
        record = ptr_9.data[start:end]

        # Try to find strings in this record
        strings_in_record = []
        for j in range(len(record)):
            if record[j] >= 32 and record[j] < 127:  # Printable start
                end_pos = record.find(b'\x00', j)
                if end_pos > j:
                    text = record[j:end_pos].decode(SCENARIO_TEXT_ENCODING, errors='replace')
                    if len(text) > 2:
                        strings_in_record.append((j, text))
                    break

        print(f"\n  Record {i}:")
        if strings_in_record:
            for offset, text in strings_in_record:
                print(f"    String at offset {offset}: {repr(text)}")
        else:
            print(f"    (no clear string found)")

        # Show first 20 bytes as hex
        hex_preview = ' '.join(f'{b:02x}' for b in record[:20])
        print(f"    First 20 bytes: {hex_preview}")


def analyze_pointer_section_14():
    """Detailed analysis of pointer section 14 (ship data)"""
    print_section("DEEP DIVE: Pointer Section 14 (Ship Data)")

    game_dir = Path("game")
    map_path = game_dir / "MALDIVE.DAT"

    if not map_path.exists():
        print(f"ERROR: {map_path} not found")
        return

    map_file = MapFile.load(map_path)
    ptr_14 = map_file.pointer_entries[14]

    print(f"\nPointer Section 14 Details:")
    print(f"  Start offset: {ptr_14.start}")
    print(f"  Count field: {ptr_14.count}")
    print(f"  Data length: {ptr_14.length} bytes")

    # Extract strings with positions
    strings = extract_strings_with_positions(ptr_14.data)

    print(f"\n\nStrings containing ship names:")
    for idx, (offset, text) in enumerate(strings):
        if any(name in text for name in ['Antares', 'Capella', 'Missouri', 'Honolulu', 'Fast Convoy', 'FC']):
            print(f"  Idx {idx:3}, Offset {offset:5}: {repr(text)}")

    # Find Antares specifically
    antares_pos = ptr_14.data.find(b'Antares')
    if antares_pos >= 0:
        print(f"\n\nRaw hex context around 'Antares' (at byte {antares_pos}):")
        start = max(0, antares_pos - 40)
        end = min(len(ptr_14.data), antares_pos + 80)
        for i in range(start, end, 16):
            hex_bytes = ' '.join(f'{b:02x}' for b in ptr_14.data[i:i+16])
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ptr_14.data[i:i+16])
            print(f"  [{i:5}] {hex_bytes:48}  {ascii_repr}")

        # Try to parse the structure around Antares
        print(f"\n\nAttempting to parse structure around Antares:")

        # Look for patterns - ship records often have:
        # - Name string
        # - Classification string (like "Fast Convoy")
        # - Numeric data (capabilities, stats, etc.)

        record_start = antares_pos - 20  # Guess: record starts 20 bytes before name
        record_data = ptr_14.data[record_start:record_start + 120]

        # Parse as words (16-bit little-endian)
        print(f"  First 60 bytes interpreted as words:")
        for i in range(0, min(60, len(record_data)), 2):
            if i + 2 <= len(record_data):
                word = struct.unpack_from('<H', record_data, i)[0]
                byte_offset = record_start + i
                print(f"    [{byte_offset:5}] Word {i//2:2}: 0x{word:04x} ({word:5})")

    # Find Capella
    capella_pos = ptr_14.data.find(b'Capella')
    if capella_pos >= 0:
        print(f"\n\nRaw hex context around 'Capella' (at byte {capella_pos}):")
        start = max(0, capella_pos - 40)
        end = min(len(ptr_14.data), capella_pos + 80)
        for i in range(start, end, 16):
            hex_bytes = ' '.join(f'{b:02x}' for b in ptr_14.data[i:i+16])
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ptr_14.data[i:i+16])
            print(f"  [{i:5}] {hex_bytes:48}  {ascii_repr}")


def analyze_pointer_section_0():
    """Analyze pointer section 0 which might contain base IDs"""
    print_section("DEEP DIVE: Pointer Section 0 (Zone/Base IDs)")

    game_dir = Path("game")
    map_path = game_dir / "MALDIVE.DAT"

    if not map_path.exists():
        print(f"ERROR: {map_path} not found")
        return

    map_file = MapFile.load(map_path)
    ptr_0 = map_file.pointer_entries[0]

    print(f"\nPointer Section 0 Details:")
    print(f"  Start offset: {ptr_0.start}")
    print(f"  Count field: {ptr_0.count}")
    print(f"  Data length: {ptr_0.length} bytes")

    # According to docs, section 0 contains (type, region_id) pairs
    print(f"\n\nParsing as word pairs (type, region):")

    num_pairs = len(ptr_0.data) // 4  # Each pair is 2 words = 4 bytes
    print(f"  Total pairs: {num_pairs}")

    for i in range(min(20, num_pairs)):  # Show first 20 pairs
        offset = i * 4
        if offset + 4 <= len(ptr_0.data):
            type_val = struct.unpack_from('<H', ptr_0.data, offset)[0]
            region_val = struct.unpack_from('<H', ptr_0.data, offset + 2)[0]

            # Get region name if valid
            region_name = "???"
            if region_val < len(map_file.regions):
                region_name = map_file.regions[region_val].name

            print(f"  Pair {i:2}: type={type_val:3} (0x{type_val:02x}), region={region_val:2} ({region_name})")


def compare_all_scenarios():
    """Compare pointer section 9 across multiple scenario map files"""
    print_section("COMPARISON: Pointer Section 9 Across Scenarios")

    game_dir = Path("game")
    map_files = ["MALDIVE.DAT", "RAIDERS.DAT", "BARABSEA.DAT"]

    for map_filename in map_files:
        map_path = game_dir / map_filename
        if not map_path.exists():
            continue

        print(f"\n\n{map_filename}:")
        print("-" * 80)

        map_file = MapFile.load(map_path)
        if len(map_file.pointer_entries) <= 9:
            print("  No pointer section 9")
            continue

        ptr_9 = map_file.pointer_entries[9]
        strings = extract_strings_with_positions(ptr_9.data)

        print(f"  Section 9: {len(ptr_9.data)} bytes, {len(strings)} strings")
        print(f"  Base-like strings (longer than 4 chars):")

        for idx, (offset, text) in enumerate(strings):
            if len(text) > 4 and any(c.isalpha() for c in text):
                # Filter out format codes
                if not any(c < ' ' for c in text):
                    print(f"    [{idx:2}] {repr(text)}")


def main():
    """Run all deep analysis functions"""
    analyze_pointer_section_9()
    analyze_pointer_section_14()
    analyze_pointer_section_0()
    compare_all_scenarios()

    print_section("CONCLUSIONS")
    print("""
Based on this deep analysis:

1. POINTER SECTION 9 (Base Names):
   - Contains base/airfield names but mixed with other data
   - String counting needs careful attention to record boundaries
   - BASE_RULE(5) operand decoding needs verification against actual game behavior

2. POINTER SECTION 14 (Ship Data):
   - Contains individual ship/unit records with names
   - Antares and Capella are clearly present with "Fast Convoy" classification
   - This is where the editor should look up convoy ship details

3. POINTER SECTION 0 (Zone/Base IDs):
   - Contains (type, region) pairs for objectives
   - May be used by BASE_RULE to look up base locations

4. SCENARIO.DAT TEXT:
   - The OBJECTIVES section DOES contain the full descriptive text
   - "Antares and Capella must reach Male Atoll" is in the text
   - "Destroy as many units as possible" is also in the text

5. KEY INSIGHT:
   The editor should display BOTH:
   - The descriptive text from SCENARIO.DAT (already present)
   - The parsed opcodes for technical users

   The issue is NOT that the data is missing - it's that the editor
   is showing ONLY the parsed opcodes and NOT the descriptive text!
""")


if __name__ == "__main__":
    sys.exit(main())
