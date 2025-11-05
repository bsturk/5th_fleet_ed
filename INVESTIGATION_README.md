# Objective Parsing Investigation - README

## Overview

This directory contains a comprehensive investigation into the objective parsing issue in the 5th Fleet scenario editor for Scenario 1 (The Battle of the Maldives).

**Investigation Date:** 2025-11-05
**Issue:** Displayed objectives appear incomplete compared to scenarios.md
**Status:** RESOLVED ✅

## Quick Start

**TL;DR:** The data is NOT missing. The editor shows descriptive text in the "Scenario" tab and binary opcodes in the "Objectives" tab. Users need to view both tabs to see complete information.

Read [INVESTIGATION_SUMMARY.md](INVESTIGATION_SUMMARY.md) for a quick overview.

## Files in This Investigation

### 1. Investigation Scripts

#### `investigate_objectives.py`
Main investigation script that analyzes Scenario 1 from all angles:
- Loads SCENARIO.DAT and extracts Scenario 1 data
- Identifies region names from MALDIVE.DAT
- Analyzes pointer sections for base and ship names
- Searches for objective text strings
- Provides comprehensive findings

**Run it:**
```bash
python3 investigate_objectives.py
```

#### `deep_analysis.py`
Deep dive into pointer sections and data structures:
- Detailed analysis of pointer section 9 (base names)
- Detailed analysis of pointer section 14 (ship unit records)
- Analysis of pointer section 0 (zone/base IDs)
- Cross-scenario comparison
- Raw hex dumps and structure parsing

**Run it:**
```bash
python3 deep_analysis.py
```

### 2. Documentation

#### `INVESTIGATION_SUMMARY.md` ⭐ START HERE
Quick summary of findings in plain English:
- What the data actually contains
- Why things appear incomplete
- What should be fixed
- Quick reference tables

**Best for:** Understanding the issue in 5 minutes

#### `OBJECTIVE_PARSING_INVESTIGATION_REPORT.md`
Complete detailed report covering all 7 investigation tasks:
- Task 1: Load Scenario 1 data
- Task 2: Identify region 6 (Gulf of Aden)
- Task 3: Identify base ID 5 (Male Atoll)
- Task 4: Analyze SCORE(24) opcode
- Task 5: Analyze SPECIAL_RULE(6) convoy delivery
- Task 6: Search for detailed objective text
- Task 7: Root cause analysis and recommendations

Includes:
- Executive summary
- Detailed findings for each task
- Root cause analysis
- Implementation recommendations
- Code examples for fixes

**Best for:** Complete technical understanding and implementation guidance

#### `INVESTIGATION_README.md` (this file)
Navigation guide for all investigation materials.

## Key Findings

### What Was Investigated

The user reported that the editor's Objectives tab shows:
```
═══ GREEN PLAYER OBJECTIVES ═══
• Special: No cruise missile attacks allowed
• Special: Convoy delivery mission active

═══ RED PLAYER OBJECTIVES ═══
• Airfield/base objective (base ID: 5)
• Victory points objective (ref: 24)
• Victory check: Gulf of Aden
```

But scenarios.md says it should show:
```
Green:
- Fast Convoy FC units Antares and Capella must reach Male Atoll
- In addition destroy as many Indian units as possible
- May not make cruise missile attacks

Red:
- Destroy or damage US airfield on Male Atoll
- In addition, destroy as many US units as possible
```

### What We Found

✅ **All data is present** in the binary files:
- Ship names "Antares" and "Capella" are in SCENARIO.DAT objectives text and MAP pointer section 14
- Base name "Male Atoll" is in MAP pointer section 9
- "Destroy as many units as possible" is in SCENARIO.DAT objectives text
- Region 6 correctly identified as "Gulf of Aden"

❌ **The issue is presentation:**
- The Objectives tab only shows decoded binary opcodes (compact references)
- The descriptive text is in the Scenario tab (separate location)
- Users viewing the Objectives tab don't see the complete picture

### The Root Cause

The game stores objectives in TWO formats:

1. **Descriptive Text** (in SCENARIO.DAT fields)
   - Human-readable
   - What players see in the manual
   - Shown in editor's "Scenario" tab

2. **Binary Opcodes** (in SCENARIO.DAT trailing_bytes)
   - Compact game logic
   - What the game engine executes
   - Shown in editor's "Objectives" tab

The editor preserves this dual structure but doesn't cross-link them, leading to user confusion.

## Answers to Specific Questions

### Q1: Why are "Antares" and "Capella" not showing up?
**A:** Ship names are in the descriptive text (Scenario tab) and unit records (MAP pointer section 14), but the binary opcodes use a flag `SPECIAL_RULE(6)` instead of storing names. The Objectives tab only shows the decoded opcodes.

### Q2: Why is "destroy as many units as possible" not displayed?
**A:** This phrase is in the descriptive text (Scenario tab), but the binary format uses `SCORE(24)` opcode which implies this objective without storing the text.

### Q3: Why does "Gulf of Aden" appear?
**A:** The `END(6)` opcode references region 6, which IS Gulf of Aden. This is correct. The scenario description focuses on Male Atoll (region 10), which may be a different part of the objective.

### Q4: Does the binary data contain full objective descriptions?
**A:** YES, but split across two representations:
- Full text descriptions: In SCENARIO.DAT objectives field
- Binary references: In SCENARIO.DAT trailing_bytes opcodes
- Supporting lookups: In MAP pointer sections

## Recommended Solutions

### Quick Fix (Recommended)
Display the SCENARIO.DAT objectives text at the top of the Objectives tab, above the decoded opcodes. This gives users both representations in one place.

### Enhanced Fix
Improve opcode decoding to cross-reference MAP data:
- Look up base names from pointer section 9
- Look up ship names from pointer section 14
- Expand SCORE opcode to show implied objective text
- Add explanatory tooltips

See the full report for implementation details and code examples.

## Data Structure Reference

### SCENARIO.DAT Structure
```
[Word: Count (10)]
[Scenario 0 Block: 5883 bytes]
  - Forces text (null-terminated)
  - "\nOBJECTIVES\n"
  - Objectives text (null-terminated)
  - "\nSPECIAL NOTES\n"
  - Notes text (null-terminated)
  - Metadata strings (scenario title, etc.)
  - Trailing bytes (56 bytes):
    - [45]: Turn count
    - [48+]: Objective script opcodes
[Scenario 1 Block: 5883 bytes]
...
```

### MAP File Structure (e.g., MALDIVE.DAT)
```
[Word: Region Count (22)]
[Region Records: 22 × 65 bytes]
  - Name, adjacency codes, region code, map position
[Pointer Table: 16 entries × 4 bytes]
  - Section 0: Zone/base IDs
  - Section 5: Air unit table
  - Section 8: Surface unit table
  - Section 9: Base names ← Used by BASE_RULE
  - Section 11: Sub unit table
  - Section 14: Individual unit records ← Contains ship names
[Pointer Data: variable length]
```

### Objective Script Format
```
Sequence of 16-bit words: (opcode << 8) | operand
Ends at 0x0000 or EOF

Example:
  0x010d = TURNS(13) - Green player section
  0x05fe = SPECIAL_RULE(254) - No cruise missiles
  0x0506 = SPECIAL_RULE(6) - Convoy delivery active
```

## Cross-References

- Main project documentation: `5th_fleet.md`
- Scenario descriptions: `scenarios.md`
- Editor source code: `scenario_editor.py`
- Data parsing library: `editor/data.py`
- Objective parsing: `editor/objectives.py`

## Running the Investigation

### Prerequisites
```bash
cd /home/user/5th_fleet_ed
# Ensure game/ directory contains SCENARIO.DAT and map files
```

### Run Scripts
```bash
# Main investigation
python3 investigate_objectives.py > investigation_output.txt

# Deep analysis
python3 deep_analysis.py > deep_analysis_output.txt
```

### Output
Both scripts print to stdout. Save output to files for review, or read directly in terminal.

## For Developers

If you're implementing fixes to the editor based on this investigation:

1. **Start with:** `INVESTIGATION_SUMMARY.md` to understand the issue
2. **Read:** `OBJECTIVE_PARSING_INVESTIGATION_REPORT.md` sections on recommendations
3. **Reference:** Code examples in the report for lookup functions
4. **Test with:** `investigate_objectives.py` to verify your changes load data correctly

### Key Implementation Points

- SCENARIO.DAT `objectives` field contains full text
- Binary opcodes in `trailing_bytes` need expansion
- BASE_RULE operand mapping to pointer section 9 needs verification (off-by-one issue)
- SPECIAL_RULE(6) should trigger lookup of FC units in pointer section 14
- SCORE opcode should display implied "destroy enemy units" objective
- Consider adding a "Show Descriptive Text" toggle in Objectives tab

## Questions?

This investigation comprehensively analyzed:
- All scenario data structures
- Binary opcode formats
- Pointer section contents
- String locations and encodings
- Cross-file references

If you have questions about specific aspects, refer to the detailed report or run the investigation scripts with modifications.

---

**Investigation Complete** ✅
All tasks completed successfully. All data accounted for. Root cause identified. Solutions proposed.
