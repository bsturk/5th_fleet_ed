# 5th Fleet Reverse-Engineering Notes

## Tooling

### Disassembly
- **`disasm.txt`**: IDA Pro disassembly of `Fleet.exe` (386k lines) - **RECOMMENDED for reverse engineering**
  - Superior cross-references (DATA XREF, CODE XREF annotations)
  - Better function detection and naming
  - Example: `"scenario.dat" ; DATA XREF: sub_8E20F+18o` shows exactly which function references the string

#### Why IDA Pro is Preferred
IDA's text export preserves cross-references inline, so it is obvious which functions touch a string or data structure:
```asm
dseg:4B90 aScenario_dat    db 'scenario.dat',0     ; DATA XREF: sub_8E20F+18o
                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^
                                                     Used by sub_8E20F at offset +18
```
Contrast with the Ghidra export, which omits that context:
```asm
60cb:4b90 "scenario.dat"
```

#### Reading IDA Annotations
`DATA XREF` entries list every function that reads or writes a datum, while `CODE XREF` entries show which callers reach a procedure. A typical procedure header looks like:
```asm
ovr148:0000 sub_7D820      proc far                 ; CODE XREF: sub_4F5C5J
```
The segment (`ovr148`) and offset (`0000`) form the 16-bit address, and the trailing comment lists known callers.

#### Navigating the Disassembly
Find a function definition by searching for its `proc` declaration:
```bash
grep "^sub_8E20F.*proc" disasm-ida.txt
```
Trace usage by following the call chain. For example, locating the code that loads `scenario.dat`:
```bash
grep '"scenario.dat"' disasm-ida.txt
grep "^.*sub_8E20F.*proc" disasm-ida.txt
sed -n '301259,301720p' disasm-ida.txt
```
Use `sed` line ranges to read the entire routine and note `call` instructions to hop to deeper helpers.

#### Hunting Constants and Access Patterns
Leverage `grep` to pinpoint structure math and file I/O:
```bash
grep "imul.*41h" disasm-ida.txt            # 65-byte region record multiplier
grep "\\[bx+36h\\]" disasm-ida.txt         # Accesses offset 0x36 in a region record
grep "int.*21h" disasm-ida.txt             # DOS file operations
grep "mov.*ah.*3fh" disasm-ida.txt         # AH=3Fh (read file)
grep "mov.*ah.*3dh" disasm-ida.txt         # AH=3Dh (open file)
```
For generic pattern hunts, use pipelines:
```bash
grep "41h" disasm-ida.txt | grep -E "imul|push|mov"
grep "proc far" disasm-ida.txt | cut -d' ' -f2        # Quick function inventory
```

#### Quick Search Recipes
Strings, callers, and structure touches can be surfaced quickly:
```bash
grep "Unable to open" disasm-ida.txt                    # Locate specific error text
grep "Unable to open.*XREF" disasm-ida.txt              # Show XREF comments for that string
grep "call.*sub_7D820" disasm-ida.txt | head -10        # Who invokes the bulk loader
grep "\\[.*+32h\\]" disasm-ida.txt                      # Accesses offset 0x32 (50 decimal)
grep "es:\\[bx+0x" disasm-ida.txt                       # All ES-segment memory touches
grep "imul" disasm-ida.txt                              # Multiplication patterns
```
To trace callers iteratively:
```bash
grep "call.*sub_7D820" disasm-ida.txt | head -10
grep "CODE XREF.*sub_8CA14" disasm-ida.txt
grep "^.*sub_8CA14.*proc" disasm-ida.txt
```

#### Addressing and Line Numbers
IDA uses `segment:offset` addresses (`ovr161:01AF`), where the segment name identifies an overlay (`ovrNNN`), code segment (`seg004`), or data segment (`dseg`). Absolute addresses depend on runtime loading, so rely on the segment label plus offset when cross-referencing.

Keep useful `sed` ranges handy for large routines:
```bash
sed -n '301259,301720p' disasm-ida.txt  # sub_8E20F
sed -n '268162,268400p' disasm-ida.txt  # sub_7D820
sed -n '45500,45600p' disasm-ida.txt    # Region access code
```
Count matches or capture line numbers when triaging large sets:
```bash
grep -c "imul.*41h" disasm-ida.txt
grep -n "sub_7D820.*proc" disasm-ida.txt
```

#### Worked Example: Region Parsing
One path to the region loader:
```bash
grep "imul.*41h" disasm-ida.txt | head -1
sed -n '45530,45550p' disasm-ida.txt
grep -B50 "seg004:2B6D" disasm-ida.txt | grep "proc far"
grep "call.*sub_XXXXX" disasm-ida.txt
```
Breaking it down:
1. Identify the multiplication by 0x41 (65) that scales region indices.
2. Read the surrounding lines to confirm context.
3. Walk backward to the owning procedure.
4. Chase `call` sites to see which code drives the loader.

#### Known Function Highlights
- `sub_8E20F` (`ovr161:01AF`): loads `scenario.dat` (records are 89 bytes).
- `sub_8CA14` (`ovr160:2023`): loads map files and iterates 65-byte region records.
- `sub_7D820` (`ovr148:0000`): generic bulk data reader.
- `sub_2375`: low-level DOS `INT 21h` read wrapper.
- `sub_4F5C5`: thunk that jumps into `sub_7D820`.

#### Further Investigation Targets
Promising follow-up areas include adjacency handling (look for two-letter region codes), map display routines (fields around header offset 0x30), unit table parsing (0x20-sized records), the 16-entry pointer section handler, and the objective interpreter (likely a jump table of opcode handlers).

### Analysis Tools
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
- `scenario_editor.py` - Tkinter GUI for editing scenarios, maps, regions, and order of battle. Run:
  ```bash
  python scenario_editor.py
  ```

### Testing
- `test_region_roundtrip.py` - Validates that region parsing preserves binary data byte-for-byte (all 24 maps pass)

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
   - Layout: 33-byte header + 32-byte tail
   - Header contains:
     - `char[?]` region name (NUL terminated).
     - 3–6 additional `char` fields containing:
       - Format control strings (e.g., `\x0fKK` sequences referencing country codes).
       - Region code such as `rpML` (`ML` is the two-letter adjacency token).
       - Adjacency list: concatenated 2-character tokens that match the `rp??` codes (e.g. `GASOSY` → `rpGA`, `rpSO`, `rpSY` → Gulf of Aden, Somalia, Seychelles). The parser now maps these tokens to full names.
       - Optional filenames (e.g. `SO.PCX`).
   - **Important parsing considerations**:
     - Region fields may contain multiple uppercase even-length strings. The correct adjacency field is the one containing **only printable characters**. Format control strings (containing `\x0f`, `\x95`, etc.) must be filtered out during parsing to avoid misidentification. Example: Africa region has both `\x0f\x95MX\x0f\x95M\x01` (format codes) and `GASOSY` (true adjacencies); only the latter should be parsed.
     - **Tail-spanning fields**: Adjacency fields frequently overflow from the 33-byte header into the 32-byte tail section. This occurs in ~50% of regions across all maps. Example: East Indian Ocean's adjacency field `WSBBSLMLCA` has bytes 0-8 (`WSBBSLMLC`) in the header and byte 9 (`A`) at offset 33 (first byte of tail). Parsers must check if the last header field ends with an uppercase letter and the tail starts with uppercase letters, then extend the field until the next NUL terminator.
   - Tail (32-byte block) contains: miscellaneous metadata words, including `map_position` data (`panel` flag for the scrolling board page, `x`/`y` pixel coordinate, and a `width` for the highlight rectangle). The first few bytes occasionally hold short ASCII labels or the final characters of tail-spanning fields.
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
| `0x01` | `TURNS` | Turn count | Turn limit (NOTE: value 0x0d appears in many scenarios but doesn't directly match player-visible turn counts) |
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

#### Turn Count Encoding - Important Findings

Through detailed analysis of all 10 stock scenarios, the relationship between opcode values and player-visible turn limits is complex:

**Key Observations:**
1. Many scenarios use opcode `0x01` (TURNS) with operand `0x0d` (13), but their actual player-visible turn counts vary (5, 9, 10, 12 turns).
2. Opcode `0x2d` (ALT_TURNS) contains the correct turn limit in scenarios that use it (e.g., scenario 7: ALT_TURNS(15) matches "15 turns").
3. The opcode `0x01` value may represent an internal time unit conversion or serve as a template/default value.
4. All stock scenarios use 8-hour game turns (e.g., "5 turns (40 hours)" = 5×8, "12 turns (4 days)" = 12×8).

**Scenario Analysis Table:**

| Scenario | Title | Manual Turns | First Opcode | Notes |
|----------|-------|--------------|--------------|-------|
| 0 | Maldives | 5 turns (40h) | TURNS(13) | Turn count doesn't match |
| 1 | Raiders | 12 turns (96h) | TURNS(13) | Turn count doesn't match |
| 2 | Arabian Sea | 10 turns (80h) | TURNS(13) | Turn count doesn't match |
| 3 | Carrier Raid | 12 turns (96h) | TURNS(13) | Turn count doesn't match |
| 4 | Locate/Destroy | 9 turns (72h) | TURNS(13) | Turn count doesn't match |
| 5 | Convoy Battles | 7 turns (56h) | CONVOY_PORT(6) | No TURNS opcode found |
| 6 | Bay of Bengal | 9 turns (72h) | opcode 0x07(9) | First operand matches! |
| 7 | Convoys to Iran | 15 turns (120h) | **ALT_TURNS(15)** | Perfect match with 0x2d |
| 8 | Indian Sideshow | 15 turns (120h) | END(109), then 0x35(15) | Uses unknown opcode 0x35 |
| 9 | Indian War | 30 turns (240h) | END(109), then 0x3a(30) | Operand in CONVOY_FALLBACK |

**Hypothesis:** The game may use opcode `0x01` as a default/template value and calculate the actual turn limit from other data (scenario metadata, opcode `0x2d`, or external configuration). The precise mechanism requires further disassembly analysis of the scenario loading and turn-counting code in `Fleet.exe`.

#### Disassembly Analysis - Turn Counter Implementation

**Turn Counter Memory Locations:**

The game stores turn-related data in segment `60cb` (the main data segment):

| Memory Location | Purpose | Details |
|----------------|---------|---------|
| `60cb:007e` | **Turn Limit Storage** | Primary location storing maximum turns for current scenario |
| `60cb:007d` | Turn Limit Comparison | Used to check if turn limit is 30 (0x1e) |
| `60cb:b3d6` | Game State Data | Contains turn-related data accessed during game processing |
| `60cb:ba26` | **Objective Pointer** | Pointer to current objective structure (used by TURNS handler) |

**Key Functions Managing Turn Limits:**

| Function | Address | Purpose | Turn Values Set |
|----------|---------|---------|-----------------|
| `FUN_1000_31cf` | `1000:31cf` | Scenario selection & initialization | Sets `[007e]` to **5 turns** |
| `FUN_1000_76c3` | `1000:76c3` | Scenario-specific turn management | Sets `[007e]` to **19 turns** |
| `FUN_1000_7bcd` | `1000:7bcd` | **Primary scenario turn loader** | Sets 2, 8, 14, or 20 turns |

**Primary Turn Limit Loading Function (`FUN_1000_7bcd`):**

This function sets different turn limits based on scenario conditions:
- At `1000:7d18`: Sets `[007e]` to **0x02** (2 turns)
- At `1000:7d5f`: Sets `[007e]` to **0x08** (8 turns)
- At `1000:7d9b`: Sets `[007e]` to **0x14** (20 turns)
- At `1000:7de6`: Sets `[007e]` to **0x08** (8 turns)

None of these hardcoded values (2, 5, 8, 19, 20) match the expected turn counts (5, 7, 9, 10, 12, 15, 30), suggesting the turn limit is calculated or loaded from elsewhere.

**Turn Counter Processing Code:**

At address `1000:2969-2983`, the game uses the turn limit as an index:
```assembly
CMP   word ptr [DAT_60cb_007e],0x0      ; Check if turn limit > 0
MOV   BX,word ptr [DAT_60cb_007e]       ; Load turn limit into BX
SHL   BX,CL                              ; Shift for table indexing
MOV   DX,word ptr [BX + 0xad1c]         ; Get turn data from table
MOV   AX,word ptr [BX + 0xad1a]         ; Get additional turn data
```

This indicates the turn limit is used to index into game state tables at offsets `0xad1c` and `0xad1a`.

#### TURNS Opcode (0x01) Handler Analysis

**Critical Discovery:** The TURNS opcode handler **completely ignores the operand value**.

**Handler Location:** `4430:1001` (13 bytes)

**Complete Disassembly:**
```assembly
4430:1001  PUSH    BP                          ; Save frame pointer
4430:1002  MOV     BP,SP                       ; Set up stack frame
4430:1004  PUSH    DS                          ; Save data segment
4430:1005  MOV     AX,0x60cb                   ; Load data segment
4430:1008  MOV     DS,AX                       ; Set DS to 60cb
4430:100a  MOV     BX,word ptr [DAT_60cb_ba26] ; Load objective struct pointer
4430:100e  MOV     AX,word ptr [BX + 0x4]      ; Read field at offset +4
4430:1011  POP     DS                          ; Restore data segment
4430:1012  POP     BP                          ; Restore frame pointer
4430:1013  RETF                                ; Return (AX = result)
```

**What This Means:**

1. The handler receives the operand as `param_3` but **never accesses it**
2. Instead, it loads a pointer from global memory `[60cb:ba26]`
3. It reads a 16-bit value from offset `+0x4` within the structure pointed to by `ba26`
4. This value is returned in `AX` register
5. **No arithmetic, no conversion, no use of the operand at all**

**Conclusion:** The TURNS opcode (0x01) is a "getter" that returns a pre-computed value from the objective structure at offset +4. The operand encoded in the bytecode (e.g., 0x0d = 13) is ignored and serves no functional purpose—it may be a legacy artifact or documentation hint.

**The Real Turn Limit Source:** The actual turn limit must be loaded into the objective structure (at `ba26 + 0x4`) during scenario initialization, likely from:
- Scenario metadata (bytes between scenario key and difficulty string)
- External configuration data
- Hardcoded values based on scenario index
- A separate data table indexed by scenario number

#### Scenario Metadata Structure Discovery

Investigation revealed a consistent metadata pattern in each 5,883-byte scenario block:

**Metadata Location:** Starts at `difficulty_position - 15` bytes

**Structure Format:**
```
Offset from diff:  -15  -14 -13 ... -6  -5  -4  -3  -2  -1   0
Pattern:          0x0f 0xa7 <scenario_key> 0x00 [?] 0x0f 0x80 0x01 0x8f <difficulty_string>
                   ^^^^      ^^^^^^^^^^^^^^^^^^^     ^^^^^^^^^^^^^^^^^^^^
                  Marker     Variable-length key     Fixed pattern (0x0f80018f)
```

**Examples:**
- Scenario 0 (Maldives, 5 turns): `0f a7 4d 61 6c 64 69 76 65 00 b0 0f 80 01 8f` + "Low"
- Scenario 2 (Barabsea, 10 turns): `0f a7 42 61 72 61 62 73 65 61 00 0f 80 01 8f` + "Low"
- Scenario 7 (Conviran, 15 turns): `0f a7 43 6f 6e 76 69 72 61 6e 00 0f 80 01 8f` + "Medium"

**Constant Pattern Analysis:**
- `0x0fa7`: Metadata header marker
- `<scenario_key>`: ASCII text (e.g., "Maldive", "Raiders", "Barabsea")
- `0x00`: NUL terminator for key
- Byte at diff-6: `0xb0` for scenarios 0-1, `0x00` for scenarios 2-9 (purpose unknown)
- `0x0f 0x80 0x01 0x8f`: Fixed 4-byte pattern
  - `0x0f`: Unknown flag/marker
  - `0x80 0x01`: As little-endian word = **0x0180** (384 decimal) - referenced in code at 1000:2034
  - `0x8f`: Unknown flag/marker

**Turn Count Storage Mystery:**

Despite extensive disassembly analysis, the actual player-visible turn limits (5, 7, 9, 10, 12, 15, 30) are **NOT stored** in any of these locations:
1. Not in the TURNS opcode (0x01) operands - these are ignored by the handler
2. Not in the pre-difficulty metadata bytes
3. Not in a simple lookup table in `Fleet.exe`
4. Not hardcoded in `FUN_1000_7bcd` (sets 2, 8, 20, or 8 based on scenario conditions)

**Hypotheses:**
1. **External Data File**: Turn limits may be stored in an external configuration file (not yet identified)
2. **Derived from Difficulty**: The combination of difficulty level + scenario index may map to turn counts
3. **Complex Calculation**: Turn limits may be calculated from multiple metadata fields using a formula
4. **Overlay/Runtime Patch**: The game may patch turn limits at runtime from data in a different file segment

**Action Items for Complete Resolution:**
- Search for additional data files in the game directory (config files, initialization data)
- Trace the scenario loading code path completely from file open to turn counter initialization
- Examine memory dumps during actual game execution to see where turn limits are stored
- Check if there are overlay files or data segments not yet analyzed

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

## Region Record Parsing - Disassembly Analysis

### Confirmed from IDA/Ghidra Disassembly:

1. **Region Record Size**: 65 bytes (0x41) confirmed by `IMUL AX,0x41` at multiple locations
   - IDA: `seg004:2B6D`, `ovr146:0692`, `ovr190:027D`, and 60+ other locations
   - Code pattern: `mov al, byte_region_index; cbw; imul ax, 41h`

2. **Map File Loading**: IDA cross-references revealed complete loading chain:
   - String `"scenario.dat"` at `dseg:4B90` → referenced by `sub_8E20F+18o`
   - Function `sub_8E20F` (ovr161:01AF) loads scenario.dat (89-byte records)
   - Function `sub_8CA14` (ovr160:2023) loads map files with `push 41h ; 'A'` (65-byte regions)
   - Function `sub_7D820` (ovr148:0000) is generic data loader called by both

3. **Region Data Loading**: Function `sub_7D820` (ovr148:0000):
   - Reads count word at file offset 0
   - Allocates `count * size` bytes (size passed as parameter, e.g., 0x41 for regions)
   - Calls `sub_2375` (file read wrapper) to bulk-read all records
   - Does NOT parse individual fields - loads entire block as-is

4. **Tail Section Access**: Game directly accesses fixed offsets in region records:
   - `+30h` (48): Pointer to region array base
   - `+32h` (50): Segment for region data
   - `+36h` (54): 21 bytes into tail section (used for zone type checks)
   - No evidence of string parsing loops for header fields

5. **Header Field Parsing**: **NOT FOUND** in disassembly
   - No string scanning (SCASB) for NUL-terminated fields in region headers
   - No loops iterating through 0-32 byte range looking for field boundaries
   - Game appears to only use: region name (display) and tail section data (coordinates, types)
   - **Implication**: Adjacency field parsing is likely performed on-demand when needed, not during initial load
