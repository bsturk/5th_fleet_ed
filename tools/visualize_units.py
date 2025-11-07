#!/usr/bin/env python3
"""
Visualize unit placements from 5th Fleet scenario files.

This tool creates a visual representation of where units are placed on the map,
helping to understand the coordinate system used for tactical placement.
"""

from pathlib import Path
from editor.data import MapFile
from PIL import Image, ImageDraw, ImageFont
import sys


def visualize_unit_placements(map_path: Path, output_path: Path):
    """Create a visualization of unit placements on the strategic map."""

    # Load the map file
    map_file = MapFile.load(map_path)

    # Load the strategic map
    mapver20_path = map_path.parent / "MAPVER20.PCX"
    if not mapver20_path.exists():
        print(f"Error: MAPVER20.PCX not found at {mapver20_path}")
        return

    map_image = Image.open(mapver20_path)
    print(f"Loaded map: {map_image.size}")

    # Create a copy for annotation
    annotated = map_image.copy()
    draw = ImageDraw.Draw(annotated)

    # Colors for each side
    side_colors = {
        0: (0, 255, 0),      # Green
        1: (255, 0, 0),      # Red
        2: (0, 0, 255),      # Blue
        3: (255, 255, 0),    # Yellow
    }

    # Collect all valid units
    unit_count = 0
    for kind in ['air', 'surface', 'sub']:
        if kind not in map_file.unit_tables:
            continue

        units = [u for u in map_file.unit_tables[kind].units if u.region_index < 22]

        for unit in units:
            side = unit.owner_raw & 0x03
            color = side_colors[side]
            region = map_file.regions[unit.region_index]

            # Try different coordinate interpretations
            word2 = unit.raw_words[2]
            word3 = unit.raw_words[3]

            # Interpretation 1: If low byte is 0, use high byte as hex coordinate
            if (word2 & 0xFF) == 0 and (word3 & 0xFF) == 0:
                x = word2 >> 8
                y = word3 >> 8
                # Scale to map (rough estimate - hex grid to pixel)
                # Assuming ~100 hexes across the map width
                pixel_x = int((x / 100) * map_image.width)
                pixel_y = int((y / 100) * map_image.height)
                marker_type = "hex"
            else:
                # Interpretation 2: Full word as coordinate
                # These might already be pixel coordinates or need different scaling
                x = word2
                y = word3

                # Try as hex coordinates
                if x < 200 and y < 200:  # Reasonable hex range
                    pixel_x = int((x / 100) * map_image.width)
                    pixel_y = int((y / 100) * map_image.height)
                    marker_type = "small"
                else:
                    # Might be pixel coordinates or encoded differently
                    # Skip for now
                    continue

            # Bounds check
            if 0 <= pixel_x < map_image.width and 0 <= pixel_y < map_image.height:
                # Draw unit marker
                size = 8 if kind == 'air' else 6
                draw.ellipse([pixel_x-size, pixel_y-size, pixel_x+size, pixel_y+size],
                           fill=color, outline=(255, 255, 255), width=1)
                unit_count += 1

    print(f"Plotted {unit_count} units")

    # Add legend
    legend_x = 10
    legend_y = 10
    draw.rectangle([legend_x, legend_y, legend_x+200, legend_y+120],
                   fill=(0, 0, 0), outline=(255, 255, 255), width=2)

    draw.text((legend_x+10, legend_y+10), "Unit Placements", fill=(255, 255, 255))
    for i, (name, color) in enumerate([("Green", side_colors[0]), ("Red", side_colors[1]),
                                        ("Blue", side_colors[2]), ("Yellow", side_colors[3])]):
        y = legend_y + 30 + i*20
        draw.ellipse([legend_x+10, y, legend_x+18, y+8], fill=color, outline=(255, 255, 255))
        draw.text((legend_x+25, y), name, fill=(255, 255, 255))

    # Save
    # Scale down for viewing
    scale = 0.5
    small_size = (int(annotated.width * scale), int(annotated.height * scale))
    annotated_small = annotated.resize(small_size, Image.LANCZOS)
    annotated_small.save(output_path)
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visualize_units.py <MAP_FILE> [OUTPUT_FILE]")
        print("Example: python visualize_units.py game/MALDIVE.DAT /tmp/maldive_units.png")
        sys.exit(1)

    map_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/unit_placements.png")

    visualize_unit_placements(map_path, output_path)
