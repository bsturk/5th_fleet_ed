# 5th Fleet Data Reference

## About This Document
- Empirical findings about `5th Fleet` scenario data, victory logic, and supporting assets derived from reverse engineering.
- For tooling, workflows, and search recipes, see `5th_fleet_reversing_tips.md`.

## Scenario & Map Payloads

### Data File: `SCENARIO.DAT`

- First word: number of scenarios (10).
- Remainder: 10 fixed-size 5,883-byte blocks. Each block contains:
  - Narrative strings (`FORCES`, `OBJECTIVES`, optional `SPECIAL NOTES`).
  - Metadata strings: scenario title, optional series label, etc. The script infers the short scenario key (e.g. `Maldive`, `Barabsea`) from the printable tail section.
  - A difficulty token such as `ELow`, `EMedium`, `EHigh` embedded near the tail.
- Trailing binary payload (seems to hold victory-point tables and other per-scenario settings). Currently left as raw hex in the script output for round-tripping.
- The scenario key matches the basename of the companion `.DAT` file that carries the actual map/OOB data (e.g. key `Maldive` → `MALDIVE.DAT`). `SCENARIO.DAT` itself contains no unit data.

### Data File: Scenario `.DAT` Files (e.g., `MALDIVE.DAT`, `RAIDERS.DAT`)

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

## Victory Logic

### Data File: Scenario Tail / Win Logic

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
| `0x01` | `TURNS` | Side marker | **Player objective delimiter:** `0x0d`=Green objectives start, `0x00`=Red objectives start. Runtime: returns turn limit from trailing_bytes[45] (operand ignored). |
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
| `0x41` | `FLEET_POSITION` | ? | Fleet positioning requirement |
| `0x6d` | `SUPPLY_LIMIT` | Port mask | Supply port restrictions (`0x75`=117 common) |
| `0xbb` | `ZONE_ENTRY` | Zone idx | Zone entry requirement |

**Special operand values:** `0xfe` (254) = "prohibited"/"all"/"any"; `0xff` (255) = unlimited; `0x00` = none/standard (context-dependent).

**Operand resolution:** Operands reference region indices (0-21), pointer section 0 (zone/base IDs), pointer section 1 (unit/rule lookup), pointer section 6 (port lists), or embedded VP tables.

**Script Structure:** Objective scripts encode victory conditions for both players. The TURNS opcode serves as a delimiter between player-specific objective blocks.

**Example decode** (*Maldives*):
```
Raw hex: 0d01 fe05 0605 0001 050e 1803 0600
Decoded: [(0x01,0x0d), (0x05,0xfe), (0x05,0x06), (0x01,0x00), (0x0e,0x05), (0x03,0x18), (0x00,0x06)]

GREEN PLAYER OBJECTIVES (starts with TURNS(0x0d)):
  0x01,0x0d -> TURNS(0x0d)          // Green objectives start (5 turns from trailing_bytes[45])
  0x05,0xfe -> SPECIAL_RULE(0xfe)  // No cruise missiles allowed
  0x05,0x06 -> SPECIAL_RULE(6)     // Convoy mission active → fast convoy to Male Atoll

RED PLAYER OBJECTIVES (starts with TURNS(0x00)):
  0x01,0x00 -> TURNS(0x00)          // Red objectives start
  0x0e,0x05 -> BASE_RULE(5)         // Airfield objective (base ID 5 → Male Atoll airfield per scenarios.md)
  0x03,0x18 -> SCORE(24)            // Victory points

SHARED/END:
  0x00,0x06 -> END(6)               // Victory check region 6
```

**Note:** Some scenarios have only one TURNS opcode, indicating shared or asymmetric objectives where one side has special conditions and the other has generic "destroy enemy units" goals.

**TURNS Opcode Dual Purpose:**
1. **During parsing:** Operand `0x0d`/`0x00` delimits Green/Red objective blocks
2. **During runtime evaluation:** Handler reads turn limit from `trailing_bytes[45]`, ignoring operand (see disassembly at 4430:1001)
#### BASE_RULE Opcode Base ID System (DECODED!)

**Discovery (2025-01-05):** The BASE_RULE (0x0e) opcode uses a unique indirection system to reference airfield/base names:

**Mapping Formula:**
```
BASE_RULE(operand) → pointer_section_9[operand - 1] → base name string
```

**Key Findings:**
- **Pointer Section 9** stores base/airfield names as null-terminated strings
- The operand is NOT a direct string table index
- Formula: `string_index = operand - 1`
- ALL null-terminated strings are counted (including single-character fragments)
- Example: `BASE_RULE(5)` → index 4 in pointer section 9 → "Male Atoll"

**Verification:**
| Scenario | Operand | Index | Base Name | Region | Status |
|----------|---------|-------|-----------|--------|--------|
| Maldives (0) | 5 | 4 | Male Atoll | 10 (Maldives) | ✓ VERIFIED |

**Technical Details:**
- Pointer section 9 contains mixed data: base names interspersed with binary records
- String parsing must include ALL null-terminated sequences, even garbage/fragments
- This differs from pointer section 0, which uses (type, region_id) pairs
- Base names appear multiple times in section 9 due to record structure

**Why not pointer section 15?** Initial investigation suggested pointer section 15, but that section contains adjacency/connectivity data, not base names. The actual base name table is in **pointer section 9**.

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

#### Objective Hexes in Map Files - DISCOVERED! (2025-11-06)

**BREAKTHROUGH:** Port destination objectives are NOT stored in scenario objective scripts but rather as **flags in the map file port structures**!

**Discovery:** Investigation of Scenario 2 ("Russian Raiders") revealed an apparent discrepancy:
- **Narrative text:** "The four Russian surface warships must reach Aden, Al Mukalla, or Ras Karma"
- **Objective script:** Only contains `CONVOY_RULE(5)` and `SCORE(51)` — NO explicit `SHIP_DEST` opcodes!

**The Solution:** Objective ports are marked with `SHIP_DEST(251)` flags embedded in the map file.

**Map File Port Structure:**

Each port in a map file (e.g., `RAIDERS.DAT`, `CARRIER.DAT`) is a **70-byte (0x46)** fixed-size entry containing port metadata. At **offset -10 bytes from the port name**, there is a SHIP_DEST marker:

- **`fb 06`** = `SHIP_DEST(251)` = **Objective Port** (primary/secondary objective hex as described in game manual)
- **`00 06`** = `SHIP_DEST(0)` = **Non-objective Port** (regular port)

The value **251 (0xfb)** is a special flag indicating "this port is an objective destination."

**Example: Scenario 2 (Russian Raiders)**

**Scenario objective script** (in SCENARIO.DAT):
```
Red objectives:
  CONVOY_RULE(5)    ; Enable ship destination checking
  SCORE(51)         ; Requires 51 victory points
```

**Map file markers** (in RAIDERS.DAT):
```
Objective ports (SHIP_DEST(251) at 'fb 06'):
  - Aden         (offset 0x093c)
  - Al Mukalla   (offset 0x09c8)
  - Ras Karma    (offset 0x0a54)

Non-objective ports (SHIP_DEST(0) at '00 06'):
  - Diego Garcia
  - Raysut
  - Other ports
```

**How It Works Together:**

1. Scenario script contains `CONVOY_RULE(5)` or `SPECIAL_RULE(6)` which tells the game: "Check if ships reach objective ports"
2. Scenario script contains `SCORE(X)` which sets the victory point threshold
3. Map file marks specific ports with `SHIP_DEST(251)` to identify which ports award points
4. Narrative text describes: "Ships must reach Aden, Al Mukalla, or Ras Karma"

The game engine reads **both** the scenario objectives AND the map port markers to determine valid destinations and award victory points.

**Why This Design?**

This data-driven approach provides several benefits:

1. **Reusability:** Same map can be used with different scenarios
2. **Flexibility:** Different scenarios can have different objective ports on the same map
3. **Designer Control:** Map designers can mark objective hexes independently of scenario scripts
4. **Manual Reference:** Matches the game manual's description of "objective hexes" with "primary" or "secondary" designations

**Detection Pattern:**

To find objective ports in any map file:
1. Search for byte pattern `fb 06` in raw map data
2. Port name appears 10-22 bytes after the marker
3. Look for null-terminated string starting with capital letter

**Verification:**

Tested with RAIDERS.DAT (Scenario 2):
```
Found objective port at offset 0x093c: Aden
Found objective port at offset 0x09c8: Al Mukalla
Found objective port at offset 0x0a54: Ras Karma
```

These match the narrative text exactly: *"The four Russian surface warships must reach Aden, Al Mukalla, or Ras Karma while destroying as many US merchant ships and warships as possible."*

**Implementation Notes:**

When implementing a scenario editor:
1. Read map file port structures to identify ports marked with `SHIP_DEST(251)`
2. Cross-reference scenario objectives (CONVOY_RULE, SCORE) with map markers
3. Display complete objectives by combining scenario script data with map port data
4. Example output: "Ships must reach Aden, Al Mukalla, or Ras Karma (51 points required)"

**Related Opcodes:**

- `0x04` (`CONVOY_RULE`) - Enables ship destination checking (Scenario 2)
- `0x05` (`SPECIAL_RULE`) with operand `0x06` - Convoy mission active (other scenarios)
- `0x06` (`SHIP_DEST`) - Direct port reference in scenario script (when used)
- `0x18` (`CONVOY_PORT`) - Convoy destination port reference (when used)

**Port Index System:**

Ports in map files are stored in a fixed-size array starting around offset 0x0600-0x0900. Each port entry is 70 bytes (0x46). Port indices used in `SHIP_DEST` and `CONVOY_PORT` opcodes reference this array with varying formulas (operand, operand-1, or operand-2 depending on context).

#### Turn Count Storage - DISCOVERED! (2025-01-04)

**BREAKTHROUGH:** After extensive disassembly analysis and data file investigation, the turn count storage location has been found!

**Turn counts are stored at BYTE OFFSET 45 in the `trailing_bytes` field of ScenarioRecord!**

**Verification Table:**

| Scenario | Title | Expected Turns | trailing_bytes[45] | Status |
|----------|-------|----------------|-------------------|--------|
| 0 | Maldives | 5 turns | 5 | ✓ MATCH |
| 1 | Raiders | 12 turns | 12 | ✓ MATCH |
| 2 | Arabian Sea | 10 turns | 10 | ✓ MATCH |
| 3 | Carrier Raid | 12 turns | 12 | ✓ MATCH |
| 4 | Locate/Destroy | 9 turns | 9 | ✓ MATCH |
| 5 | Convoy Battles | 7 turns | 6 | ⚠ Value is 6 |
| 6 | Bay of Bengal | 9 turns | N/A | Shorter trailing_bytes |
| 7 | Convoys to Iran | 15 turns | N/A | Uses ALT_TURNS(0x2d) opcode |
| 8 | Indian Sideshow | 15 turns | N/A | Uses ALT_TURNS(0x2d) opcode |
| 9 | Indian War | 30 turns | N/A | Uses ALT_TURNS(0x2d) opcode |

**Key Findings:**
1. **Standard scenarios (56-byte trailing_bytes)**: Turn count at byte offset 45
2. **Scenarios with shorter trailing_bytes**: Use ALT_TURNS (0x2d) opcode in objectives script instead
3. **Editing turn counts**: Modify `trailing_bytes[45]` directly or use the scenario editor
4. **TURNS(0x01) opcode**: Does NOT store the actual turn limit - it's stored separately at offset 45
5. All stock scenarios use 8-hour game turns (e.g., "5 turns (40 hours)" = 5×8)

**Discovery Method:**
- Traced through disassembly from turn counter (offset 0x7E in game state structure)
- Followed initialization chain back through dword_5E648+48Bh
- Systematically searched SCENARIO.DAT, map files, and Fleet.exe
- Finally located consistent byte pattern at offset 45 in trailing_bytes

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

**Turn Count Storage Location - DISCOVERED (2025-01-04)**

After extensive disassembly tracing and data file analysis, the turn count storage has been located:

**Primary Storage: `trailing_bytes[45]` (byte offset 45)**

For standard scenarios with 56-byte trailing_bytes sections, the turn count is stored as a single byte at offset 45.

**Structure of trailing_bytes (56 bytes total):**
```
Offset  Content
------  -------
0-1     0x0f 0x99           Unknown header
2-3     0x0c 0xfe           Unknown flags
4-20    "5th Fleet\x00"     Game name string
21-23   0xc4 0x31 0x04      Unknown data
24-25   0x00 0x02           Unknown flags
26-29   0x5c 0xbc 0x0f 0xbc Unknown data
30-31   0x0f 0xa7           Unknown data
32-40   "<scenario_key>"    E.g., "Maldive\x00", "Raiders\x00"
41      0xb0 or 0x00        Unknown flag
42-45   0x0f 0x80 0x01 0x8f Fixed pattern
45      **TURN COUNT**      ← Actual turn limit stored here!
46-55   Objective script    Starts with difficulty ("Low\x00", etc.) then opcodes
```

**Example: The Battle of the Maldives (5 turns)**
```
Hex: 0f990cfe35746820466c65657400c4310400025cbc0fbc0fa74d616c6469766500b00f80018f4c6f77000d01fe0506050001050e18030600
          │                                                        │           │  └─ Objectives script
          │                                                        │           └─ Turn count = 0x05 (5)
          │                                                        └─ Scenario key "Maldive"
          └─ Metadata prefix
```

**Fallback Storage: ALT_TURNS (0x2d) opcode**

Scenarios with shorter trailing_bytes (or those using the campaign system) store turn counts in the objectives script using opcode 0x2d (ALT_TURNS).

**How the Game Uses It:**

1. During scenario loading (in `sub_612DB` at ovr137:0755-0769), the game reads:
   ```asm
   mov ax, seg dseg
   mov es, ax
   les bx, es:dword_5E648       ; Load scenario data pointer
   les bx, es:[bx+48Bh]         ; Get metadata structure at offset 0x48B
   mov dx, es:[bx+3]            ; Read high word
   mov ax, es:[bx+1]            ; Read low word (THIS is trailing_bytes[45]!)
   les bx, [bp+arg_0]
   mov es:[bx+36h], dx          ; Store high word at offset 0x36
   mov es:[bx+34h], ax          ; Store turn count at offset 0x34
   ```

2. Later (in `sub_8BDD8` at ovr160:12EC-1305), this value is copied to the turn counter:
   ```asm
   mov ax, seg dseg
   mov es, ax
   les bx, es:dword_5E644
   mov ax, es:[bx+52h]          ; Get turn count from game state (+52h)
   dec ax                       ; Decrement by 1
   mov al, [bp+var_1]
   cbw
   add ax, ax                   ; Multiply by 2 for word offset
   mov dx, seg dseg
   mov es, dx
   les bx, es:dword_5E644
   add bx, ax
   mov es:[bx+7Eh], ax          ; Store at offset 0x7E (active turn counter)
   ```

3. The pointer at `dword_5E648 + 48Bh` points to the scenario metadata structure, and offset `+1` within that structure corresponds to `trailing_bytes[45]`.

**Discovery Method:**

1. Traced disassembly backwards from turn counter at memory offset 0x7E
2. Found initialization at `dword_5E648 + 48Bh + 1` (points to scenario metadata)
3. Systematically examined all scenario trailing_bytes for the expected values (5, 12, 10, 12, 9...)
4. Found consistent match at byte offset 45 for first 5 scenarios
5. Verified against game behavior and ALT_TURNS opcode for validation

**Why It Was Hard to Find:**

- The value is NOT in the objectives script portion - it's in the metadata section before the script
- Many scenarios share identical metadata prefixes (bytes 0-44), making pattern recognition difficult
- The 56-byte trailing_bytes structure has no obvious field boundaries or markers
- TURNS opcode (0x01) was a red herring - its operand is ignored
- Required both disassembly tracing AND systematic data file analysis to discover

## Additional Scenario Structures

### Data File: Order of Battle (OOB)

- Pointer entries 5, 8, and 11 hold the air, surface, and submarine OOB respectively. Each block is a sequence of 32-byte frames (16 little-endian words).
- The low byte of word 0 is the template index into `TRMAIR.DAT`, `TRMSRF.DAT`, or `TRMSUB.DAT`. The remaining bits encode ownership/flags (`side = owner_raw & 0x03` is surfaced by the parser). Subsequent words carry deployment metadata (region hints—when the value is < number of regions we map it to the region name—plus tile coordinates/other flags).
- The script aggregates these frames to report total units per category, the most common templates, side distribution, and a few sample deployments. Raw word data is preserved in JSON for deeper reverse-engineering.

### Data Table: Global Tables

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

### Pointer Sections Relevant to Victory Logic

## Derived Outputs

- **Pointer section 0**: (type, id) pairs indexing zones/bases/objectives. Format: `(type_byte, id_byte)` as little-endian words. Example: `(0x02,0x05)`, `(0x09,0x02)`. These are referenced by opcodes like `0x0c` (TASK_FORCE) when operand != `0xfe`.
- **Pointer section 1**: (type, value) lookup table for units, special rules, and scenario-specific data. Similar format to section 0 but used for different categories of game objects.
- **Pointer section 6**: Port lists for convoy objectives. Referenced by opcodes `0x3a` (CONVOY_FALLBACK) and `0x3d` (PORT_LIST) to specify multiple valid destination ports.
- **Pointer section 12**: Unit deployment/setup script (NOT victory conditions). Contains `(opcode, operand)` tuples using the same interpreter instruction set. Opcodes `0x02`-`0x15` correspond to the unit-setup vocabulary (`AIR`, `SHIP`, `SUB`, `STK`, `TF`, `TG`, `CARR`, `BASE`, `SH`, `SB`). This section initializes task forces, stacks, and formations at scenario start.

### JSON Output from `dump_5th_fleet.py`
Sample structure returned by the `--json` flag; field names map directly to scenario blocks, map records, pointer sections, and unit templates.
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

## Graphics Assets

### Graphics Assets: Strategic Board PCX

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

## Region Record Parsing (Disassembly)
Insights from the `disasm.txt` export that explain how map-region records are loaded and interpreted at runtime.

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
