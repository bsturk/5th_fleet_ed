# 5th Fleet Reverse-Engineering Notes

## Tooling

- `Fleet.exe` is a Borland/Turbo Pascal 16-bit DOS program. Graphics use the Borland Graphics Interface with the EGAVGA 2.00 BGI driver.
- `dump_5th_fleet.py` parses `SCENARIO.DAT` and the scenario `.DAT` files, exposing text, region records, pointer sections, and a quick summary of the order of battle. Run:
  ```bash
  python dump_5th_fleet.py --scenario game/SCENARIO.DAT --map game/MALDIVE.DAT
  ```
  Add `--json` for machine-readable output.
- `decode_objectives.py` decodes the objective scripts from `SCENARIO.DAT` into human-readable victory conditions using the opcode mapping table. Run:
  ```bash
  python decode_objectives.py
  ```
- `analyze_opcodes.py` performs statistical analysis on opcode usage patterns across all scenarios and searches `Fleet.exe` for interpreter vocabulary.

## Key Data Files

### SCENARIO.DAT

- First word: number of scenarios (10).
- Remainder: 10 fixed-size 5,883-byte blocks. Each block contains:
  - Narrative strings (`FORCES`, `OBJECTIVES`, optional `SPECIAL NOTES`).
  - Metadata strings: scenario title, optional series label, etc. The script infers the short scenario key (e.g. `Maldive`, `Barabsea`) from the printable tail section.
  - A difficulty token such as `ELow`, `EMedium`, `EHigh` embedded near the tail.
- Trailing binary payload (seems to hold victory-point tables and other per-scenario settings). Currently left as raw hex in the script output for round-tripping.
- The scenario key matches the basename of the companion `.DAT` file that carries the actual map/OOB data (e.g. key `Maldive` → `MALDIVE.DAT`). `SCENARIO.DAT` itself contains no unit data.

### Scenario `.DAT` Files (e.g., `MALDIVE.DAT`, `RAIDERS.DAT`, etc.)

General layout:

1. `word` region count (22 for playable scenarios).
2. Region records (`count` × 65 bytes):
   - `char[?]` region name (NUL terminated).
   - 3–6 additional `char` fields containing:
     - Format control strings (e.g., `\x0fKK` sequences referencing country codes).
     - Region code such as `rpML` (`ML` is the two-letter adjacency token).
     - Adjacency list: concatenated 2-character tokens that match the `rp??` codes (e.g. `GASOSY` → `rpGA`, `rpSO`, `rpSY` → Gulf of Aden, Somalia, Seychelles). The parser now maps these tokens to full names.
     - Optional filenames (e.g. `SO.PCX`).
- Trailing 32-byte block per region containing miscellaneous metadata. The parser exposes the raw words plus a derived `map_position` (`panel` flag for the scrolling board page, `x`/`y` pixel coordinate, and a `width` for the highlight rectangle). The first few bytes occasionally hold short ASCII labels used elsewhere.
3. Pointer table: 16 entries of `<offset_word, size_word>`. Offsets are relative to the pointer-data base (immediately following the table) and several entries overlap on purpose.
4. Pointer data sections: additional structures referenced via the pointer table. Contents vary, examples include:
   - Index lists (pairs of words where values align with region indices).
   - Raw strings (base names, filenames).
   - Unit tables (see below).
   - Mixed binary data (scripts, reinforcement schedules, etc.).

### Scenario Tail / Win Logic

- Each 5,883-byte scenario block ends with a compact **objective script** immediately after the difficulty string (`Low`, `Medium`, `High`). This script encodes victory conditions, turn limits, and special rules.
- **Script format**: Sequence of little-endian 16-bit words with encoding **`(opcode << 8) | operand`** (high byte = opcode, low byte = operand). Scripts end at `0x0000` or block boundary.
  - Example from *The Battle of the Maldives*:
    ```
    Raw hex: 0d01 fe05 0605 0001 050e 1803 0600
    Decoded: [(0x01,0x0d), (0x05,0xfe), (0x05,0x06), (0x01,0x00), (0x0e,0x05), (0x03,0x18), (0x00,0x06)]
    ```

#### Opcode Decoder Ring

`Fleet.exe` embeds the interpreter vocabulary at offset **`0x5c22b`**: `AIR(%d,%d,%d)`, `SHIP(%d,%d,%d)`, `SUB(%d,%d,%d)`, `STK(%d,%d,%d)`, `TF(%d,%d,%d)`, `TG(%d,%d,%d)`, `CARR(%d,%d,%d)`, `BASE(%d,%d,%d)`, `SH(%d,%d,%d,%d)`, `SB(%d,%d,%d,%d)`. Each is prefixed with an arity tag (`NI2` = 2 int args, `NI4` = 4 int args).

Cross-referencing scenario objectives with observed opcode patterns yields this mapping:

| Opcode | Mnemonic | Operand | Description |
|--------|----------|---------|-------------|
| `0x00` | `END` | Region index | End-of-script / victory check for region |
| `0x01` | `TURNS` | Turn count | Turn limit (`0x0d`=13, `0x0f`=15, `0x00`=unlimited) |
| `0x03` | `SCORE` | VP ref | Victory point objective (indexes VP table) |
| `0x04` | `CONVOY_RULE` | Flags | Convoy delivery rule flags |
| `0x05` | `SPECIAL_RULE` | Code | `0xfe`=no cruise missiles, `0x06`=convoy active, `0x00`=standard |
| `0x06` | `SHIP_DEST` | Port idx | Ships must reach port |
| `0x07` | ? | ? | Unknown (used in pointer section 12 for setup) |
| `0x08` | ? | ? | Unknown |
| `0x09` | `ZONE_CONTROL` | Zone idx | Zone must be controlled/occupied |
| `0x0a` | `ZONE_CHECK` | Zone idx | Check zone status (`0xfe`=special check) |
| `0x0c` | `TASK_FORCE` | TF ref | TF objective (`0xfe`=all TFs, else pointer sect 0 idx) |
| `0x0e` | `BASE_RULE` | Base idx | Airfield/base objective (destroy or hold) |
| `0x0f` | ? | ? | Unknown |
| `0x13` | `PORT_RESTRICT` | Flags | Replenishment port restrictions |
| `0x18` | `CONVOY_PORT` | Port idx | Convoy destination port |
| `0x1d` | `SHIP_OBJECTIVE` | Ship type | Ship-specific objective (class/template ref) |
| `0x29` | `REGION_RULE` | Region idx | Region-based victory rule |
| `0x2d` | `ALT_TURNS` | Turn count | Alternate turn limit (campaign scenarios) |
| `0x3a` | `CONVOY_FALLBACK` | List ref | Fallback port list (pointer sect 6) |
| `0x3c` | `DELIVERY_CHECK` | Flags | Delivery success/failure check |
| `0x3d` | `PORT_LIST` | List idx | Port list (multi-destination objectives) |
| `0x6d` | `SUPPLY_LIMIT` | Port mask | Supply port restrictions (`0x75`=117 common) |
| `0xbb` | `ZONE_ENTRY` | Zone idx | Zone entry requirement |

**Special operand values:** `0xfe` (254) = "prohibited"/"all"/"any"; `0xff` (255) = unlimited; `0x00` = none/standard (context-dependent).

**Operand resolution:** Operands reference region indices (0-21), pointer section 0 (zone/base IDs), pointer section 1 (unit/rule lookup), pointer section 6 (port lists), or embedded VP tables.

**Example decode** (*Maldives*):
```
0x01,0x0d -> TURNS(13)            // 13-turn limit
0x05,0xfe -> SPECIAL_RULE(0xfe)  // No cruise missiles
0x05,0x06 -> SPECIAL_RULE(6)      // Convoy mission active
0x01,0x00 -> TURNS(0)             // (Redundant/alternate check)
0x0e,0x05 -> BASE_RULE(5)         // Airfield objective (Male Atoll)
0x03,0x18 -> SCORE(24)            // Victory points
0x00,0x06 -> END(6)               // Victory check region 6
```

Use `decode_objectives.py` to decode all scenarios.

### Order of Battle (OOB)

- Pointer entries 5, 8, and 11 hold the air, surface, and submarine OOB respectively. Each block is a sequence of 32-byte frames (16 little-endian words).
- The low byte of word 0 is the template index into `TRMAIR.DAT`, `TRMSRF.DAT`, or `TRMSUB.DAT`. The remaining bits encode ownership/flags (`side = owner_raw & 0x03` is surfaced by the parser). Subsequent words carry deployment metadata (region hints—when the value is < number of regions we map it to the region name—plus tile coordinates/other flags).
- The script aggregates these frames to report total units per category, the most common templates, side distribution, and a few sample deployments. Raw word data is preserved in JSON for deeper reverse-engineering.

### Global Tables

- `TRMAIR.DAT`, `TRMSRF.DAT`, `TRMSUB.DAT`: Unit templates (counts followed by fixed-size records containing name, nationality code, stats, and weapon references). Needed to interpret per-scenario unit placements. Each record also carries the tactical chit index used in `MICONRES.RES`:
  - Air (`TRMAIR.DAT`): byte @ offset `0x21` (33) → icon id.
  - Surface (`TRMSRF.DAT`): word @ offset `0x72` (114) → icon id (low byte).
  - Submarine (`TRMSUB.DAT`): byte @ offset `0x1A` (26) → icon id.
- `REFER.DAT`: Lookup tables for terrain keywords (`SHAL`, `DEEP`), country abbreviations (`KKIN`, `KKUS`, etc.), weapon names (`Harpoon`, `SS-N-19`) and other shared strings.
- Graphics/UI assets:
  - Strategic maps: `MAPVER20.PCX` (2861×2126 full board) and `SMALLMP.PCX` (89×66 strategic thumbnail) in `game/`.
  - GUI resource bundles: `MAINLIB.GXL`, `GRAFIX.GXL`, `SYSTEM.RES`, etc.
  - Unit reference cards: individual 248×165 PCXs in `TRM.GXL` (e.g., `ENTPRISE.PCX`, `AKULA   .PCX`) that back the unit detail/stat screens.
  - Map counter art: tactical map icons (26×26 pixels) live in `MICONRES.RES` as 66 `MICN` records (MICN = "Map ICon"). Each record has a 16-byte header followed by pixel data:
    - Header structure:
      - Bytes 0-3: `MICN` signature
      - Bytes 4-7: Reserved/pointer (always 0x00000000)
      - Bytes 8-11: Packed value (little-endian): `(height << 24 | width << 16 | size)` where size includes both header and data
      - Bytes 12-15: Background color (low nibble at byte 12 = EGA color index, typically 0x0C = light red/pink)
    - Pixel data format (NOT planar bitplanes as originally documented):
      - 8-byte internal header (mostly zeros)
      - **Packed 4-bit pixels**: 2 pixels per byte, high nibble first, low nibble second
      - 1-pixel alignment offset: skip the first pixel after the 8-byte header
      - Pixels stored in raster order (left-to-right, top-to-bottom)
      - 26×26 = 676 pixels, requiring 338 bytes (plus offset = 339 bytes)
    - The background color index is replaced by the engine with side-specific colors (0=green, 1=red, 2=blue, 3=yellow) to indicate unit ownership
    - Index 0 is treated as transparent
    - The scenario editor renders these with EGA palette + side tinting for preview
  - Unit reference cards: Individual 248×165 PCXs in `TRM.GXL` (e.g., `ENTPRISE.PCX`, `AKULA   .PCX`) are tactical reference sheets showing detailed stats and larger artwork for each unit type.
  - Selected unit display: When a unit is selected in-game, a display panel shows nationality flag, CAP symbol, unit name, unit type, and an icon (such as a ship silhouette). Likely sources:
    - `FLAGS.GXL`: Contains nationality flag PCX files (FLAGAU, FLAGUS, FLAGRU, etc.)
    - `GRAFIX.GXL`: Contains REVCAP.PCX (CAP symbol graphics)
    - `FLEET.RES`: Alchemy resource container with BTMP (bitmap) records, possibly containing unit type icons and silhouettes
    - `MAINLIB.GXL`: Contains OPDSPLAY.PCX (operational display elements) and TRM.PCX
    - Further investigation needed to decode BTMP format and identify specific ship/aircraft silhouettes

### Map Pointer Sections Relevant to Victory Logic

- **Pointer section 0**: (type, id) pairs indexing zones/bases/objectives. Format: `(type_byte, id_byte)` as little-endian words. Example: `(0x02,0x05)`, `(0x09,0x02)`. These are referenced by opcodes like `0x0c` (TASK_FORCE) when operand != `0xfe`.
- **Pointer section 1**: (type, value) lookup table for units, special rules, and scenario-specific data. Similar format to section 0 but used for different categories of game objects.
- **Pointer section 6**: Port lists for convoy objectives. Referenced by opcodes `0x3a` (CONVOY_FALLBACK) and `0x3d` (PORT_LIST) to specify multiple valid destination ports.
- **Pointer section 12**: Unit deployment/setup script (NOT victory conditions). Contains `(opcode, operand)` tuples using the same interpreter instruction set. Opcodes `0x02`-`0x15` correspond to the unit-setup vocabulary (`AIR`, `SHIP`, `SUB`, `STK`, `TF`, `TG`, `CARR`, `BASE`, `SH`, `SB`). This section initializes task forces, stacks, and formations at scenario start.

## JSON Fields Provided by `dump_5th_fleet.py`

```
{
  "scenario_records": [
    {
      "index": 0,
      "forces": "...",
      "objectives": "...",
      "notes": "...",
      "metadata_strings": ["The Battle of the Maldives"],
      "scenario_key": "Maldive",
      "difficulty": "ELow",
      "printable_sequences": [...],
      "trailing_bytes_hex": "..."
    },
    ...
  ],
  "map": {
    "file": "MALDIVE.DAT",
    "region_count": 22,
    "regions": [
      {
        "index": 0,
        "name": "Africa",
        "region_code": "AF",
        "fields": [
          {"text": "\u000fKKX\u000fKK\u0001", "raw_hex": "..."},
          {"text": "…", "raw_hex": "..."},
          ...
        ],
        "adjacent_codes": ["GA", "SO", "SY"],
        "adjacent_regions": ["Gulf of Aden", "Somalia", "Seychelles"],
        "map_position": {
          "panel": 0,
          "x_raw": 146,
          "y_raw": 34,
          "width_raw": 180,
          "x_px": 73.0,
          "y_px": 17.0,
          "width_px": 90.0
        },
        "tail_words": [...]
      },
      ...
    ],
    "pointer_table": [
      {"index": 0, "start": 231, "count": 256, "classification": "raw_bytes", "...": "..."},
      ...
    ],
    "sections": [
      {
        "index": 5,
        "classification": "unit_table",
        "offset": 3288,
        "size": 1024,
        "preview": {
          "unit_count": 30,
          "top_templates": [["AV-8B", 12], ["E-2C", 3], ...],
          "side_counts": [[0, 16], [1, 4], [2, 6], [3, 4]],
          "top_regions": [["Male Atoll", 6], ["Gulf of Aden", 3], ...]
        }
      },
      ...
    ],
    "unit_tables": {
      "air": [
        {
          "slot": 0,
          "template_id": 63,
          "template_name": "T95H",
          "owner_raw": 194,
          "side": 2,
          "region_index": 6,
          "region_name": "Gulf of Aden",
          "tile_x": 34,
          "tile_y": 34,
          "raw_words": [...]
        },
        ...
      ],
      "surface": [...],
      "sub": [...]
    }
  }
}
```

### Mapping the Strategic Board to PCX Assets

- The scrolling strategic board displayed in the UI is `STRATMAP.PCX`, a 640×480, 16-colour image embedded inside `MAINLIB.GXL`. Each resource entry in `MAINLIB.GXL` stores a name followed by two 32-bit little-endian integers (`offset`, `length`). `STRATMAP.PCX` lives at offset 0x0004B851 (309 329) with length 100 197 bytes.
- Region highlight coordinates from the `.DAT` “tail” block are local to 256-wide board panels. There are two panel pages:
  - `panel = 0` lives at pixel offset `(x_base, y_base) = (184, 0)` inside `STRATMAP.PCX`.
  - `panel = 1` lives at `(48, 8)`.
- The stored `x_raw`, `y_raw`, `width_raw` values are already pixel units for the panel; to locate a highlight rectangle inside `STRATMAP.PCX`, use:
  ```
  pcx_x = x_base + x_raw
  pcx_y = y_base + y_raw
  pcx_width = width_raw
  ```
  (heights are thin strips; the game draws custom outlines.) We verified this by overlaying the rectangles on the extracted PCX and all fall squarely on the coastline artwork—no rectangle extends past 256 pixels within its panel.
- The game likely renders a 320×200 viewport over the 640-pixel board, toggling between the two panel offsets when you scroll horizontally.
- Other view modes:
  - The operational (hex) map is drawn from `TACTICAL.PCX` (offset 174 850, length 21 711 bytes) and related assets such as `DPBRIDGE.PCX` for UI chrome; these files also sit in `MAINLIB.GXL` and weave together the scrolling hex view, though the pointer-table that feeds the hex map still needs to be identified.
  - Tactical engagements use the “combat window” assets (`COMBTWIN.PCX`, plus winning-variation screens like `WINNONE .PCX`, `WINGREEN.PCX`, `WINRED  .PCX`). These PCXs control the 1‑on‑1 battle board rather than the strategic/operational overlays.

## Editing Considerations

- Scenario modifications:
  - Text changes: edit `SCENARIO.DAT` blocks (preserve block length).
  - Region edits: modify `name`, adjacency codes, numeric tail entries in the 65-byte records.
  - Base/unit additions: pointers 5/8/11 contain 32-byte frames referencing the air/surface/submarine template libraries; edit those frames to adjust the OOB.
  - Map highlight adjustments: the derived `map_position` (panel/x/y/width) comes from the per-region tail bytes; tweak these to move the highlight rectangle between map panels (`panel` toggles between the two scrolling boards). To change the actual PCX location, add the panel base offset described above.
- All numeric fields are little-endian. Keep counts in the pointer table in sync with actual data sizes.
- No known checksums; game should accept edited data if sizes/offsets remain consistent.

## External Map/Graphics Editing

- Strategical/operational/tactical maps are external assets, not bundled in the executable:
  - `MAPVER20.PCX` holds the full-resolution political board (2861×2126); `SMALLMP.PCX` is the 89×66 overview used for mini-map and briefing screens.
  - `*.GXL` files (Genus Microprogramming format) hold additional screens, sprites, UI elements; they embed PCX data internally.
- These can be edited or replaced with standard graphics tools (convert/unpack PCX/GXL as needed), independent of the scenario `.DAT` files.

## Next Steps

1. Extend `dump_5th_fleet.py` (or related tooling) to fully decode the remaining pointer payloads (base layouts, reinforcement scripts, OOB flag fields) so edits can be made safely.
2. Build read/write capabilities: write back modified text and binary structures while keeping offsets aligned.
3. Translate unit/weapon identifiers via `TRM*.DAT` and `REFER.DAT` to support a user-friendly editor (drop-down lists, etc.).
4. Investigate `Fleet.exe` routines for rule logic if deeper behavioral changes are needed beyond data edits.
