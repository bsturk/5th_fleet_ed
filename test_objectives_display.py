#!/usr/bin/env python3
"""
Test script to verify objective display improvements.
"""

import sys
from pathlib import Path

# Add editor module to path
sys.path.insert(0, str(Path(__file__).parent))

from editor.data import ScenarioFile

def test_scenario_1_objectives():
    """Test that Scenario 1 objectives are displayed correctly."""
    scenario_file = ScenarioFile.load(Path("game/SCENARIO.DAT"))

    if not scenario_file.records:
        print("ERROR: No scenarios found in SCENARIO.DAT")
        return False

    scenario_1 = scenario_file.records[0]

    print("=" * 80)
    print("SCENARIO 1 - Battle of the Maldives")
    print("=" * 80)
    print()

    # Check if objectives text exists
    print("1. Objectives Text from SCENARIO.DAT:")
    print("-" * 80)
    if scenario_1.objectives and scenario_1.objectives.strip():
        print(scenario_1.objectives.strip())
        print()

        # Verify key information is present
        objectives_lower = scenario_1.objectives.lower()
        checks = {
            "Antares mentioned": "antares" in objectives_lower,
            "Capella mentioned": "capella" in objectives_lower,
            "Male Atoll mentioned": "male" in objectives_lower,
            "Destroy/damage airfield": "destroy" in objectives_lower or "damage" in objectives_lower,
            "Indian units mentioned": "indian" in objectives_lower,
        }

        print()
        print("2. Content Verification:")
        print("-" * 80)
        all_passed = True
        for check_name, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check_name}")
            if not passed:
                all_passed = False

        print()
        if all_passed:
            print("✓ All key objective information is present in the objectives text!")
        else:
            print("⚠ Some expected information is missing from objectives text")

        return all_passed
    else:
        print("ERROR: No objectives text found!")
        return False

if __name__ == "__main__":
    success = test_scenario_1_objectives()
    sys.exit(0 if success else 1)
