# 5th Fleet Reversing Tips

## Project Snapshot
- Reverse-engineering the DOS-era `Fleet.exe` and companion data files to expose scenario structure, objectives, and supporting assets.
- `Fleet.exe` targets Borland/Turbo Pascal's 16-bit DOS runtime with the EGAVGA 2.00 BGI driver statically linked.
- Game data lives under `game/` (scenario `.DAT` files, PCX/GXL assets) with helper tooling mirrored in `tools/` and Python scripts.
- Empirical findings and field layouts are documented separately in `5th_fleet.md`.

## Tooling & References

### IDA Pro Export (`disasm.txt`)
- **`disasm.txt`**: IDA Pro disassembly of `Fleet.exe` (386k lines) – **RECOMMENDED for reverse engineering**
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
grep "^sub_8E20F.*proc" disasm.txt
```
Trace usage by following the call chain. For example, locating the code that loads `scenario.dat`:
```bash
grep '"scenario.dat"' disasm.txt
grep "^.*sub_8E20F.*proc" disasm.txt
sed -n '301259,301720p' disasm.txt
```
Use `sed` line ranges to read the entire routine and note `call` instructions to hop to deeper helpers.

#### Hunting Constants and Access Patterns
Leverage `grep` to pinpoint structure math and file I/O:
```bash
grep "imul.*41h" disasm.txt            # 65-byte region record multiplier
grep "\\[bx+36h\\]" disasm.txt         # Accesses offset 0x36 in a region record
grep "int.*21h" disasm.txt             # DOS file operations
grep "mov.*ah.*3fh" disasm.txt         # AH=3Fh (read file)
grep "mov.*ah.*3dh" disasm.txt         # AH=3Dh (open file)
```
For generic pattern hunts, use pipelines:
```bash
grep "41h" disasm.txt | grep -E "imul|push|mov"
grep "proc far" disasm.txt | cut -d' ' -f2        # Quick function inventory
```

#### Quick Search Recipes
Strings, callers, and structure touches can be surfaced quickly:
```bash
grep "Unable to open" disasm.txt                    # Locate specific error text
grep "Unable to open.*XREF" disasm.txt              # Show XREF comments for that string
grep "call.*sub_7D820" disasm.txt | head -10        # Who invokes the bulk loader
grep "\\[.*+32h\\]" disasm.txt                      # Accesses offset 0x32 (50 decimal)
grep "es:\\[bx+0x" disasm.txt                       # All ES-segment memory touches
grep "imul" disasm.txt                              # Multiplication patterns
```
To trace callers iteratively:
```bash
grep "call.*sub_7D820" disasm.txt | head -10
grep "CODE XREF.*sub_8CA14" disasm.txt
grep "^.*sub_8CA14.*proc" disasm.txt
```

#### Addressing and Line Numbers
IDA uses `segment:offset` addresses (`ovr161:01AF`), where the segment name identifies an overlay (`ovrNNN`), code segment (`seg004`), or data segment (`dseg`). Absolute addresses depend on runtime loading, so rely on the segment label plus offset when cross-referencing.

Keep useful `sed` ranges handy for large routines:
```bash
sed -n '301259,301720p' disasm.txt  # sub_8E20F
sed -n '268162,268400p' disasm.txt  # sub_7D820
sed -n '45500,45600p' disasm.txt    # Region access code
```
Count matches or capture line numbers when triaging large sets:
```bash
grep -c "imul.*41h" disasm.txt
grep -n "sub_7D820.*proc" disasm.txt
```

#### Worked Example: Region Parsing
One path to the region loader:
```bash
grep "imul.*41h" disasm.txt | head -1
sed -n '45530,45550p' disasm.txt
grep -B50 "seg004:2B6D" disasm.txt | grep "proc far"
grep "call.*sub_XXXXX" disasm.txt
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

### Python Helpers
- `dump_5th_fleet.py` parses `SCENARIO.DAT` and companion scenario `.DAT` files to surface text, region records, pointer sections, and order-of-battle summaries.
  ```bash
  python dump_5th_fleet.py --scenario game/SCENARIO.DAT --map game/MALDIVE.DAT
  ```
  Add `--json` for machine-readable output.
- `decode_objectives.py` converts objective scripts into human-readable victory conditions using the opcode mapping table.
  ```bash
  python decode_objectives.py
  ```
- `analyze_opcodes.py` performs statistical analysis on opcode usage across scenarios and hunts for interpreter vocabulary in the executable.
- `scenario_editor.py` is a Tkinter GUI for editing scenarios, maps, regions, and order of battle.
  ```bash
  python scenario_editor.py
  ```
- `test_region_roundtrip.py` confirms the region parser re-serializes all maps byte-for-byte.

## Workflow Tips
- Start with the data reference in `5th_fleet.md`, then use `disasm.txt` or the Python helpers above to drill into implementation details.
- Keep terminal one-liners handy for grepping disassembly and inspecting binary payloads; the command snippets above cover common searches.
- When experimenting, copy binaries first. Executables and `.DAT` files lack checksums, but offsets and pointer counts must remain consistent.

## Editing & Asset Guardrails
- Scenario modifications:
  - Text changes: edit `SCENARIO.DAT` blocks (preserve block length).
  - Region edits: adjust names, adjacency codes, and numeric tail entries in the 65-byte records.
  - Base/unit additions: pointers 5/8/11 contain 32-byte frames referencing the air/surface/submarine template libraries.
  - Map highlight adjustments: `map_position` (panel/x/y/width) in the tail block controls highlight rectangles; panel toggles between two 256-pixel board halves. To shift the actual PCX art, add the panel base offsets documented in `5th_fleet.md`.
- All numeric fields are little-endian—keep pointer-table counts synchronized with actual payload sizes.
- External map/graphics assets:
  - `MAPVER20.PCX` (2861×2126) holds the strategic overview; `SMALLMP.PCX` is the 89×66 briefing thumbnail.
  - `*.GXL` containers embed additional PCX resources (UI chrome, unit art, flags). Convert/unpack them before editing.

## Toolchain Clues from Disassembly
- Runtime scaffolding matches Borland/Turbo Pascal: the executable queries DOS (AH=0x30) for version info, installs Turbo Pascal exception traps through INT 21h functions 35h/25h, and relies on `RET n` conventions rather than cdecl.
- Floating-point error strings in `disasm.txt` match Borland's System unit text; no external EXE packer signature appears—the binary runs directly into the Pascal runtime without decompression stubs.
- Graphics use the Borland Graphics Interface: the data segment contains BGI status strings and embedded `.BGI/.CHR` payloads, including the full EGAVGA driver image.
- The bundled EGAVGA driver self-identifies as “BGI Device Driver (EGAVGA) 2.00 – Mar 21 1988,” placing the toolchain in the 1988–1990 Turbo/Borland Pascal 4.x/5.x era.
