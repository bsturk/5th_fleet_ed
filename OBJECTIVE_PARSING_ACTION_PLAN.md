# Scenario Editor Objective Parsing - Implementation Action Plan

## Executive Summary

After deep investigation, I've discovered that **the binary opcode data IS incomplete in some cases** and **uses different encoding schemes across scenarios**. This is not just a display issue - the editor needs significant enhancements to properly decode and allow editing of objectives.

---

## Key Discoveries

### 1. SCENARIO 1: Missing Convoy Destination

**Problem:** Scenario 1 has `SPECIAL_RULE(0x06)` (convoy active) but NO `CONVOY_PORT` or `SHIP_DEST` opcode.

**Current opcodes:**
```
TURNS(13)           - Green section
SPECIAL_RULE(0xfe)  - No missiles
SPECIAL_RULE(0x06)  - Convoy active   <-- WHERE IS DESTINATION?
TURNS(0)            - Red section
BASE_RULE(5)        - Male Atoll
SCORE(24)           - Victory points
END(6)              - Gulf of Aden
```

**Expected:** Some opcode specifying "ships Antares and Capella must reach Male Atoll"

**Theories:**
1. **Destination is inferred** - Since Red has BASE_RULE(5)=Male Atoll, maybe the game assumes convoy goes there
2. **Data is missing** - The original game data never had a destination opcode
3. **Hardcoded in engine** - Scenario 1 convoy destination is hardcoded in game code
4. **In MAP file** - Destination might be in unit records or other MAP data

**Action needed:** Test actual game to see how it knows where convoy goes.

---

### 2. SCENARIO 6: Has Complete Convoy Data

**Opcodes found:**
```
CONVOY_PORT(6)      - Destination port 6
END(9)              - Victory check
UNKNOWN_07(0)
0x2b(9)             - Unknown opcode
DELIVERY_CHECK(10)  - Check delivery success
```

**Port resolution test:**
- Operand: 6
- Expected: "Diego Garcia"
- Formula `operand - 2` = index 4 = "Diego Garcia" ✓
- Formula `operand - 1` = index 5 = garbage
- Formula `operand` = index 6 = empty string

**But wait:** BASE_RULE uses `operand - 1` and it works!

**Conclusion:** Different opcodes use different indexing formulas OR pointer section 9 has inconsistent structure.

---

### 3. Ship Names: Data Exists But Not Cross-Referenced

**Location:** MAP file pointer section 14

**Found for Scenario 1:**
- "Antares" at offset 4328
- "Capella" at offset 4632
- Classification: "Fast Convoy"
- Abbreviation: "FC"

**Current gap:** No automatic way to determine which ships are convoy ships.

**Possible solutions:**
1. Look up units with template_id=26 (Fast Convoy)
2. Parse pointer section 14 to find ships with "FC" classification
3. Match ship names from narrative text

**Problem:** Even if we find the ships, how do we know they're THE convoy ships for the objective vs just units on the map?

---

### 4. Victory Points (SCORE Opcode): Unknown Format

**Example:** `SCORE(24)` means "destroy as many units as possible"

**Problem:** Operand 24 references a victory points table, but:
- Table location unknown
- Table format unknown
- Might be in trailing_bytes bytes 0-42
- Might be in MAP file
- Might be computed dynamically by game

**Impact:** Editor can't display or edit what the VP objective actually means.

---

### 5. END Opcode: Gulf of Aden Mystery

**Scenario 1 has:** `END(6)` = Region 6 = Gulf of Aden

**Problem:** Gulf of Aden is NOT mentioned anywhere in objectives

**Theories:**
1. **Global victory check** - Not player-specific, just happens to appear after Red marker
2. **Convoy origin** - Ships start near Gulf of Aden (need to verify)
3. **Wrong data** - Should be END(10) for Maldives region
4. **Technical flag** - END has a different meaning we don't understand

**Impact:** Displayed objective "Victory check: Gulf of Aden" is confusing and possibly wrong.

---

## What Actually Needs Fixing

### CRITICAL: Port Name Resolution

**Issue:** CONVOY_PORT and SHIP_DEST show "port ref: X" instead of port names.

**Solution needed:**
1. Test formula across all 10 scenarios with CONVOY_PORT opcodes
2. Determine if it's always `operand - 2` or varies
3. Implement `_extract_port_name(operand)` method similar to `_extract_base_name()`
4. Handle cases where port isn't in pointer section 9

**Files to modify:**
- `scenario_editor.py:1384-1385` (CONVOY_PORT display)
- `scenario_editor.py:1374-1375` (SHIP_DEST display)

**Test cases:**
- Scenario 6: CONVOY_PORT(6) should show "Diego Garcia"
- Find other scenarios with these opcodes and verify

---

### CRITICAL: Convoy Ship Identification

**Issue:** `SPECIAL_RULE(0x06)` just says "convoy active" - doesn't say which ships or where.

**For Scenario 1 specifically:**
- Opcodes don't specify destination (no CONVOY_PORT)
- Opcodes don't specify ships (Antares, Capella)
- This information ONLY exists in narrative text

**Possible solutions:**

**Option A: Parse narrative text (hacky but works)**
```python
if SPECIAL_RULE(0x06) and not has_CONVOY_PORT:
    # Extract ship names from record.objectives using regex
    import re
    ships = re.findall(r'(Antares|Capella|\\w+) and (\\w+) must reach (\\w+ \\w+)', record.objectives)
    # Display: "Convoy mission: Antares and Capella must reach Male Atoll"
```

**Option B: Cross-reference MAP data**
```python
# Find units with Fast Convoy template
convoy_units = [u for u in surface_units if u.template_id == 26]
# Look up names in pointer section 14
ship_names = extract_unit_names_from_section_14(convoy_units)
# Display: "Convoy mission active: {ship_names} (destination unknown)"
```

**Option C: Add missing opcodes to game data**
```python
# Manually add CONVOY_PORT opcode for Scenario 1
# This changes the game data but makes it explicit
script.insert(2, (0x18, port_id_for_male_atoll))
```

**Recommendation:** Use Option A for display, but warn user that opcode data is incomplete.

---

### HIGH PRIORITY: Victory Points Decoding

**Issue:** `SCORE(24)` operand 24 means nothing to users.

**What it should say:** "Destroy as many Indian units as possible" (for Green) or "Destroy as many US units as possible" (for Red)

**Research needed:**
1. Examine trailing_bytes[0:42] for VP table structure
2. Check if operand is an offset into trailing_bytes
3. Test if it's in MAP file
4. Reverse engineer from actual game behavior

**Workaround:** Display generic text based on player section
```python
if opcode == 0x03:  # SCORE
    if current_player == "Green":
        display("Destroy as many enemy units as possible")
    elif current_player == "Red":
        display("Destroy as many enemy units as possible")
    else:
        display(f"Victory points objective (ref: {operand})")
```

---

### MEDIUM PRIORITY: END Opcode Interpretation

**Issue:** END(6) shows "Victory check: Gulf of Aden" but it's unclear what this means.

**Actions:**
1. Test Scenario 1 in actual game - does Gulf of Aden matter for victory?
2. Check if ships start in/near Gulf of Aden region
3. Compare END opcodes across all scenarios - is it always a sensible region?

**Display improvement:**
```python
if opcode == 0x00 and operand > 0:
    region_name = get_region_name(operand)
    # Add context hint
    display(f"Victory check region: {region_name}")
    display(f"  (Note: May be global end-game trigger, not player objective)")
```

---

### LOW PRIORITY: Action Type Inference

**Issue:** BASE_RULE(5) doesn't say "destroy" vs "defend" vs "reach"

**Reality:** This information is NOT in the opcodes. It's only in narrative text.

**Workaround:** Add heuristic hints
```python
if opcode == 0x0e:  # BASE_RULE
    base_name = extract_base_name(operand)
    if current_player == "Red":
        hint = " (likely: attack/destroy)"
    elif current_player == "Green":
        hint = " (likely: defend)"
    else:
        hint = ""
    display(f"Airfield/base objective: {base_name}{hint}")
```

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 days)
1. **Implement port name resolution** for CONVOY_PORT and SHIP_DEST
   - Test operand-2 formula across scenarios
   - Add fallback for unknown ports
2. **Add contextual hints** for ambiguous opcodes
   - BASE_RULE: add "(attack)" or "(defend)" based on player
   - END: add note that it may be global
   - SCORE: add generic "destroy enemies" text
3. **Document known limitations** in UI
   - Add tooltip: "Some objective details only in narrative text"
   - Highlight when opcodes are incomplete

### Phase 2: Deep Fixes (3-5 days)
4. **Research VP table format**
   - Analyze trailing_bytes[0:42] structure across all scenarios
   - Document if/where VP targets are encoded
5. **Test actual game behavior**
   - Run Scenario 1 and verify convoy destination
   - Check if Gulf of Aden is relevant to victory
6. **Implement convoy ship extraction**
   - Cross-reference SPECIAL_RULE(0x06) with MAP unit data
   - Parse pointer section 14 for ship names
   - Display actual ship names when available

### Phase 3: Editor Enhancements (1 week)
7. **Add opcode validation**
   - Warn if SPECIAL_RULE(0x06) without CONVOY_PORT
   - Flag missing destination opcodes
8. **Smart opcode insertion**
   - When user adds convoy rule, prompt for destination
   - Auto-add CONVOY_PORT opcode
9. **Narrative text sync**
   - Parse narrative objectives to extract data
   - Suggest missing opcodes based on text analysis

---

## Files That Need Changes

### `scenario_editor.py`

**Lines 1047-1102:** `_extract_base_name()`
- Working correctly, no changes needed

**Lines 1374-1375:** SHIP_DEST display
```python
# CURRENT:
elif opcode == 0x06:  # SHIP_DEST
    lines.append(f"• Ships must reach port (index: {operand})")

# PROPOSED:
elif opcode == 0x06:  # SHIP_DEST
    port_name = self._extract_port_name(operand)
    if port_name:
        lines.append(f"• Ships must reach {port_name}")
    else:
        lines.append(f"• Ships must reach port (index: {operand})")
```

**Lines 1384-1385:** CONVOY_PORT display
```python
# CURRENT:
elif opcode == 0x18:  # CONVOY_PORT
    lines.append(f"• Convoy destination (port ref: {operand})")

# PROPOSED:
elif opcode == 0x18:  # CONVOY_PORT
    port_name = self._extract_port_name(operand)
    if port_name:
        lines.append(f"• Convoy destination: {port_name}")
    else:
        lines.append(f"• Convoy destination (port ref: {operand})")
```

**Lines 1346-1354:** SPECIAL_RULE display
```python
# CURRENT:
elif opcode == 0x05:  # SPECIAL_RULE
    if operand == 0x06:
        lines.append("• Special: Convoy delivery mission active")

# PROPOSED:
elif opcode == 0x05:  # SPECIAL_RULE
    if operand == 0x06:
        # Try to find convoy details
        convoy_port = next((op for op in script if op[0] == 0x18), None)
        if convoy_port:
            port_name = self._extract_port_name(convoy_port[1])
            lines.append(f"• Convoy delivery mission: destination {port_name or 'unknown'}")
        else:
            lines.append("• Convoy delivery mission active")
            lines.append("    ⚠ WARNING: No CONVOY_PORT opcode found - destination unknown")
```

**Lines 1371-1372:** SCORE display
```python
# CURRENT:
elif opcode == 0x03:  # SCORE
    lines.append(f"• Victory points objective (ref: {operand})")

# PROPOSED:
elif opcode == 0x03:  # SCORE
    # Add generic description based on context
    vp_desc = "Destroy as many enemy units as possible"
    lines.append(f"• Victory points: {vp_desc}")
    lines.append(f"    (VP ref: {operand} - see narrative text for details)")
```

**NEW METHOD:** `_extract_port_name()`
```python
def _extract_port_name(self, port_operand: int) -> Optional[str]:
    """Extract port name from pointer section 9.

    Formula appears to be: string_index = operand - 2
    But may vary - need testing across scenarios.
    """
    if self.map_file is None:
        return None

    pointer_section_9 = next((e for e in self.map_file.pointer_entries if e.index == 9), None)
    if pointer_section_9 is None:
        return None

    section_data = self.map_file.pointer_blob[pointer_section_9.start:pointer_section_9.start + pointer_section_9.count]

    # Extract all strings
    strings = []
    i = 0
    while i < len(section_data):
        if section_data[i] == 0:
            i += 1
            continue
        start = i
        while i < len(section_data) and section_data[i] != 0:
            i += 1
        string = section_data[start:i].decode('latin1', errors='replace')
        strings.append(string)
        i += 1

    # Try formula: operand - 2
    string_index = port_operand - 2
    if 0 <= string_index < len(strings):
        port_name = strings[string_index]
        # Filter garbage strings
        if len(port_name) >= 4 and port_name[0].isupper():
            return port_name

    # Fallback: try operand - 1 (BASE_RULE formula)
    string_index = port_operand - 1
    if 0 <= string_index < len(strings):
        port_name = strings[string_index]
        if len(port_name) >= 4 and port_name[0].isupper():
            return port_name

    return None
```

---

## Testing Checklist

### Scenario 1 (Maldives)
- [ ] BASE_RULE(5) shows "Male Atoll" ✓ (already works)
- [ ] SPECIAL_RULE(0x06) shows convoy warning (no CONVOY_PORT found)
- [ ] END(6) shows Gulf of Aden with context note
- [ ] SCORE(24) shows generic VP text

### Scenario 6 (Convoy Battles)
- [ ] CONVOY_PORT(6) resolves to "Diego Garcia"
- [ ] SPECIAL_RULE not present (different structure)
- [ ] No TURNS opcodes - handle gracefully

### All Scenarios
- [ ] Run through all 10 scenarios
- [ ] Verify port names resolve correctly
- [ ] Check for scenarios with SHIP_DEST opcode
- [ ] Document any new opcode patterns found

---

## Questions That Still Need Answers

1. **Scenario 1 convoy destination:**
   - How does the game know ships go to Male Atoll?
   - Is it hardcoded, inferred, or in MAP data we haven't found?

2. **VP table format:**
   - Where is the victory points table?
   - How to decode SCORE(24) to actual objectives?

3. **END opcode semantics:**
   - Is it player-specific or global?
   - Why Gulf of Aden for Scenario 1?

4. **Port indexing formula:**
   - Is it always `operand - 2`?
   - Why different from BASE_RULE (`operand - 1`)?
   - Does it vary by pointer section or opcode type?

5. **Ship name linkage:**
   - How to definitively match "Antares"/"Capella" names to convoy objective?
   - Is it just "all units with template Fast Convoy"?
   - Or is there explicit unit ID references we haven't found?

---

## Recommendation

**Start with Phase 1** - implement port name resolution and add contextual hints. This will immediately improve the editor's usefulness without requiring deep research into unknown data structures.

**Then investigate** - spend time with the actual game to answer the questions above. Understanding how the game interprets the data will guide correct implementation.

**Finally enhance** - once we know what the data means, we can build smarter editing tools.

**Accept limitations** - some information (like action types) genuinely isn't in the binary data. The narrative text will always be the authoritative source for those details. The editor should help users understand this, not hide it.
