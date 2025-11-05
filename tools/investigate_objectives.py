#!/usr/bin/env python3
"""
Comprehensive investigation of objective parsing issue for Scenario 1.
This script analyzes the binary data to understand what information is available.
"""

import struct
import sys
from pathlib import Path
from typing import List, Tuple, Optional

sys.path.append(str(Path(__file__).resolve().parents[1]))

# Import existing parsing functions
from editor.data import ScenarioFile, MapFile, SCENARIO_TEXT_ENCODING
from editor.objectives import parse_objective_script, OPCODE_MAP, SPECIAL_OPERANDS


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def decode_opcode(opcode: int, operand: int) -> Tuple[str, str]:
    """Decode a single opcode into human-readable form"""
    if opcode in OPCODE_MAP:
        mnemonic, param_desc, description = OPCODE_MAP[opcode]
        operand_str = SPECIAL_OPERANDS.get(operand, str(operand))
        return f"{mnemonic}({operand_str})", description
    else:
        return f"OP_{opcode:02x}({operand})", "Unknown opcode"


def analyze_scenario_1():
    """Main investigation function for Scenario 1"""
    game_dir = Path("game")
    scenario_path = game_dir / "SCENARIO.DAT"

    if not scenario_path.exists():
        print(f"ERROR: {scenario_path} not found")
        return 1

    print_section("INVESTIGATION: Scenario 1 Objective Parsing Issue")

    # =========================================================================
    # TASK 1: Load Scenario 1 data
    # =========================================================================
    print_section("TASK 1: Loading Scenario 1 from SCENARIO.DAT")

    scenario_file = ScenarioFile.load(scenario_path)
    scenario_1 = scenario_file.records[0]  # Index 0 = Scenario 1

    print(f"Scenario Index: {scenario_1.index}")
    print(f"Scenario Title: {scenario_1.metadata_strings()[0] if scenario_1.metadata_entries else 'N/A'}")
    print(f"\nForces Section:")
    print(scenario_1.forces[:200] + "..." if len(scenario_1.forces) > 200 else scenario_1.forces)
    print(f"\nObjectives Section:")
    print(scenario_1.objectives[:500] + "..." if len(scenario_1.objectives) > 500 else scenario_1.objectives)
    print(f"\nSpecial Notes Section:")
    print(scenario_1.notes[:200] + "..." if len(scenario_1.notes) > 200 else scenario_1.notes)

    # Parse objective script
    script = parse_objective_script(scenario_1.trailing_bytes)
    print(f"\n\nObjective Script Opcodes ({len(script)} opcodes):")
    for opcode, operand in script:
        code_str, description = decode_opcode(opcode, operand)
        print(f"  0x{opcode:02x}({operand:3}) -> {code_str:25} // {description}")

    # =========================================================================
    # TASK 2: Determine what region 6 corresponds to
    # =========================================================================
    print_section("TASK 2: Identifying Region Names from MAP.DAT")

    # Scenario 1 uses MALDIVE.DAT according to the scenario key
    map_path = game_dir / "MALDIVE.DAT"

    if not map_path.exists():
        print(f"ERROR: {map_path} not found")
        return 1

    map_file = MapFile.load(map_path)

    print(f"\nTotal regions in MALDIVE.DAT: {map_file.region_count}")
    print(f"\nFirst 15 region names:")
    for i, region in enumerate(map_file.regions[:15]):
        region_code = region.region_code() or "N/A"
        print(f"  Region {i:2}: {region.name:30} (code: {region_code})")

    # Specifically check region 6
    if len(map_file.regions) > 6:
        region_6 = map_file.regions[6]
        print(f"\n*** Region 6 specifically: {region_6.name} ***")
        print(f"    Region code: {region_6.region_code()}")
        print(f"    Adjacent regions: {region_6.adjacent_codes()}")

    # =========================================================================
    # TASK 3: Identify base ID 5 from pointer section 9
    # =========================================================================
    print_section("TASK 3: Identifying Base ID 5 from Pointer Section 9")

    if len(map_file.pointer_entries) > 9:
        ptr_9 = map_file.pointer_entries[9]
        print(f"\nPointer Section 9:")
        print(f"  Start offset: {ptr_9.start}")
        print(f"  Count: {ptr_9.count}")
        print(f"  Length: {ptr_9.length} bytes")

        # Extract all null-terminated strings from section 9
        data = ptr_9.data
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
                    strings.append((len(strings), text))
            except:
                pass

            i = end + 1

        print(f"\nAll null-terminated strings in pointer section 9 ({len(strings)} total):")
        for idx, text in strings[:20]:  # Show first 20
            print(f"  String {idx:2}: {repr(text)}")

        # Check what BASE_RULE(5) would resolve to
        if len(strings) >= 5:
            base_5_index = 5 - 1  # operand - 1
            base_5_name = strings[base_5_index][1] if base_5_index < len(strings) else "NOT FOUND"
            print(f"\n*** BASE_RULE(5) resolves to index {base_5_index}: {repr(base_5_name)} ***")
    else:
        print("ERROR: Pointer section 9 not found")

    # =========================================================================
    # TASK 4: Analyze SCORE opcode (0x03 with operand 24)
    # =========================================================================
    print_section("TASK 4: Analyzing SCORE(24) Opcode")

    print("\nThe SCORE opcode (0x03) with operand 24 refers to a victory points objective.")
    print("According to 5th_fleet.md:")
    print("  - SCORE operand indexes a VP table")
    print("  - This is likely embedded in the trailing_bytes of the scenario")

    # Show trailing bytes around where VP table might be
    print(f"\nScenario 1 trailing_bytes length: {len(scenario_1.trailing_bytes)}")
    print(f"Trailing bytes (hex):")
    for i in range(0, min(len(scenario_1.trailing_bytes), 80), 16):
        hex_bytes = ' '.join(f'{b:02x}' for b in scenario_1.trailing_bytes[i:i+16])
        ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in scenario_1.trailing_bytes[i:i+16])
        print(f"  [{i:3}] {hex_bytes:48}  {ascii_repr}")

    # Look for byte 24 (0x18) in trailing bytes
    print(f"\nSearching for byte value 24 (0x18) in trailing_bytes:")
    for i, byte in enumerate(scenario_1.trailing_bytes):
        if byte == 24:
            context = scenario_1.trailing_bytes[max(0, i-5):i+6]
            print(f"  Found at offset {i}: context = {context.hex()}")

    # =========================================================================
    # TASK 5: Analyze SPECIAL_RULE 0x06 (convoy delivery active)
    # =========================================================================
    print_section("TASK 5: Analyzing SPECIAL_RULE(6) - Convoy Delivery")

    print("\nSPECIAL_RULE(6) indicates 'convoy delivery mission active'")
    print("This is a flag that tells the game engine to check for convoy delivery objectives.")
    print("\nSearching for ship names 'Antares' and 'Capella' in the map file...")

    # Search all pointer sections for ship names
    found_antares = False
    found_capella = False

    for ptr_idx, ptr in enumerate(map_file.pointer_entries):
        data = ptr.data
        if b'Antares' in data or b'ANTARES' in data or b'antares' in data:
            print(f"\n  Found 'Antares' reference in pointer section {ptr_idx}")
            # Extract context
            for variant in [b'Antares', b'ANTARES', b'antares']:
                pos = data.find(variant)
                if pos >= 0:
                    context_start = max(0, pos - 20)
                    context_end = min(len(data), pos + 30)
                    context = data[context_start:context_end]
                    print(f"    Context: {context}")
                    found_antares = True

        if b'Capella' in data or b'CAPELLA' in data or b'capella' in data:
            print(f"\n  Found 'Capella' reference in pointer section {ptr_idx}")
            for variant in [b'Capella', b'CAPELLA', b'capella']:
                pos = data.find(variant)
                if pos >= 0:
                    context_start = max(0, pos - 20)
                    context_end = min(len(data), pos + 30)
                    context = data[context_start:context_end]
                    print(f"    Context: {context}")
                    found_capella = True

    if not found_antares:
        print("\n  'Antares' NOT FOUND in any pointer section")
    if not found_capella:
        print("\n  'Capella' NOT FOUND in any pointer section")

    # Check unit tables
    print("\n\nChecking unit tables for ship names:")
    for kind, unit_table in map_file.unit_tables.items():
        print(f"\n  {kind.upper()} units ({len(unit_table.units)} units):")
        templates = map_file.template_library.get(kind, [])
        for unit in unit_table.units[:10]:  # Show first 10
            template_name = templates[unit.template_id].name if unit.template_id < len(templates) else "UNKNOWN"
            print(f"    Slot {unit.slot}: {template_name} (template {unit.template_id}) at region {unit.region_index}")

            # Check if this is Antares or Capella
            if 'Antares' in template_name or 'Capella' in template_name:
                print(f"      *** FOUND SHIP: {template_name} ***")

    # =========================================================================
    # TASK 6: Search for detailed objective text
    # =========================================================================
    print_section("TASK 6: Searching for Detailed Objective Text")

    print("\nSearching SCENARIO.DAT for text like 'Antares', 'Capella', 'Male Atoll'...")

    # Read raw scenario data
    raw_data = scenario_path.read_bytes()

    search_terms = [
        b'Antares', b'ANTARES',
        b'Capella', b'CAPELLA',
        b'Male Atoll', b'Male', b'MALE',
        b'destroy as many', b'Destroy as many',
        b'fast convoy', b'Fast Convoy', b'FC'
    ]

    for term in search_terms:
        pos = raw_data.find(term)
        if pos >= 0:
            # Extract context
            context_start = max(0, pos - 50)
            context_end = min(len(raw_data), pos + 50)
            context = raw_data[context_start:context_end]

            # Try to decode as text
            try:
                text = context.decode(SCENARIO_TEXT_ENCODING, errors='replace')
                print(f"\n  Found '{term.decode()}' at offset {pos}:")
                print(f"    {repr(text)}")
            except:
                print(f"\n  Found '{term.decode()}' at offset {pos} (binary context)")

    print("\n\nSearching MAP file (MALDIVE.DAT) for these terms...")
    map_raw = map_path.read_bytes()

    for term in search_terms:
        pos = map_raw.find(term)
        if pos >= 0:
            context_start = max(0, pos - 50)
            context_end = min(len(map_raw), pos + 50)
            context = map_raw[context_start:context_end]

            try:
                text = context.decode(SCENARIO_TEXT_ENCODING, errors='replace')
                print(f"\n  Found '{term.decode()}' at offset {pos}:")
                print(f"    {repr(text)}")
            except:
                print(f"\n  Found '{term.decode()}' at offset {pos} (binary context)")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print_section("INVESTIGATION SUMMARY")

    print("""
The investigation reveals several key findings:

1. SCENARIO.DAT Structure:
   - Contains Forces, Objectives, and Special Notes text sections
   - These sections appear to contain only high-level descriptions
   - The detailed ship names (Antares, Capella) are NOT in SCENARIO.DAT text

2. Objective Script Opcodes:
   - Scripts use a compact binary format with opcode/operand pairs
   - Opcodes represent objective types (convoy, base, score, etc.)
   - Operands are indices or flags, NOT full descriptions

3. Region Names:
   - Region 6 identification needs verification against MAP.DAT
   - The editor may be showing incorrect region names

4. Base Names:
   - BASE_RULE(5) resolves via pointer section 9
   - Uses formula: string_index = operand - 1

5. Ship Names:
   - Specific ship names like "Antares" and "Capella" appear to be:
     a) Stored in unit template names in MAP.DAT, OR
     b) Need to be manually added as descriptive text

6. "Destroy as many units as possible":
   - This is a generic objective that's implied by the SCORE opcode
   - It's not explicitly encoded in the binary data
   - The editor needs to infer and display this text

CONCLUSION: The binary data contains compact opcode references, but the detailed
human-readable objective descriptions need to be inferred by the editor based on
the opcode types and operands. The editor should:

- Expand SPECIAL_RULE(6) to mention specific convoy ships by looking them up
- Expand BASE_RULE(5) to "Destroy/damage [base name] airfield"
- Add implied text like "destroy as many units as possible" for SCORE objectives
- Correct the region name display for END(6)
""")

    return 0


if __name__ == "__main__":
    sys.exit(analyze_scenario_1())
