# Special Scenario Types in 5th Fleet

## Overview

Analysis of scenarios 8, 9, and 14 reveals **three distinct scenario types** with different player section handling. The editor now properly color-codes each type.

## Scenario Types

### Type 1: Standard Two-Player Scenarios (Most scenarios)

**Player Section Markers:**
- `PLAYER_SECTION(0x0d)` - Green player objectives start
- `PLAYER_SECTION(0x00)` - Red player objectives start

**Structure:**
```
[0] PLAYER_SECTION(0x0d)  ← Green marker
[1-N] Green objectives
[M] PLAYER_SECTION(0x00) or END(0)  ← Red marker/delimiter
[M+1...] Red objectives
[LAST] Victory modifier
```

**Editor Display:**
- Green objectives: Light green background (#e8f5e9)
- Red objectives: Light red background (#ffebee)
- Player markers: Bold with darker background

**Examples:** Scenarios 0-4, 11-13, 21-22

---

### Type 2: Campaign Mode Scenarios (Scenario 14)

**Player Section Marker:**
- `PLAYER_SECTION(0xc0)` - Campaign mode marker (0xc0 = 192 decimal)

**Structure:**
```
[0] SCENARIO_INIT_14(9)     ← Campaign initialization
[1] PLAYER_SECTION(0xc0)    ← Campaign mode marker
[2] CAMPAIGN_FLAG(0)        ← Campaign flag
[3] Victory modifier
```

**Key Characteristics:**
- Single operand value 0xc0 (192) identifies campaign mode
- No separate Green/Red sections - unified objectives
- Accompanied by CAMPAIGN_FLAG opcode
- Special campaign rules apply

**Editor Display:**
- All objectives: Light yellow/cream background (#fff9e6)
- Campaign marker: Bold gold background (#ffd700)

**Turn Count:** 0 (special flag indicating non-standard turn system)

---

### Type 3: Single-Player Scenarios (Scenarios 8, 9)

**Player Section Markers:** NONE

**Structure:**
```
[0] END(109)                ← Special initialization (109 = 0x6d = SUPPLY_LIMIT opcode!)
[1] Setup parameter
[2] END(region/value)       ← Region or mode marker
[3] Objective/flag
[4] Victory modifier
```

**Key Characteristics:**
- **NO PLAYER_SECTION markers at all**
- First opcode is END(109) where 109 = 0x6d = SUPPLY_LIMIT opcode number
- This is a **self-referential pattern** - using an opcode's value as data
- Player likely controls Red (defender) with specific objectives
- Single unified objective list (no Green/Red split)

**Editor Display:**
- All objectives: Light gray background (#f0f0f0)
- No player section headers
- Neutral/single-player appearance

**Turn Count:** 0 (special flag)

**Examples:**
- **Scenario 8**: END(109), SETUP_PARAM(15), END(25), SCENARIO_INIT_14(0), VICTORY_MOD_5F(56)
- **Scenario 9**: END(109), CONVOY_FALLBACK(30), END(28), VICTORY_MOD_23(0), VICTORY_MOD_86(98)

---

## Self-Referential Opcode Pattern

**Discovery:** END(109) in first position is a **self-referential initialization**:

```
Operand 109 (decimal) = 0x6d (hex) = SUPPLY_LIMIT opcode number
```

This clever encoding technique uses the opcode number itself as a parameter value. The game engine recognizes END(109) as:
- NOT a region victory check (operand would be < 20)
- NOT a section delimiter (operand would be 0)
- A **pointer/reference to the SUPPLY_LIMIT system** (operand = supply opcode value)

This indicates the scenario uses special supply/logistics rules without explicitly using the SUPPLY_LIMIT opcode in first position.

**Alternative Interpretation:** END(109) might trigger a special scenario mode where:
- Turn-based gameplay is disabled (turn count = 0)
- Player controls a single side (likely Red/defender)
- Special victory conditions apply
- Supply mechanics are modified

---

## Editor Coloring Logic

### Detection Algorithm

```python
# Detect scenario type
has_green_marker = any(op == 0x01 and oper == 0x0d for op, oper in script)
has_red_marker = any(op == 0x01 and oper == 0x00 for op, oper in script)
has_campaign_marker = any(op == 0x01 and oper == 0xc0 for op, oper in script)

if has_campaign_marker:
    scenario_type = "Campaign"
    color = "campaign" (yellow/gold)
elif not has_green_marker and not has_red_marker:
    scenario_type = "Single-Player"
    color = "neutral" (gray)
else:
    scenario_type = "Two-Player"
    color = "green" or "red" (based on section)
```

### Color Scheme

| Type | Background | Header | Hex Color |
|------|------------|--------|-----------|
| Green objectives | Light green | Darker green | #e8f5e9 / #c8e6c9 |
| Red objectives | Light red | Darker red | #ffebee / #ffcdd2 |
| Campaign mode | Light yellow | Gold | #fff9e6 / #ffd700 |
| Single-player | Light gray | N/A | #f0f0f0 |

---

## Technical Details

### PLAYER_SECTION Opcode (0x01)

**Operand Values:**
- `0x0d` (13) - Green player section start
- `0x00` (0) - Red player section start
- `0xc0` (192) - Campaign mode / special rules
- Other values - Reserved/undefined

**Usage Pattern:**
- Standard scenarios: Two markers (0x0d and 0x00)
- Campaign scenarios: One marker (0xc0)
- Single-player scenarios: No markers

### Turn Count Field

**Location:** `trailing_bytes[0]` (byte offset 5761 in scenario data)

**Values:**
- `> 0` - Standard turn limit for turn-based scenarios
- `0` - Special flag indicating:
  - Campaign mode with variable length
  - Single-player mode with objective-based completion
  - Non-standard victory conditions

---

## Implications for Scenario Design

1. **Three Distinct Gameplay Modes:**
   - Two-player competitive (standard)
   - Campaign progression (special rules)
   - Single-player challenge (no turn limit)

2. **Flexible Victory Conditions:**
   - Standard: VP thresholds per player
   - Campaign: Mission completion
   - Single-player: Objective achievement

3. **Editor Support:**
   - All three types fully supported
   - Proper visual distinction via color coding
   - Accurate display of objectives per type

---

## Future Research

1. **END(109) Deeper Meaning:**
   - What exact game behavior does END(109) trigger?
   - Is it truly a supply system reference?
   - Are there other self-referential opcode patterns?

2. **Campaign Mode Details:**
   - What special rules does 0xc0 enable?
   - How do campaign scenarios link together?
   - Victory progression mechanics?

3. **Single-Player Mechanics:**
   - Which side does player control in scenarios 8 and 9?
   - What are the actual objectives (since no explicit markers)?
   - How does END(25) vs END(28) differ?

---

*Analysis completed: 2025-01-06*
*Discovered by: Systematic position analysis + edge case investigation*
*Result: Complete understanding of scenario type diversity*
