# DOSBox Debugger Guide: Solving the Operand 29 Mystery

## Goal
Find out what the game does with ZONE_CHECK(29) in Scenario 2 "Russian Raiders"

## Prerequisites
- DOSBox (version with debugger support - most builds have it)
- 5th Fleet installed in a directory
- Scenario 2 data (we know it has ZONE_CHECK(29) at script position 2)

## Part 1: Launch DOSBox with Debugger

### Step 1: Start DOSBox Debugger

**On Linux/Mac:**
```bash
dosbox -debug
```

**On Windows:**
```
dosbox.exe -debug
```

You should see TWO windows:
1. The normal DOSBox window (black screen)
2. The debugger window (shows assembly code and registers)

### Step 2: Mount and Navigate to Game

In the main DOSBox window (not debugger), type:
```
mount c game
c:
dir
```

You should see `FLEET.EXE` and other game files.

## Part 2: Finding Scenario Data in Memory

### Step 3: Run the Game Until Scenario Selection

In the main DOSBox window:
```
fleet
```

The game will start. Navigate through menus until you reach the **scenario selection screen**.

### Step 4: Switch to Debugger Window

Click on the debugger window. You'll see something like:
```
0070:00001234  MOV AX, [BP+06]
EAX: 00000000  EBX: 00000000
...
```

### Step 5: Search for Our Scenario Data

We know Scenario 2's script bytes are: `0d 01 fe 0c 1d 0a 00 00`

In the debugger window, type:
```
SEARCH 0 FFFFF 0D 01 FE 0C 1D 0A
```

This searches ALL memory for that byte pattern. It should return an address like:
```
Found at: 1234:5678
```

**WRITE DOWN THIS ADDRESS!** This is where Scenario 2's data is loaded in memory.

### Step 6: Examine the Data

To see the memory at that address, type:
```
D 1234:5678
```

You should see your hex dump:
```
1234:5678  0D 01 FE 0C 1D 0A 00 00 ...
```

Verify this matches! The byte `1D` (29 decimal) should be at offset +4 from the start.

## Part 3: Finding the Code That Reads This Data

### Step 7: Set a Memory Breakpoint

We want to break when the game READS the operand value 29. The operand is at address `1234:5678+4` (wherever you found it, plus 4 bytes).

Calculate the address of the operand byte:
- If found at `1234:5678`, the operand 29 is at `1234:567C` (5678 + 4 = 567C)

Set a breakpoint on READ access:
```
BPMR 1234:567C
```

(BPMR = BreakPoint Memory Read)

### Step 8: Select Scenario 2

Go back to the main DOSBox window and **select Scenario 2 to start playing**.

The game should immediately freeze when it reads that memory location, and the debugger window will become active.

### Step 9: Examine What's Happening

You're now at the EXACT moment the game reads operand 29!

Look at the debugger window. You'll see:
```
0070:00001234  MOV AL, [BX+04]    ; Reading the operand!
EAX: 0000001D                      ; AL now contains 0x1D (29)!
```

**Key things to note:**
1. What instruction is reading it? (MOV, CMP, etc.)
2. What register does it go into?
3. What's the next instruction?

### Step 10: Step Through the Code

Press `F10` to step to the NEXT instruction. Watch what happens to that value!

Common things to look for:
- `CMP AL, 16h` - is it comparing to 22 (max regions)?
- `JA somewhere` - jumping if above 22?
- `SUB AL, 16h` - subtracting 22 to get a different index?
- `AND AL, 1Fh` - masking bits?

**Keep pressing F10 and WRITE DOWN each instruction** until you see:
- A comparison
- A jump based on the value
- A lookup using the value as index

## Part 4: What to Look For

### Scenario A: Bounds Check
```
CMP AL, 16h        ; Compare to 22
JA handle_special  ; Jump if above
; ... normal region code ...
handle_special:
; ... special handling for values > 22 ...
```

### Scenario B: Lookup Table
```
MOV BX, AX         ; Move operand to BX
ADD BX, BX         ; Multiply by 2 (word index)
MOV AX, [victory_table + BX]  ; Look up in table
```

### Scenario C: Arithmetic Transform
```
MOV AL, [operand]  ; AL = 29
SUB AL, 16h        ; AL = 29 - 22 = 7
; Now uses 7 for something else!
```

### Scenario D: It's Ignored
```
MOV AL, [operand]  ; AL = 29
; ... no code uses AL after this ...
; It just continues without checking!
```

## Part 5: Reporting Back

Please capture and send me:

1. **The memory address where you found the scenario data**
2. **The exact instructions** (5-10 lines) after reading operand 29
3. **Register values** at that point (especially AX, BX, CX)
4. **Any comparisons or jumps** based on the value

Example report format:
```
Found scenario data at: 2E34:0120
Operand 29 at: 2E34:0124

Code at breakpoint:
2E34:0124  MOV AL, [SI+04]     ; AL = 1D
2E34:0127  CMP AL, 16h         ; Compare to 22
2E34:0129  JBE short 2E34:0140 ; Jump if <=22
2E34:012B  SUB AL, 16h         ; AL = 1D - 16 = 07 !!!!
2E34:012D  MOV BX, AX
...

Register at MOV: AX=001D SI=0120
After SUB: AX=0007
```

## Troubleshooting

**Q: Game doesn't freeze after BPMR**
A: The scenario data might not be loaded yet. Try:
1. Start scenario 2 completely (get into gameplay)
2. Let it sit for a few turns
3. The objective check might only happen at game end

**Q: Can't find the byte pattern**
A: Try searching just for the distinctive parts:
```
SEARCH 0 FFFFF 1D 0A 00 00
```

**Q: Too many results**
A: Look for results in data segments (DS), not code segments (CS)

**Q: Debugger is confusing**
A: Essential commands:
- `D address` - Dump memory
- `R` - Show registers
- `F10` - Step over (one instruction)
- `F11` - Step into (follow calls)
- `BP address` - Set breakpoint
- `BPMR address` - Break on memory read
- `G` - Continue execution

## Quick Reference Card

```
Essential Debugger Commands:
SEARCH start end bytes    - Find bytes in memory
D seg:offset             - Display memory
BPMR seg:offset          - Break on memory read
F10                      - Step one instruction
R                        - Show registers
G                        - Continue (go)
Q                        - Quit debugger
```

## Expected Outcome

We should discover ONE of these:
1. Operand 29 gets transformed (29 - 22 = 7, or some other math)
2. Values > 21 trigger alternate lookup tables
3. Values > 21 are special condition IDs (not zone indices at all)
4. The operand is actually checked differently based on context

This will FINALLY solve the mystery! 🎯
