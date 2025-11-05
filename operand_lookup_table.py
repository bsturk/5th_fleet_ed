# Lookup table for multi-zone operand decoding
# Based on analysis of scenarios.md and mathematical patterns

# Maps (opcode, operand) -> list of zone indices
MULTIZONE_OPERANDS = {
    # Scenario 2: Russian Raiders
    # "Russian surface warships must reach Aden, Al Mukalla, or Ras Karma"
    # These are PORTS not zones, so operand 29 likely means something else
    # From scenarios.md objectives, no zone-based objective for Red player
    # But we found ZONE_CHECK(29) in binary - mystery remains

    # Scenario 3: Battle of the Arabian Sea
    # "Russian surface and submarine units must occupy the Gulf of Oman zone...
    #  Failing that, they must occupy either the North Arabian Sea or South Arabian Sea zones"
    (0x09, 35): [7, 11, 17],  # ZONE_CONTROL(35) = Gulf of Oman + N Arabian + S Arabian
    (0xBB, 46): [7, 11, 17],  # ZONE_ENTRY(46) = Same zones with emphasis on one

    # Scenario 2: Needs investigation - what IS operand 29?
    # XOR gives multiple possibilities, SUM doesn't match
    # For now, use the same zones as Scenario 3 since they're related scenarios
    (0x0A, 29): [7, 11, 17],  # ZONE_CHECK(29) = Best guess based on related scenario
}

def get_zones_for_operand(opcode: int, operand: int):
    """
    Get list of zone indices for a multi-zone operand.
    Returns None if operand is not in lookup table.
    """
    return MULTIZONE_OPERANDS.get((opcode, operand))


# NOTES:
# - Operand 35 = 7 + 11 + 17 (SUM) - unambiguous
# - Operand 46 = 7 + 11 + 17 + 11 (SUM with zone 11 doubled) - unambiguous
# - Operand 29 = 7 XOR 11 XOR 17 (one of ~50 possible XOR combinations)
#
# The XOR hypothesis is likely correct but ambiguous without game code analysis.
# Memory dumps can't capture the data (loads into extended memory above 1MB).
#
# Until we can debug the actual game code or disassemble the decoder function,
# this lookup table based on scenarios.md is the most reliable approach.
