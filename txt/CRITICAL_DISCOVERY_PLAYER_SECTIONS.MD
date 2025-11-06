# CRITICAL DISCOVERY: Player Section Encoding

## The Fundamental Misunderstanding

**Previous Assumption:** All scenarios use PLAYER_SECTION opcode markers to split Green and Red objectives in the opcode script.

**REALITY:** Only scenarios 0-4 use this encoding! The other 19 scenarios do NOT encode player separation in their opcode scripts at all.

## The Truth About Scenario Encoding

### Analysis of All 24 Scenarios

```
Scenario   Has 0x0d   Has 0x00   Has 0xc0   Pattern
=========  =========  =========  =========  =======
0          TRUE       TRUE       FALSE      Explicit Green/Red split
1          TRUE       FALSE      FALSE      Explicit Green/Red split
2          TRUE       FALSE      FALSE      Explicit Green/Red split
3          TRUE       TRUE       FALSE      Explicit Green/Red split
4          TRUE       FALSE      FALSE      Explicit Green/Red split
5-13       FALSE      FALSE      FALSE      NO PLAYER MARKERS
14         FALSE      FALSE      TRUE       Campaign marker
15-23      FALSE      FALSE      FALSE      NO PLAYER MARKERS
```

### Three Encoding Patterns

#### Pattern 1: Explicit Player Section Encoding (Scenarios 0-4 ONLY)

**Structure:**
```
[0] PLAYER_SECTION(0x0d)     ← Green player objectives start
[1-2] Green objectives
[3] PLAYER_SECTION(0x00) or END(0)  ← Red player objectives start
[4] Red objective
[5] Victory modifier (SCORE or similar)
```

**Characteristics:**
- Uses PLAYER_SECTION markers to EXPLICITLY separate Green from Red
- Opcodes encode player-specific objectives
- Editor displays with Green/Red coloring

**Examples:**
- Scenario 0: PLAYER_SECTION(13), SPECIAL_RULE(254), SPECIAL_RULE(6), PLAYER_SECTION(0), BASE_RULE(5), SCORE(24)
- Scenario 3: PLAYER_SECTION(13), TASK_FORCE(254), SHIP_DEST(18), PLAYER_SECTION(0), SHIP_OBJECTIVE(8), SHIP_DEST(30)

#### Pattern 2: Game Rules Encoding (Scenarios 5-13, 15-23)

**Structure:**
```
[0] Setup opcode (CAMPAIGN_INIT, ALT_TURNS, etc.)
[1] END(region/value)  ← Victory condition
[2] Generic objective or flag
[3] Victory modifier
```

**Characteristics:**
- **NO PLAYER_SECTION markers**
- Opcodes encode:
  - Scenario initialization
  - Victory conditions (region-based, zone-based)
  - Game rules and mechanics
  - Victory modifiers
- Opcodes do NOT encode "these are Green objectives vs Red objectives"
- Player objectives determined by:
  - Unit ownership (Green owns US units, Red owns Russian units)
  - Narrative text in scenario data
  - Hardcoded game logic

**Editor Display:** Neutral gray coloring - no player split in opcode script

**Examples:**
- Scenario 5: CONVOY_PORT(6), END(9), CAMPAIGN_INIT(0), VICTORY_MOD_2B(9)
- Scenario 7: ALT_TURNS(15), END(9), ZONE_CONTROL(0), CONVOY_FALLBACK(32)
- Scenario 8: END(109), SETUP_PARAM(15), END(25), SCENARIO_INIT_14(0), VICTORY_MOD_5F(56)

#### Pattern 3: Campaign Mode (Scenario 14 ONLY)

**Structure:**
```
[0] SCENARIO_INIT_14(9)
[1] PLAYER_SECTION(0xc0)  ← Campaign mode marker (192 decimal)
[2] CAMPAIGN_FLAG(0)
[3] VICTORY_MOD_19(12)
```

**Characteristics:**
- Uses PLAYER_SECTION(0xc0) as campaign mode identifier
- No Green/Red split - unified campaign objectives
- Special campaign rules apply

**Editor Display:** Gold/yellow coloring for campaign mode

## How Player Objectives Are Actually Determined

### For Scenarios 0-4 (Explicit Encoding):
✓ Opcodes explicitly encode Green vs Red objectives using PLAYER_SECTION markers
✓ Editor can parse and display player-specific objectives from opcodes

### For Scenarios 5-23 (Implicit Assignment):
✗ Opcodes do NOT encode player separation
✓ Player objectives determined by:

1. **Unit Ownership**
   - Green player controls US/Allied units
   - Red player controls Russian/Enemy units
   - Objective: "FC units must reach port X" applies to the player who owns FC units

2. **Narrative Text**
   - All scenarios contain "Green Player:" and "Red Player:" sections in narrative data
   - Describes forces and objectives for each player
   - Located in bytes 0-5760 of scenario data

3. **Game Engine Logic**
   - Evaluates objectives based on unit state and ownership
   - Example: CONVOY_PORT(6) + ZONE_CONTROL(0) means "your convoys must reach port 6 while controlling zones"
   - "Your" = determined by which units you control

## Implications for the Scenario Editor

### Previous (Incorrect) Behavior:
- Assumed all scenarios split objectives by player in opcode script
- Tried to color scenarios 8, 9, etc. as Green/Red
- Failed because those scenarios have no player markers

### Correct Behavior:

**Scenarios 0-4:**
```python
if has_player_section_markers:
    color = "green" or "red" based on current section
```

**Scenario 14:**
```python
if has_campaign_marker:
    color = "campaign" (gold/yellow)
```

**Scenarios 5-13, 15-23:**
```python
if no_player_markers:
    color = "neutral" (gray)
    # These opcodes encode game rules, not player-specific objectives
    # Don't try to separate by player - there's no separation in the script
```

## The END(109) Pattern Explained

**Scenarios 8 and 9** start with `END(109)`:
- 109 decimal = 0x6d hex = SUPPLY_LIMIT opcode number
- This is a **self-referential initialization**
- Signals: "This scenario uses special supply/logistics rules"
- Does NOT mean "single-player" - these are still two-player scenarios
- The game determines objectives from unit ownership and narrative text

## Key Takeaway

**Only 5 out of 24 scenarios (20.8%) use explicit player section encoding in opcodes.**

**The majority (79.2%) encode game rules and victory conditions, leaving player objective assignment to the game engine based on unit ownership and narrative text.**

This is a fundamental architectural choice by the game designers:
- Simple scenarios (0-4): Explicitly encode player objectives in opcodes
- Complex scenarios (5-23): Define game rules in opcodes, determine player objectives at runtime

---

*Discovered: 2025-01-06*
*Method: Systematic analysis of all 24 scenarios*
*Impact: Complete revision of editor coloring logic*
