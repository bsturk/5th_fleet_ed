# 5th Fleet / 6th Fleet File Format Documentation

This document describes the binary file formats used by the 5th Fleet and 6th Fleet games.

## Table of Contents

1. [Scenario Files](#scenario-files)
2. [Map Files](#map-files)
3. [Objective System](#objective-system)
4. [Objective Hexes in Map Files](#objective-hexes-in-map-files)

## Scenario Files

### SCENARIO.DAT Structure

The `SCENARIO.DAT` file contains all 24 scenarios, each exactly **5883 bytes** (0x16FB).

#### Scenario Entry Layout

```
Offset  Size  Description
------  ----  -----------
0x0000  Var   Scenario name (null-terminated string)
        Var   Narrative text with FORCES and OBJECTIVES sections
        Var   Padding (null bytes)
0x16E7  4     Difficulty marker: "Low\x00", "Med\x00", or "High\x00"
0x16EB  Var   Map-related binary data (11 bytes)
0x16EF  128   Objective script (max 64 words, little-endian)
```

### Objective Script Format

The objective script is a sequence of 16-bit little-endian words:

```
Format: <operand><opcode>
  - High byte (bits 8-15): Opcode
  - Low byte (bits 0-7):   Operand
```

#### Key Opcodes

| Opcode | Name          | Operand Meaning           | Description                          |
|--------|---------------|---------------------------|--------------------------------------|
| 0x00   | END           | Region index              | End marker / section separator       |
| 0x01   | TURNS         | 0x0d=Green, 0x00=Red     | Player section delimiter             |
| 0x03   | SCORE         | Victory points required   | Victory point objective              |
| 0x04   | CONVOY_RULE   | Flags                     | Convoy delivery rule flags           |
| 0x05   | SPECIAL_RULE  | Rule code                 | Special rules (e.g., 0xfe=no cruise) |
| 0x06   | SHIP_DEST     | Port index                | Ships must reach port                |
| 0x09   | ZONE_CONTROL  | Zone index                | Zone must be controlled              |
| 0x0A   | ZONE_CHECK    | Zone index                | Check zone status                    |
| 0x0C   | TASK_FORCE    | Task force reference      | Task force objective                 |
| 0x18   | CONVOY_PORT   | Port index                | Convoy destination port              |
| 0x1D   | SHIP_OBJECTIVE| Ship type                 | Ship-specific objective              |
| 0xBB   | ZONE_ENTRY    | Zone index                | Zone entry requirement               |

#### Script Structure

Scripts are divided into Green and Red sections:

```
TURNS(13)           ; Green section starts (0x0d marker)
TASK_FORCE(254)
ZONE_CHECK(29)
END(0)              ; Section separator (NOT end of script!)
CONVOY_RULE(5)      ; Red section starts (implicit after END)
SCORE(51)
0x0000              ; Second consecutive zero = true end
```

**Important**: A single `END(0)` word (0x0000) acts as a section separator between Green and Red objectives. The script only terminates when **two consecutive zeros** appear.

## Map Files

Map files (e.g., `RAIDERS.DAT`, `CARRIER.DAT`) define the geographical layout, regions, and ports for scenarios.

### Map File Structure

```
Offset  Size  Description
------  ----  -----------
0x0000  2     Region count (typically 22, little-endian)
0x0002  Var   Region definitions (22 entries, variable size)
~0x0600 Var   Port definitions (fixed 70-byte entries)
```

### Port Entry Structure

Each port is a **70-byte (0x46)** fixed-size structure:

```
Offset from port start:
  -30 to -20:  Binary metadata
  -20 to -10:  Coordinates and flags
  -10:         SHIP_DEST marker (see below)
  0:           Port name (null-terminated string)
  +varies:     Additional port data (coordinates, etc.)
```

## Objective System

The game uses a split data model for objectives:

1. **Scenario file** (`SCENARIO.DAT`): Contains high-level objective types (CONVOY_RULE, SCORE, etc.)
2. **Map file** (e.g., `RAIDERS.DAT`): Contains specific port/location markers

This design allows the same map to be reused with different scenarios having different objective locations.

## Objective Hexes in Map Files

### Discovery

A critical finding: **Port destinations for ship objectives are NOT stored in scenario objective scripts** but rather as **flags in the map file port structures**.

### The Pattern

Each port in a map file has a SHIP_DEST marker at offset **-10 bytes from the port name**:

- **`fb 06`** = `SHIP_DEST(251)` = **Objective Port** (primary/secondary objective hex)
- **`00 06`** = `SHIP_DEST(0)` = **Non-objective Port** (regular port)

The value **251 (0xfb)** is a special flag indicating "this port is an objective destination."

### Example: Scenario 2 (Russian Raiders)

**Scenario objective script** (in SCENARIO.DAT):
```
Red objectives:
  CONVOY_RULE(5)    ; Enable ship destination checking
  SCORE(51)         ; Requires 51 victory points
```

**Map file markers** (in RAIDERS.DAT):
```
Objective ports (SHIP_DEST(251)):
  - Aden         (offset 0x093c)
  - Al Mukalla   (offset 0x09c8)
  - Ras Karma    (offset 0x0a54)

Non-objective ports (SHIP_DEST(0)):
  - Diego Garcia
  - Raysut
  - Other ports
```

### How It Works Together

1. Scenario script contains `CONVOY_RULE(5)` which tells the game: "Check if ships reach objective ports"
2. Scenario script contains `SCORE(51)` which sets the victory point threshold
3. Map file marks specific ports with `SHIP_DEST(251)` to identify which ports award points
4. Narrative text describes: "Ships must reach Aden, Al Mukalla, or Ras Karma"

The game engine reads **both** the scenario objectives AND the map port markers to determine valid destinations and award victory points.

### Why This Design?

This data-driven approach provides several benefits:

1. **Reusability**: Same map can be used with different scenarios
2. **Flexibility**: Different scenarios can have different objective ports on the same map
3. **Designer Control**: Map designers can mark objective hexes independently of scenario scripts
4. **Manual Reference**: Matches the game manual's description of "objective hexes" with "primary" or "secondary" designations

### Implementation Notes

When implementing a scenario editor:

1. **Read map file** port structures to identify ports marked with `SHIP_DEST(251)`
2. **Cross-reference** scenario objectives (CONVOY_RULE, SCORE) with map markers
3. **Display complete objectives** by combining scenario script data with map port data
4. **Example output**: "Ships must reach Aden, Al Mukalla, or Ras Karma (51 points required)"

### Multi-Zone Operands

There are exactly **3 out-of-range zone operands** in all 24 scenarios:

| Scenario | Opcode        | Operand | Zones Encoded        |
|----------|---------------|---------|----------------------|
| 2        | ZONE_CHECK    | 29      | 7, 11, 17 (OR)      |
| 3        | ZONE_CONTROL  | 35      | 7, 11, 17 (AND)     |
| 3        | ZONE_ENTRY    | 46      | 7, 11, 17 (entry)   |

These map to:
- Zone 7: Gulf of Oman
- Zone 11: North Arabian Sea
- Zone 17: South Arabian Sea

These are **hardcoded special cases** in the game engine, not algorithmically decoded. The different values (29, 35, 46) may represent different mathematical encodings attempted by developers, but all resolve to the same three zones.

## References

- Game manual description of "objective hexes"
- `docs/operand_investigation.md` - Detailed investigation of out-of-range operands
- `editor/objectives.py` - Objective script parser implementation
- `scenario_editor.py` - Scenario editor with objective decoder
