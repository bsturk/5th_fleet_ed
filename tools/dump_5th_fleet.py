#!/usr/bin/env python3
"""
Quick-and-dirty helpers for inspecting SSI's 5th Fleet scenario data.

The goal is to make it easy to peek at the structure of SCENARIO.DAT and the
scenario-specific *.DAT map files so you have a reliable starting point for a
Python-based editor.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path
from collections import Counter
from typing import Dict, Iterable, List, Tuple

sys.path.append(str(Path(__file__).resolve().parents[1]))

from editor.data import load_template_library

REGION_RECORD_LEN = 65  # observed constant across the scenario *.DAT files
SCENARIO_TEXT_ENCODING = "latin1"  # Turbo Pascal wrote raw bytes; latin1 preserves them
UNIT_POINTER_MAP = {5: "air", 8: "surface", 11: "sub"}
PCX_PANEL_OFFSETS = {0: (184, 0), 1: (48, 8)}


def read_word(data: bytes, offset: int) -> Tuple[int, int]:
    """Return little-endian word at offset and the new offset."""
    value = struct.unpack_from("<H", data, offset)[0]
    return value, offset + 2


def read_cstring_bytes(data: bytes, offset: int) -> Tuple[bytes, int]:
    """Read a NUL-terminated byte string starting at offset."""
    end = data.find(b"\x00", offset)
    if end == -1:
        return data[offset:], len(data)
    return data[offset:end], end + 1


def chunk_pairs(data: bytes, offset: int, count: int) -> List[Tuple[int, int]]:
    """Read `count` little-endian (word, word) pairs starting at offset."""
    pairs = []
    for idx in range(count):
        start = offset + idx * 4
        if start + 4 > len(data):
            break
        pairs.append(struct.unpack_from("<HH", data, start))
    return pairs


def parse_scenario_record(blob: bytes, index: int) -> Dict[str, object]:
    """
    Decode one 5,883-byte scenario block from SCENARIO.DAT.

    The file stores fixed-length character buffers, so each block is littered
    with padding. We keep the parsing defensive and surface any bytes we do not
    currently understand so the editor can preserve them losslessly.
    """

    def decode_text(raw: bytes) -> str:
        return raw.decode(SCENARIO_TEXT_ENCODING, errors="replace").strip()

    record: Dict[str, object] = {"index": index, "raw_length": len(blob)}

    # SECTION 1: narrative strings
    try:
        forces_raw, remainder = blob.split(b"\nOBJECTIVES\n", 1)
        record["forces"] = decode_text(forces_raw)
    except ValueError:
        record["forces"] = decode_text(blob)
        record["parse_warning"] = "OBJECTIVES marker missing"
        return record

    try:
        objectives_raw, remainder = remainder.split(b"\nSPECIAL NOTES\n", 1)
        record["objectives"] = decode_text(objectives_raw)

        notes_end = remainder.find(b"\x00")
        if notes_end == -1:
            record["notes"] = decode_text(remainder)
            remainder = b""
        else:
            record["notes"] = decode_text(remainder[:notes_end])
            remainder = remainder[notes_end + 1 :]
    except ValueError:
        # Some scenarios omit the SPECIAL NOTES section. In that case we keep
        # the remainder as objectives text up to the first NUL and continue.
        split_pos = remainder.find(b"\x00")
        if split_pos == -1:
            record["objectives"] = decode_text(remainder)
            remainder = b""
        else:
            record["objectives"] = decode_text(remainder[:split_pos])
            remainder = remainder[split_pos + 1 :]
        record["notes"] = ""
        record["parse_warning"] = "SPECIAL NOTES marker missing"

    # SECTION 2: metadata strings up until the binary payload.
    metadata_strings: List[str] = []
    remainder = remainder.lstrip(b"\x00")
    while remainder:
        # Binary data kicks in once we hit a control character (<0x20).
        if remainder[0] < 0x20:
            break
        meta_bytes, rel = read_cstring_bytes(remainder, 0)
        metadata_strings.append(
            meta_bytes.decode(SCENARIO_TEXT_ENCODING, errors="replace")
        )
        remainder = remainder[rel:].lstrip(b"\x00")

    record["metadata_strings"] = metadata_strings

    # Everything else is preserved verbatim, but we also surface any embedded
    # printable strings to make hunting for parameters easier.
    printable_sequences = re.findall(rb"[ -~]{3,}", remainder)
    record["printable_sequences"] = [
        seq.decode(SCENARIO_TEXT_ENCODING, errors="replace")
        for seq in printable_sequences
    ]
    record["difficulty"] = next(
        (seq for seq in record["printable_sequences"] if seq.startswith("E")), None
    )

    scenario_key = None
    for seq in record["printable_sequences"]:
        candidate = seq.strip()
        if not candidate or candidate.startswith(")") or candidate.startswith("n-"):
            continue
        if candidate.isalpha():
            scenario_key = candidate
            break
    if not scenario_key:
        for meta in metadata_strings[1:]:
            meta_candidate = meta.strip()
            if meta_candidate and " " not in meta_candidate:
                scenario_key = meta_candidate
                break
    if scenario_key:
        record["scenario_key"] = scenario_key

    record["trailing_bytes_hex"] = remainder.hex()

    return record


def parse_scenario_file(path: Path) -> List[Dict[str, object]]:
    """Load SCENARIO.DAT and decode its ten fixed-size blocks."""
    data = path.read_bytes()
    count, offset = read_word(data, 0)
    if count == 0:
        return []

    payload = data[offset:]
    block_len = len(payload) // count
    records = []
    for idx in range(count):
        start = idx * block_len
        records.append(parse_scenario_record(payload[start : start + block_len], idx))
    return records


def parse_region_block(block: bytes, index: int) -> Dict[str, object]:
    """Decode a single 65-byte region record."""
    region: Dict[str, object] = {"index": index}

    # Region name is first.
    name_bytes, offset = read_cstring_bytes(block, 0)
    region["name"] = name_bytes.decode(SCENARIO_TEXT_ENCODING, errors="replace")

    # Remaining zero-terminated fields contain control codes, adjacency strings,
    # and optional file references. We capture them verbatim and expose helper
    # renders for strings that are obviously ASCII.
    fields: List[Dict[str, object]] = []
    while offset < len(block):
        if len(block) - offset <= 32:
            break
        field_raw, offset = read_cstring_bytes(block, offset)
        fields.append(
            {
                "raw_hex": field_raw.hex(),
                "text": field_raw.decode(SCENARIO_TEXT_ENCODING, errors="replace"),
            }
        )

    region["fields"] = fields

    tail = block[-32:]
    tail_words = list(struct.unpack("<16H", tail))
    region["tail_words"] = tail_words
    label_bytes = tail[:10].rstrip(b"\x00")
    label_text = label_bytes.decode(SCENARIO_TEXT_ENCODING, errors="replace")
    if label_text and all(c.isprintable() for c in label_text) and len(label_text) > 1:
        region["label_hint"] = label_text

    if len(tail) >= 16:
        word5 = tail_words[5]
        word6 = tail_words[6]
        word7 = tail_words[7]
        raw_x = word5 >> 8
        raw_y = word6 >> 8
        raw_width = word7 >> 8
        map_panel = word7 & 0xFF
        region["map_position"] = {
            "panel": map_panel,
            "x_raw": raw_x,
            "y_raw": raw_y,
            "width_raw": raw_width,
            "x_px": raw_x,
            "y_px": raw_y,
            "width_px": raw_width,
        }
        if map_panel in PCX_PANEL_OFFSETS:
            base_x, base_y = PCX_PANEL_OFFSETS[map_panel]
            region["map_position"]["pcx_x"] = base_x + raw_x
            region["map_position"]["pcx_y"] = base_y + raw_y
            region["map_position"]["pcx_width"] = raw_width

    for field in reversed(fields):
        neighbors_raw = field["text"]
        if neighbors_raw and len(neighbors_raw) % 2 == 0 and neighbors_raw.isupper():
            region["adjacent_codes"] = [
                neighbors_raw[i : i + 2] for i in range(0, len(neighbors_raw), 2)
            ]
            break

    return region


def parse_map_file(path: Path) -> Dict[str, object]:
    """Parse a scenario-specific *.DAT map file and surface the parts we know."""
    data = path.read_bytes()
    region_count, _ = read_word(data, 0)

    regions: List[Dict[str, object]] = []
    offset = 2
    for idx in range(region_count):
        block = data[offset : offset + REGION_RECORD_LEN]
        regions.append(parse_region_block(block, idx))
        offset += REGION_RECORD_LEN

    pointer_table_offset = offset
    pointer_pairs = chunk_pairs(data, pointer_table_offset, 16)

    code_to_region: Dict[str, Dict[str, object]] = {}
    for region in regions:
        code = None
        for field in region["fields"]:
            match = re.search(r"rp([A-Z0-9]{2})", field["text"])
            if match:
                code = match.group(1)
                break
        if code:
            region["region_code"] = code
            code_to_region[code] = region

    for region in regions:
        codes = region.get("adjacent_codes", [])
        if codes:
            region["adjacent_regions"] = [
                code_to_region[code]["name"] if code in code_to_region else code
                for code in codes
            ]

    pointer_data_base = pointer_table_offset + len(pointer_pairs) * 4
    abs_entries = sorted(
        (pointer_data_base + start, idx)
        for idx, (start, _count) in enumerate(pointer_pairs)
    )

    next_offset_lookup: Dict[int, int] = {}
    for position, (abs_offset, idx) in enumerate(abs_entries):
        next_abs = len(data)
        for future_abs, _future_idx in abs_entries[position + 1 :]:
            if future_abs > abs_offset:
                next_abs = future_abs
                break
        next_offset_lookup[idx] = next_abs

    template_library = load_template_library(path.parent)

    pointer_table: List[Dict[str, object]] = []
    sections: List[Dict[str, object]] = []
    unit_tables: Dict[str, List[Dict[str, object]]] = {}

    for idx, (start, count) in enumerate(pointer_pairs):
        abs_offset = pointer_data_base + start
        next_abs = next_offset_lookup.get(idx, len(data))
        actual_len = max(0, min(len(data), next_abs) - abs_offset)
        if actual_len == 0:
            actual_len = min(count, len(data) - abs_offset)

        chunk = data[abs_offset : abs_offset + actual_len]
        entry: Dict[str, object] = {
            "index": idx,
            "start": start,
            "count": count,
            "absolute_offset": abs_offset,
            "data_size": len(chunk),
        }
        pointer_table.append(entry)

        if not chunk:
            continue

        ascii_sequences = [
            seq.decode(SCENARIO_TEXT_ENCODING, errors="replace")
            for seq in re.findall(rb"[ -~]{4,}", chunk)
        ]
        ascii_ratio = sum(1 for b in chunk if 32 <= b < 127) / len(chunk)
        classification = "raw_bytes"
        preview: Dict[str, object] = {}

        if idx in UNIT_POINTER_MAP and len(chunk) >= 32:
            classification = "unit_table"
            kind = UNIT_POINTER_MAP[idx]
            templates = template_library.get(kind, [])
            frame_size = 32
            frames = len(chunk) // frame_size
            units: List[Dict[str, object]] = []
            for slot in range(frames):
                frame = chunk[slot * frame_size : (slot + 1) * frame_size]
                words = struct.unpack("<16H", frame)
                template_id = words[0] & 0xFF
                owner_raw = words[0] >> 8
                if template_id >= len(templates):
                    continue
                region_index = words[1]
                region_name = regions[region_index]["name"] if 0 <= region_index < len(regions) else None
                side = owner_raw & 0x03
                units.append(
                    {
                        "slot": slot,
                        "template_id": template_id,
                        "template_name": templates[template_id].name,
                        "template_icon": templates[template_id].icon_index,
                        "owner_raw": owner_raw,
                        "side": side,
                        "region_index": region_index,
                        "region_name": region_name,
                        "tile_x": words[2],
                        "tile_y": words[3],
                        "raw_words": words[:8],
                    }
                )
            unit_tables[kind] = units
            preview["unit_count"] = len(units)
            template_counter = Counter(
                unit["template_name"] for unit in units
            )
            preview["top_templates"] = template_counter.most_common(5)
            side_counter = Counter(unit["side"] for unit in units)
            preview["side_counts"] = sorted(side_counter.items())
            region_counter = Counter(
                unit["region_name"] or unit["region_index"] for unit in units if unit["region_index"] is not None
            )
            preview["top_regions"] = region_counter.most_common(5)
        elif ascii_ratio > 0.5:
            classification = "string_block"
            preview["strings"] = ascii_sequences[:20]
        elif len(chunk) % 2 == 0:
            words = list(struct.unpack_from("<" + "H" * (len(chunk) // 2), chunk))
            preview["words"] = words[:32]
            if words and all(w < region_count + 10 for w in words[:20]):
                classification = "index_words"
                preview["pairs"] = [
                    {"from": words[i], "to": words[i + 1]}
                    for i in range(0, min(len(words) - 1, 20), 2)
                ]
            if ascii_sequences:
                preview["strings"] = ascii_sequences[:10]
        else:
            preview["bytes_hex"] = chunk[:64].hex()
            if ascii_sequences:
                preview["strings"] = ascii_sequences[:10]

        entry["classification"] = classification
        entry["preview"] = preview
        sections.append(
            {
                "index": idx,
                "classification": classification,
                "offset": abs_offset,
                "size": len(chunk),
                "preview": preview,
            }
        )

    return {
        "file": path.name,
        "region_count": region_count,
        "regions": regions,
        "pointer_table": pointer_table,
        "sections": sections,
        "unit_tables": unit_tables,
        "remaining_bytes": len(data) - pointer_table_offset - len(pointer_pairs) * 4,
    }


def summarise_scenarios(records: Iterable[Dict[str, object]]) -> str:
    lines = []
    for record in records:
        metadata_strings = record.get("metadata_strings", [])
        title = metadata_strings[0] if metadata_strings else "<untitled>"
        lines.append(f"[{record['index']}] {title}")
        difficulty = record.get("difficulty") or (
            record.get("printable_sequences", [None])[0] or "?"
        )
        scenario_key = record.get("scenario_key", "")
        lines.append(f"  Difficulty : {difficulty}")
        lines.append(f"  Key        : {scenario_key}")
        forces = record.get("forces", "")
        if forces:
            lines.append(f"  Forces     : {forces.splitlines()[0][:80]}")
        objectives = record.get("objectives", "")
        if objectives:
            lines.append(f"  Objectives : {objectives.splitlines()[0][:80]}")
        lines.append("")
    return "\n".join(lines)


def summarise_map(map_info: Dict[str, object]) -> str:
    lines = [
        f"{map_info['file']} — {map_info['region_count']} regions, "
        f"{len(map_info['pointer_table'])} pointer entries",
        "",
    ]
    for region in map_info["regions"]:
        lines.append(f"[{region['index']:02}] {region['name']}")
        if "adjacent_codes" in region:
            lines.append(f"     Adjacent: {', '.join(region['adjacent_codes'])}")
        if "adjacent_regions" in region:
            lines.append(f"     Adjacent names: {', '.join(region['adjacent_regions'])}")
        position = region.get("map_position")
        if position:
            lines.append(
                f"     Map pos : panel {position['panel']}, "
                f"x {position['x_raw']} (px {position['x_px']:.1f}), "
                f"y {position['y_raw']} (px {position['y_px']:.1f}), "
                f"width {position['width_raw']} (px {position['width_px']:.1f})"
            )
        if region.get("label_hint"):
            lines.append(f"     Label   : {region['label_hint']}")
    lines.append("")
    lines.append("Pointer sections:")
    for section in map_info.get("sections", []):
        lines.append(
            f"  [{section['index']:02}] {section['classification']} "
            f"@{section['offset']} ({section['size']} bytes)"
        )
        preview = section.get("preview", {})
        if section["classification"] == "unit_table":
            unit_count = preview.get("unit_count", 0)
            top = preview.get("top_templates", [])
            lines.append(f"       units: {unit_count}")
            if top:
                formatted = ", ".join(f"{name}×{count}" for name, count in top)
                lines.append(f"       top: {formatted}")
            side_counts = preview.get("side_counts", [])
            if side_counts:
                side_fmt = ", ".join(f"side{side}×{count}" for side, count in side_counts)
                lines.append(f"       sides: {side_fmt}")
            kind = UNIT_POINTER_MAP.get(section["index"])
            if kind:
                sample_units = map_info.get("unit_tables", {}).get(kind, [])[:5]
                if sample_units:
                    sample_fmt = "; ".join(
                        f"{unit['template_name']}@{unit['region_name'] or unit['region_index']} (side {unit['side']})"
                        for unit in sample_units
                    )
                    lines.append(f"       sample: {sample_fmt}")
        elif "strings" in preview:
            sample = ", ".join(preview["strings"][:5])
            lines.append(f"       strings: {sample}")
        elif "pairs" in preview:
            sample = preview["pairs"][:5]
            lines.append(f"       pairs: {sample}")
        elif "words" in preview:
            lines.append(f"       words: {preview['words'][:10]}")
    unit_tables = map_info.get("unit_tables", {})
    if unit_tables:
        lines.append("")
        lines.append("Order of battle overview:")
        for kind, units in unit_tables.items():
            template_counts = Counter(unit["template_name"] for unit in units)
            side_counts = Counter(unit["side"] for unit in units)
            template_fmt = ", ".join(
                f"{name}×{count}" for name, count in template_counts.most_common(5)
            )
            side_fmt = ", ".join(f"side{side}×{count}" for side, count in sorted(side_counts.items()))
            lines.append(
                f"  {kind.capitalize():<7}: {len(units)} units ({template_fmt}) [sides: {side_fmt}]"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect scenario and map data from SSI's 5th Fleet."
    )
    parser.add_argument("--scenario", type=Path, help="Path to SCENARIO.DAT")
    parser.add_argument("--map", type=Path, help="Path to a scenario *.DAT file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of the human-readable summaries.",
    )
    args = parser.parse_args()

    output: Dict[str, object] = {}

    if args.scenario:
        records = parse_scenario_file(args.scenario)
        output["scenario_records"] = records
        if not args.json:
            print(summarise_scenarios(records))

    if args.map:
        map_info = parse_map_file(args.map)
        output["map"] = map_info
        if not args.json:
            print(summarise_map(map_info))

    if args.json:
        print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
