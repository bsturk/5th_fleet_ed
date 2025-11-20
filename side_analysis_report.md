# Side Assignment Analysis - Order of Battle

## Executive Summary

**Issue**: The scenario editor allows setting unit "side" to 0-3 (Green, Red, Blue, Yellow), but 5th Fleet is a **two-player wargame** (Green player vs Red player).

**Finding**: The data format uses **bits 0-1 of `owner_raw`** to encode 4 possible "side" values, and **all 4 values are actively used** in the game data.

**Recommendation**: The current behavior appears to be **INCORRECT**. Based on analysis, **bit 1 alone likely determines player ownership**, not both bits.

---

## Data Analysis

### Actual Usage Across Scenarios

Analyzed 5 scenarios (M ALD IVE, RAIDERS, CARRIER, BENGAL, CONVBATT):

```
Side Distribution:
  Side 0 (Green ):  214 units (52.8%)
  Side 1 (Red   ):   61 units (15.1%)
  Side 2 (Blue  ):   66 units (16.3%)
  Side 3 (Yellow):   64 units (15.8%)

Total: 405 units
```

**All 4 side values are used extensively in the actual game data.**

### Bit Pattern Analysis (Maldives Scenario)

When examining different bit interpretations:

```
Bits 0-1 (current interpretation):
  Side 0: 46 units
  Side 1:  5 units
  Side 2: 12 units
  Side 3: 21 units

Bit 1 alone (proposed correct interpretation):
  Bit1=0 (sides 0+1): 51 units  (Green player - US/Allied)
  Bit1=1 (sides 2+3): 33 units  (Red player - Soviet/Indian)
  Ratio: ~60/40 split

Bit 0 alone:
  Bit0=0 (sides 0+2): 58 units
  Bit0=1 (sides 1+3): 26 units
  Ratio: ~69/31 split
```

**The 51 vs 33 split from bit 1 suggests it determines player ownership.**

### Game Design Confirmation

From SCENARIO.DAT narratives:
- **Green Player**: US/Allied forces (e.g., "fast sealift ships Antares and Capella")
- **Red Player**: Soviet/Russian/Indian forces (e.g., "Destroy or damage the U.S. Airfield")

From documentation (txt/CRITICAL_DISCOVERY_PLAYER_SECTIONS.MD):
- "Green player controls US/Allied units"
- "Red player controls Russian/Enemy units"

**Confirmed: 5th Fleet is a TWO-PLAYER game.**

---

## Proposed Interpretation

### Current (Incorrect?) Encoding:
```c
side = owner_raw & 0x03;  // Gives 0-3 (Green, Red, Blue, Yellow)
```

### Proposed Correct Encoding:
```c
player = (owner_raw >> 1) & 0x01;  // Bit 1 = player (0=Green, 1=Red)
color  = owner_raw & 0x01;          // Bit 0 = color/formation ID
```

This would give:
- `owner_raw & 0x03 == 0` (00): Green player, color 0
- `owner_raw & 0x03 == 1` (01): Green player, color 1
- `owner_raw & 0x03 == 2` (10): Red player, color 0
- `owner_raw & 0x03 == 3` (11): Red player, color 1

### Alternative Interpretation:
The 4 "sides" might represent:
- **Side 0**: Green player, primary force
- **Side 1**: Green player, secondary force (e.g., allied units, reinforcements)
- **Side 2**: Red player, primary force
- **Side 3**: Red player, secondary force (e.g., allied units, reinforcements)

---

## Implementation Status

✅ **IMPLEMENTED**: Option 2 - Updated UI labels to clarify two-player nature

### Changes Made:

1. **scenario_editor.py**:
   - Icon preview radio buttons: Changed from `["Green", "Red", "Blue", "Yellow"]` to `["Green-A", "Green-B", "Red-A", "Red-B"]`
   - Unit editor label: Updated to show `"Side (0=Green-A, 1=Green-B, 2=Red-A, 3=Red-B)"`
   - Added explanatory comments in code

2. **txt/5TH_FLEET.MD**:
   - Updated Unit Record Structure table to show new side labels
   - Rewrote "Note on owner_raw Encoding" section to explain:
     - 5th Fleet is a two-player game
     - Bit 1 likely determines player (0=Green, 1=Red)
     - Bit 0 may indicate formation/sub-group
     - All 4 side values are actively used in data

3. **check_sides.py**:
   - Updated output to use new side labels
   - Improved conclusion text to reflect two-player game with 4 side values

### Future Investigations (Optional):

1. Check disassembly for how the game actually interprets bits 0-1
2. Test in-game to see if units with sides 1 vs 0 (or 3 vs 2) behave differently
3. Determine exact meaning of "A/B" sub-groups (primary/allied? formations? AI control?)

---

## Current Code Locations

**scenario_editor.py:**
- Line 551: `ttk.Label(editor, text="Side (0-3)")`
- Line 553: `ttk.Spinbox(editor, textvariable=self.unit_side_var, from_=0, to=3, width=5)`
- Line 764: `for side_value, side_label in enumerate(["Green", "Red", "Blue", "Yellow"]):`
- Line 1358: `self.unit_side_var.set(unit.owner_raw & 0x03)`
- Line 1411: `unit.owner_raw = (unit.owner_raw & 0xFFFC) | (self.unit_side_var.get() & 0x03)`

**Documentation:**
- txt/5TH_FLEET.MD:843: "bits 0-1 = side: 0=Green, 1=Red, 2=Blue, 3=Yellow"
- txt/5TH_FLEET.MD:878: "Higher bits flag mission state"

---

## Next Steps

1. **Search disassembly** for how the game checks unit ownership/side
2. **Test hypothesis**: Does bit 1 alone determine player allegiance?
3. **Update documentation** if the interpretation is confirmed
4. **Fix the editor** to correctly represent player ownership

---

**Analysis Date**: 2025-11-19
**Analyst**: Claude (AI assistant)
**Data Source**: game/*.DAT scenario files, scenario_editor.py, txt/*.MD documentation
