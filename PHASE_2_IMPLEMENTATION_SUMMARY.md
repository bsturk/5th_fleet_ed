# Phase 2 Implementation Summary: Contextual Enhancements

## Completed Enhancements

### 1. Convoy Destination Warnings ✅

**Problem:** Scenario 1 has `SPECIAL_RULE(0x06)` (convoy active) but no `CONVOY_PORT` or `SHIP_DEST` opcode. The destination is ONLY in narrative text.

**Solution Implemented:**
- Pre-scan objective script for convoy-related opcodes
- Detect when `SPECIAL_RULE(0x06)` exists without destination opcodes
- Display clear warning to user:
```
• Special: Convoy delivery mission active
    ⚠ WARNING: No CONVOY_PORT or SHIP_DEST opcode found
    Destination only specified in narrative text above
```

**Impact:** Users now understand when opcode data is incomplete and know to check narrative text.

---

### 2. BASE_RULE Contextual Hints ✅

**Problem:** `BASE_RULE(5)` doesn't specify whether it's an attack, defend, or reach objective. Just says "Male Atoll".

**Solution Implemented:**
- Track current player context (Green/Red)
- Add action hints based on player:
  - Red player + BASE_RULE: `"(likely: attack/destroy)"`
  - Green player + BASE_RULE: `"(likely: defend)"`

**Example:**
```
═══ RED PLAYER OBJECTIVES ═══
• Airfield/base objective: Male Atoll (likely: attack/destroy)
```

**Impact:** Users get educated guesses about objective type instead of ambiguous labels.

**Limitation:** These are heuristic hints, not ground truth. Actual action type only exists in narrative text.

---

### 3. SCORE Opcode Improvement ✅

**Problem:** `SCORE(24)` showed as cryptic "Victory points objective (ref: 24)".

**Solution Implemented:**
- Provide generic description: `"Destroy as many enemy units as possible"`
- Still show technical reference for accuracy
- Direct user to narrative text for specifics

**Example:**
```
• Victory points: Destroy as many enemy units as possible
    (VP reference: 24 - see narrative text for specifics)
```

**Research Findings:**
- Only 2 out of 12+ scenarios use SCORE opcodes (Scenario 1 and 12)
- Both have "destroy as many units" objectives
- Operand values vary (0, 24) but meaning appears consistent
- VP table structure remains undocumented, but generic text is accurate

**Impact:** Much more user-friendly than technical reference number.

---

### 4. END Opcode Clarification ✅

**Problem:** `END(6)` shows "Victory check: Gulf of Aden" for Scenario 1, but Gulf of Aden isn't mentioned in objectives.

**Solution Implemented:**
- Changed label from "Victory check" to "Victory check region"
- Added explanatory note: `"(May be global end-game trigger, not player-specific objective)"`

**Example:**
```
• Victory check region: Gulf of Aden
    (May be global end-game trigger, not player-specific objective)
```

**Research Findings:**
- END opcodes appear in 8 out of 12 scenarios
- Region IDs vary widely: 1, 6, 9, 25, 28, 70, 109
- Some scenarios have multiple END opcodes
- **Critical discovery:** END can appear BEFORE any TURNS marker (Scenario 6)
  - This proves END is NOT always player-specific
  - It's a global game-ending condition
- END also appears in both Green and Red sections across different scenarios
- The region it references may be:
  - A victory check location
  - A game-over trigger region
  - A technical flag unrelated to actual objectives

**Impact:** Users understand the ambiguity instead of being confused by seemingly irrelevant regions.

---

## VP Table Format Research

### Investigation Results

**Query:** What do SCORE operands reference? Where is the VP table?

**Findings:**
1. **SCORE is rare:**
   - Only 2 scenarios use it: #1 (Maldives) and #12 (Battle of the Gulf)
   - Both have identical objective: "Destroy as many units as possible"

2. **Operand values:**
   - Scenario 1: `SCORE(24)`
   - Scenario 12: `SCORE(0)`
   - Different operands, same objective text

3. **Data location search:**
   - Operand values (0, 24) do NOT appear in trailing_bytes[0:42]
   - No obvious VP table structure found in metadata section
   - May be hardcoded in game engine
   - May be in MAP files (not investigated yet)

4. **Conclusion:**
   - VP table format remains undocumented
   - Generic text "Destroy as many enemy units" is accurate for all known cases
   - Further reverse engineering would require:
     - Game executable analysis
     - Testing actual VP calculations in-game
     - Examining MAP files for VP data

**Recommendation:** Generic text is sufficient. VP table research can be deprioritized.

---

## END Opcode Deep Dive

### Placement Patterns

| Scenario | END Opcode | Placement | Appears In |
|----------|-----------|-----------|------------|
| 1 (Maldives) | END(6) | After Red marker | Red section |
| 3 (Arabian Sea) | END(1) | After Green marker | Green section |
| 4 (Carrier Raid) | END(6) | After Red marker | Red section |
| 6 (Convoy Battles) | END(9) | **Before any marker** | **No player section** |
| 7 (Bay of Bengal) | END(70) | Before any marker | No player section |
| 8 (Convoys to Iran) | END(9) | Before any marker | No player section |
| 9 (Indian Ocean Sideshow) | END(109), END(25) | Mixed | Mixed |
| 10 (Indian Ocean War) | END(109), END(28) | Mixed | Mixed |

### Key Insights

1. **NOT player-specific:** Scenario 6 has END(9) with NO TURNS markers at all
2. **Global victory condition:** END likely checks "has game ended?" rather than "has this player won?"
3. **Multiple END opcodes:** Some scenarios have 2 END opcodes (different regions)
4. **Region relevance unclear:** Gulf of Aden (region 6) appears in 3 scenarios' END opcodes but isn't in their narrative objectives

### Theory

END opcode may check one of:
- "Has any unit entered this region?" → trigger game end
- "Is this region occupied?" → calculate victory
- "Has this region been visited?" → scenario progression
- Technical flag: "Check region X for end-game state"

**Without game testing or executable analysis, the exact meaning remains unknown.**

**Display enhancement is appropriate:** Warning users that it's ambiguous is the right approach.

---

## Code Changes Summary

### Files Modified
- `scenario_editor.py` (2 methods updated)

### Methods Updated

**1. `_decode_objectives()` (lines 1350-1496)**
- Added pre-scan for convoy opcodes (lines 1382-1385)
- Enhanced SPECIAL_RULE(0x06) with warning (lines 1414-1416)
- Added BASE_RULE contextual hints (lines 1453-1464)
- Improved SCORE display (lines 1439-1442)
- Enhanced END display (lines 1435-1436)

**2. `_render_decoded_objectives()` (lines 1498-1695)**
- Added pre-scan for convoy opcodes (lines 1529-1532)
- Enhanced SPECIAL_RULE(0x06) with warning (lines 1579-1581)
- Added BASE_RULE contextual hints (lines 1635-1646)
- Improved SCORE display (lines 1616-1618)
- Enhanced END display (lines 1609-1610)

### Test Results

**Scenario 1 Test:**
- ✅ Convoy warning displays correctly (no CONVOY_PORT found)
- ✅ BASE_RULE shows "(likely: attack/destroy)" in Red section
- ✅ SCORE shows "Destroy as many enemy units"
- ✅ END shows Gulf of Aden with global trigger note

---

## User Experience Improvements

### Before Phase 2:
```
═══ GREEN PLAYER OBJECTIVES ═══
• Special: Convoy delivery mission active

═══ RED PLAYER OBJECTIVES ═══
• Airfield/base objective: Male Atoll
• Victory points objective (ref: 24)
• Victory check: Gulf of Aden
```

### After Phase 2:
```
═══ GREEN PLAYER OBJECTIVES ═══
• Special: Convoy delivery mission active
    ⚠ WARNING: No CONVOY_PORT or SHIP_DEST opcode found
    Destination only specified in narrative text above

═══ RED PLAYER OBJECTIVES ═══
• Airfield/base objective: Male Atoll (likely: attack/destroy)
• Victory points: Destroy as many enemy units as possible
    (VP reference: 24 - see narrative text for specifics)
• Victory check region: Gulf of Aden
    (May be global end-game trigger, not player-specific objective)
```

**Much clearer!** Users now understand:
1. When data is missing from opcodes
2. Where to find missing information (narrative text)
3. What ambiguous opcodes likely mean
4. That some opcodes may be technical/global, not player objectives

---

## What's Still Missing (Phase 3 Candidates)

### 1. Convoy Ship Names
- Data exists in MAP pointer section 14
- Need cross-referencing logic to match ships to convoy objective
- Could display: `"Convoy mission: Antares, Capella must reach [destination]"`

### 2. Port Names (DONE IN PHASE 1!)
- ✅ Already implemented in previous commit
- `CONVOY_PORT(6)` → "Diego Garcia"

### 3. Objective Type Definitiveness
- Currently using "likely" hints
- Could parse narrative text to extract action verbs
- Would require regex parsing and NLP-lite logic

### 4. Task Force Names
- `TASK_FORCE(ref: X)` still shows reference number
- Need to find TF name database in MAP files

### 5. Multi-destination parsing
- `PORT_LIST(ref: X)` shows reference, not actual ports
- Need to decode port list data structure

---

## Recommendations

### For Users (Immediate):
1. **Test the editor** - Load scenarios and verify enhancements work correctly
2. **Check warnings** - Scenario 1 should show convoy destination warning
3. **Read narrative text** - It's still the authoritative source for details

### For Developers (Phase 3):
1. **Convoy ship extraction** - HIGH VALUE, moderate effort
2. **Task force names** - LOW VALUE (uncommon opcode), moderate effort
3. **Narrative text parsing** - HIGH EFFORT, moderate value (already have hints)
4. **PORT_LIST decoding** - HIGH EFFORT, unknown value (need to find scenarios that use it)

### Prioritization:
**Do next:** Convoy ship name extraction from pointer section 14

**Maybe later:** Task force names, PORT_LIST decoding

**Skip:** Narrative text parsing (too fragile, current hints are good enough)

---

## Commit History

1. `ffef43b` - Implement port name resolution for CONVOY_PORT and SHIP_DEST opcodes
2. `1905906` - Add contextual warnings and hints for ambiguous objective opcodes

**Branch:** `claude/debug-scenario-objective-parsing-011CUpzPPUVQa36TevFrerRu`

**Status:** Phase 2 complete, pushed to remote ✅

---

## Lessons Learned

1. **Dual representation is real:** Opcodes are sparse technical flags, narrative text has the full story
2. **Context is crucial:** Same opcode means different things in different player sections
3. **Some data genuinely doesn't exist:** Action types, ship names for Scenario 1 convoy, etc.
4. **Warnings are better than silence:** Telling users "data missing" is better than showing incomplete info
5. **Heuristics are useful:** "Likely attack/destroy" helps even if not 100% certain
6. **Game testing would help:** Without running actual game, some mysteries (END, SCORE) remain

---

## Next Steps

If continuing to Phase 3:
1. Extract convoy ship names from MAP pointer section 14
2. Match template_id=26 (Fast Convoy) units to ship names
3. Display ship names in convoy objective line
4. Test across all scenarios with convoy missions

Otherwise:
- Document current state
- Mark project as "good enough for editor use"
- Wait for user feedback before further enhancements
