from __future__ import annotations

import dataclasses
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SCENARIO_TEXT_ENCODING = "latin1"
SCENARIO_BLOCK_SIZE = 5883  # observed from SCENARIO.DAT reverse engineering
REGION_RECORD_LEN = 65
UNIT_POINTER_MAP = {5: "air", 8: "surface", 11: "sub"}
UNIT_FRAME_WORDS = 16
UNIT_FRAME_SIZE = UNIT_FRAME_WORDS * 2
TEMPLATE_ICON_OFFSETS = {
    "TRMAIR.DAT": (33, 1),
    "TRMSRF.DAT": (114, 2),
    "TRMSUB.DAT": (None, 1),  # Icon offset unknown - byte 26 was reading text data
}


def _read_word(data: bytes, offset: int) -> Tuple[int, int]:
    value = struct.unpack_from("<H", data, offset)[0]
    return value, offset + 2


def _read_cstring_bytes(data: bytes, offset: int) -> Tuple[bytes, int]:
    end = data.find(b"\x00", offset)
    if end == -1:
        return data[offset:], len(data)
    return data[offset:end], end + 1


@dataclass
class MetadataEntry:
    text: str
    extra_zero_count: int = 0  # number of NUL bytes following the terminator

    def to_bytes(self) -> bytes:
        encoded = self.text.encode(SCENARIO_TEXT_ENCODING, errors="replace")
        return encoded + b"\x00" + (b"\x00" * self.extra_zero_count)


@dataclass
class ScenarioRecord:
    index: int
    forces: str
    objectives: str
    notes: str
    metadata_entries: List[MetadataEntry] = field(default_factory=list)
    metadata_leading_zeros: int = 0
    trailing_bytes: bytes = b""
    has_special_notes_marker: bool = True
    block_size: int = SCENARIO_BLOCK_SIZE
    raw_block: Optional[bytes] = None
    scenario_key: Optional[str] = None
    difficulty_token: Optional[str] = None

    def metadata_strings(self) -> List[str]:
        return [entry.text for entry in self.metadata_entries]

    def set_metadata_strings(self, strings: Iterable[str]) -> None:
        strings = list(strings)
        if len(strings) != len(self.metadata_entries):
            self.metadata_entries = [MetadataEntry(text=s) for s in strings]
        else:
            for entry, text in zip(self.metadata_entries, strings):
                entry.text = text

    def to_bytes(self) -> bytes:
        """Serialise the record back into its 5,883-byte block."""
        if self.raw_block is not None:
            # Unparsed block; return as-is to preserve integrity.
            if len(self.raw_block) != self.block_size:
                raise ValueError(
                    f"Raw scenario block size mismatch ({len(self.raw_block)} != {self.block_size})"
                )
            return bytes(self.raw_block)
        parts: List[bytes] = []

        def encode(text: str) -> bytes:
            return text.encode(SCENARIO_TEXT_ENCODING, errors="replace")

        parts.append(encode(self.forces))
        parts.append(b"\nOBJECTIVES\n")
        parts.append(encode(self.objectives))

        if self.has_special_notes_marker:
            parts.append(b"\nSPECIAL NOTES\n")
            parts.append(encode(self.notes))
        else:
            # Legacy scenarios without the marker kept notes folded into objectives.
            # We still allow editing by appending the raw notes text (if any).
            if self.notes:
                parts.append(encode(self.notes))

        parts.append(b"\x00")

        parts.append(b"\x00" * self.metadata_leading_zeros)
        for entry in self.metadata_entries:
            parts.append(entry.to_bytes())

        parts.append(self.trailing_bytes)

        block = b"".join(parts)
        if len(block) > self.block_size:
            raise ValueError(
                f"Scenario block overflow: {len(block)} bytes (limit {self.block_size})"
            )
        if len(block) < self.block_size:
            block += b"\x00" * (self.block_size - len(block))
        return block


@dataclass
class ScenarioFile:
    path: Optional[Path]
    records: List[ScenarioRecord]

    @property
    def scenario_count(self) -> int:
        return len(self.records)

    @classmethod
    def load(cls, path: Path) -> "ScenarioFile":
        data = path.read_bytes()
        count, offset = _read_word(data, 0)
        if count <= 0:
            return cls(path=path, records=[])
        payload = data[offset:]
        block_len = len(payload) // count
        records: List[ScenarioRecord] = []
        for idx in range(count):
            start = idx * block_len
            block = payload[start : start + block_len]
            records.append(parse_scenario_block(block, index=idx))
        return cls(path=path, records=records)

    def save(self, path: Optional[Path] = None) -> None:
        target = path or self.path
        if target is None:
            raise ValueError("No path supplied for saving ScenarioFile.")
        buffer = bytearray()
        buffer.extend(struct.pack("<H", len(self.records)))
        for record in self.records:
            buffer.extend(record.to_bytes())
        target.write_bytes(bytes(buffer))


def parse_scenario_block(block: bytes, index: int) -> ScenarioRecord:
    def decode(raw: bytes) -> str:
        decoded = raw.decode(SCENARIO_TEXT_ENCODING, errors="replace")
        # Strip trailing non-printable characters (but preserve internal whitespace)
        return decoded.rstrip('\x00\xf0\xff')

    record = ScenarioRecord(
        index=index,
        forces="",
        objectives="",
        notes="",
        metadata_entries=[],
        metadata_leading_zeros=0,
        trailing_bytes=b"",
        has_special_notes_marker=True,
        block_size=len(block),
        raw_block=None,
    )

    try:
        # Try standard format first
        if b"\nOBJECTIVES\n" in block:
            forces_raw, remainder = block.split(b"\nOBJECTIVES\n", 1)
        # Try variant with trailing space (some scenarios have this)
        elif b"\nOBJECTIVES \n" in block:
            forces_raw, remainder = block.split(b"\nOBJECTIVES \n", 1)
        else:
            raise ValueError("No OBJECTIVES marker found")
        record.forces = decode(forces_raw)
    except ValueError:
        record.raw_block = bytes(block)
        record.forces = decode(block)
        record.has_special_notes_marker = False
        record.objectives = ""
        record.notes = ""
        record.trailing_bytes = b""
        return record

    if b"\nSPECIAL NOTES\n" in remainder:
        objectives_raw, remainder = remainder.split(b"\nSPECIAL NOTES\n", 1)
        record.objectives = decode(objectives_raw)
        notes_end = remainder.find(b"\x00")
        if notes_end == -1:
            record.notes = decode(remainder)
            remainder = b""
        else:
            record.notes = decode(remainder[:notes_end])
            remainder = remainder[notes_end + 1 :]
    else:
        record.has_special_notes_marker = False
        split_pos = remainder.find(b"\x00")
        if split_pos == -1:
            record.objectives = decode(remainder)
            remainder = b""
        else:
            record.objectives = decode(remainder[:split_pos])
            remainder = remainder[split_pos + 1 :]
        record.notes = ""

    # Track leading zeros before metadata strings.
    metadata_leading_zeros = 0
    while metadata_leading_zeros < len(remainder) and remainder[metadata_leading_zeros] == 0:
        metadata_leading_zeros += 1
    record.metadata_leading_zeros = metadata_leading_zeros
    cursor = metadata_leading_zeros

    metadata_entries: List[MetadataEntry] = []
    while cursor < len(remainder):
        first = remainder[cursor]
        if first < 0x20:
            break
        segment, cursor = _read_cstring_bytes(remainder, cursor)
        extra_zeros = 0
        while cursor < len(remainder) and remainder[cursor] == 0:
            extra_zeros += 1
            cursor += 1
        metadata_entries.append(
            MetadataEntry(
                text=segment.decode(SCENARIO_TEXT_ENCODING, errors="replace"),
                extra_zero_count=extra_zeros,
            )
        )

    record.metadata_entries = metadata_entries
    record.trailing_bytes = remainder[cursor:]

    printable_sequences = re.findall(rb"[ -~]{3,}", record.trailing_bytes)

    # Look for difficulty: "Low", "Medium", "High", or "ELow", "EMedium", "EHigh" etc.
    record.difficulty_token = next(
        (
            seq.decode(SCENARIO_TEXT_ENCODING, errors="replace")
            for seq in printable_sequences
            if re.match(rb"^E?(Low|Medium|High)", seq)
        ),
        None,
    )

    # Look for scenario key (alphabetic string, but skip known non-key strings)
    skip_strings = {b"5th Fleet", b"Low", b"Medium", b"High", b"ELow", b"EMedium", b"EHigh"}
    for seq in printable_sequences:
        text = seq.decode(SCENARIO_TEXT_ENCODING, errors="replace").strip()
        if text and text.isalpha() and seq not in skip_strings:
            record.scenario_key = text
            break

    return record


def create_blank_scenario(index: int) -> ScenarioRecord:
    """Return a minimal scenario record ready for editing."""
    forces = "FORCES\nGreen Player:\nRed Player:"
    objectives = "OBJECTIVES\nGreen Player:\nRed Player:"
    notes = ""
    metadata_entries = [MetadataEntry(text=f"Scenario {index + 1}", extra_zero_count=0)]
    trailing_bytes = b"\x00" * 56
    return ScenarioRecord(
        index=index,
        forces=forces,
        objectives=objectives,
        notes=notes,
        metadata_entries=metadata_entries,
        metadata_leading_zeros=0,
        trailing_bytes=trailing_bytes,
        has_special_notes_marker=True,
        block_size=SCENARIO_BLOCK_SIZE,
    )


@dataclass
class RegionField:
    raw: bytes
    has_trailing_null: bool

    def text(self) -> str:
        return self.raw.decode(SCENARIO_TEXT_ENCODING, errors="replace")

    def set_text(self, value: str) -> None:
        self.raw = value.encode(SCENARIO_TEXT_ENCODING, errors="replace")


@dataclass
class MapRegion:
    index: int
    name: str
    fields: List[RegionField]
    tail_words: List[int]
    tail_data_start: int = 33  # Byte offset where tail_words actually start (33 if no overflow)
    adjacency_field_index: Optional[int] = None
    region_code_field_index: Optional[int] = None

    def region_code(self) -> Optional[str]:
        if self.region_code_field_index is None:
            return None
        return _find_region_code(self.fields[self.region_code_field_index].text())

    def map_position(self) -> Optional[Dict[str, int]]:
        if len(self.tail_words) < 8:
            return None
        word5 = self.tail_words[5]
        word6 = self.tail_words[6]
        word7 = self.tail_words[7]
        return {
            "panel": word7 & 0xFF,
            "x_raw": word5 >> 8,
            "y_raw": word6 >> 8,
            "width_raw": word7 >> 8,
        }

    def set_map_position(self, panel: int, x_raw: int, y_raw: int, width_raw: int) -> None:
        while len(self.tail_words) < 8:
            self.tail_words.append(0)
        self.tail_words[5] = (x_raw & 0xFF) << 8 | (self.tail_words[5] & 0xFF)
        self.tail_words[6] = (y_raw & 0xFF) << 8 | (self.tail_words[6] & 0xFF)
        self.tail_words[7] = ((width_raw & 0xFF) << 8) | (panel & 0xFF)

    def adjacent_codes(self) -> List[str]:
        idx = self.adjacency_field_index
        if idx is None:
            return []
        text = self.fields[idx].text()
        if not text:
            return []
        if len(text) % 2 != 0:
            return []
        return [text[i : i + 2] for i in range(0, len(text), 2)]

    def set_adjacent_codes(self, codes: Iterable[str]) -> None:
        idx = self.adjacency_field_index
        if idx is None:
            return
        merged = "".join(code.upper() for code in codes)
        self.fields[idx].set_text(merged)

    def to_bytes(self) -> bytes:
        """
        Reconstruct the 65-byte region record.

        Layout:
        - Bytes 0-32: Header (name + fields, may have partial field at end)
        - Bytes 33-64: Tail (may start with field continuation, then tail_words)
        """
        header_limit = REGION_RECORD_LEN - 32  # 33 bytes

        # Build header and collect any overflow
        header = bytearray()
        header.extend(self.name.encode(SCENARIO_TEXT_ENCODING, errors="replace"))
        header.append(0)

        tail_overflow = bytearray()  # Field bytes that overflow into tail

        for field in self.fields:
            field_start = len(header)
            field_data = bytearray(field.raw)
            if field.has_trailing_null:
                field_data.append(0)

            # Check if this field will overflow the header
            if field_start + len(field_data) > header_limit:
                # Split field: put what fits in header, rest in tail overflow
                header_space = header_limit - field_start
                if header_space > 0:
                    header.extend(field_data[:header_space])
                    tail_overflow.extend(field_data[header_space:])
                else:
                    # No space in header, entire field goes to tail overflow
                    tail_overflow.extend(field_data)
                break  # No more fields can fit
            else:
                header.extend(field_data)

        # Pad header to exactly 33 bytes
        while len(header) < header_limit:
            header.append(0)

        # Build tail section
        tail = bytearray()

        # Add field overflow first (if any)
        tail.extend(tail_overflow)

        # Calculate where tail_words should start
        # tail_data_start is absolute offset (33+), so tail offset is relative
        tail_words_offset = self.tail_data_start - header_limit

        # Add padding between field overflow and tail_words if needed
        while len(tail) < tail_words_offset:
            tail.append(0)

        # Add tail_words
        tail_words_bytes = struct.pack("<" + "H" * len(self.tail_words), *self.tail_words)
        tail.extend(tail_words_bytes)

        # Pad or truncate tail to exactly 32 bytes
        while len(tail) < 32:
            tail.append(0)
        tail = tail[:32]

        return bytes(header + tail)

    def clone(self) -> "MapRegion":
        return MapRegion(
            index=self.index,
            name=self.name,
            fields=[
                RegionField(raw=bytes(field.raw), has_trailing_null=field.has_trailing_null)
                for field in self.fields
            ],
            tail_words=list(self.tail_words),
            tail_data_start=self.tail_data_start,
            adjacency_field_index=self.adjacency_field_index,
            region_code_field_index=self.region_code_field_index,
        )


def _find_region_code(text: str) -> Optional[str]:
    match = re.search(r"rp([A-Z0-9]{2})", text)
    if match:
        return match.group(1)
    return None


@dataclass
class PointerEntry:
    index: int
    start: int
    count: int
    data: bytearray
    length: int

    def classification(self) -> str:
        if self.index in UNIT_POINTER_MAP and len(self.data) >= UNIT_FRAME_SIZE:
            return "unit_table"
        return "raw_bytes"

    def clone(self) -> "PointerEntry":
        return PointerEntry(
            index=self.index,
            start=self.start,
            count=self.count,
            data=bytearray(self.data),
            length=self.length,
        )


@dataclass
class UnitRecord:
    slot: int
    template_id: int
    owner_raw: int
    region_index: int
    tile_x: int
    tile_y: int
    raw_words: List[int] = field(default_factory=list)
    template_icon: Optional[int] = None

    def encode(self) -> bytes:
        words = list(self.raw_words) if self.raw_words else [0] * UNIT_FRAME_WORDS
        if len(words) < UNIT_FRAME_WORDS:
            words.extend([0] * (UNIT_FRAME_WORDS - len(words)))
        words[0] = (self.owner_raw << 8) | (self.template_id & 0xFF)
        words[1] = self.region_index & 0xFFFF
        words[2] = self.tile_x & 0xFFFF
        words[3] = self.tile_y & 0xFFFF
        return struct.pack("<" + "H" * UNIT_FRAME_WORDS, *words[:UNIT_FRAME_WORDS])


@dataclass
class UnitTable:
    kind: str
    pointer_entry: PointerEntry
    units: List[UnitRecord]
    max_slots: int

    def rebuild_chunk(self) -> bytes:
        # Build a mapping of slot -> unit
        unit_by_slot = {unit.slot: unit for unit in self.units}

        chunks = []
        for slot in range(self.max_slots):
            if slot in unit_by_slot:
                chunk = unit_by_slot[slot].encode()
            else:
                chunk = b"\x00" * UNIT_FRAME_SIZE
            chunks.append(chunk)
        return b"".join(chunks)

    def sync_to_pointer(self) -> None:
        encoded = self.rebuild_chunk()
        if len(encoded) != len(self.pointer_entry.data):
            raise ValueError(
                f"{self.kind} unit table size mismatch: {len(encoded)} vs {len(self.pointer_entry.data)}"
            )
        self.pointer_entry.data[:] = encoded

    def add_unit(self, unit: UnitRecord) -> None:
        if len(self.units) >= self.max_slots:
            raise ValueError(f"No free slots available in {self.kind} unit table.")

        # Find the first available slot
        used_slots = {u.slot for u in self.units}
        for slot in range(self.max_slots):
            if slot not in used_slots:
                unit.slot = slot
                break
        else:
            # This shouldn't happen if len check above is correct, but be safe
            raise ValueError(f"No free slots available in {self.kind} unit table.")

        unit.raw_words = unit.raw_words or [0] * UNIT_FRAME_WORDS
        self.units.append(unit)

    def remove_unit(self, slot: int) -> None:
        # Remove the unit with the specified slot, preserving other slot numbers
        self.units = [unit for unit in self.units if unit.slot != slot]


@dataclass
class PositionEntry:
    start: int
    end: int
    tile_x_raw: int
    tile_y_raw: int
    panel: int
    flags: int
    region_code: int

    def region_hint(self) -> Optional[int]:
        value = self.region_code & 0xFF
        return value if value != 0xFF else None

    def hex_x(self) -> int:
        if self.tile_x_raw == 0:
            return 0
        if self.tile_x_raw % 256 == 0:
            return self.tile_x_raw // 256
        return self.tile_x_raw


@dataclass
class MapFile:
    path: Optional[Path]
    regions: List[MapRegion]
    pointer_entries: List[PointerEntry]
    unit_tables: Dict[str, UnitTable]
    pointer_blob: bytearray
    template_library: Dict[str, List[TemplateRecord]] = field(default_factory=dict)
    position_entries: List["PositionEntry"] = field(default_factory=list)

    @property
    def region_count(self) -> int:
        return len(self.regions)

    @classmethod
    def load(cls, path: Path, template_library: Optional[Dict[str, List[TemplateRecord]]] = None) -> "MapFile":
        data = path.read_bytes()
        region_count, offset = _read_word(data, 0)
        regions: List[MapRegion] = []
        cursor = offset
        for index in range(region_count):
            block = data[cursor : cursor + REGION_RECORD_LEN]
            regions.append(parse_region_block(block, index))
            cursor += REGION_RECORD_LEN

        pointer_table_offset = cursor
        pointer_pairs: List[Tuple[int, int]] = []
        for idx in range(16):
            start, cursor = _read_word(data, pointer_table_offset + idx * 4)
            count, cursor = _read_word(data, pointer_table_offset + idx * 4 + 2)
            pointer_pairs.append((start, count))
        pointer_data_base = pointer_table_offset + 16 * 4
        pointer_blob = bytearray(data[pointer_data_base:])
        pointer_entries = []

        # Load templates from the map file's directory if not provided
        if template_library is None:
            template_library = load_template_library(path.parent)

        # Determine actual chunk extents by looking at next start.
        abs_entries = sorted(
            (pointer_data_base + start, idx) for idx, (start, _count) in enumerate(pointer_pairs)
        )
        next_lookup: Dict[int, int] = {}
        for pos, (abs_offset, idx) in enumerate(abs_entries):
            next_abs = len(data)
            for future_abs, _future_idx in abs_entries[pos + 1 :]:
                if future_abs > abs_offset:
                    next_abs = future_abs
                    break
            next_lookup[idx] = next_abs

        for idx, (start, count) in enumerate(pointer_pairs):
            abs_offset = pointer_data_base + start
            limit = next_lookup.get(idx, len(data))
            chunk = bytes(data[abs_offset:limit])
            pointer_entries.append(
                PointerEntry(
                    index=idx,
                    start=start,
                    count=count,
                    data=bytearray(chunk),
                    length=len(chunk),
                )
            )

        unit_tables: Dict[str, UnitTable] = {}
        position_entries: List[PositionEntry] = []
        position_struct = struct.Struct("<HHHBBBH")
        pointer_entry_14 = next((entry for entry in pointer_entries if entry.index == 14), None)
        if pointer_entry_14 and len(pointer_entry_14.data) >= position_struct.size:
            blob = pointer_entry_14.data
            count = len(blob) // position_struct.size
            for idx in range(count):
                start, end, tile_x_raw, tile_y_raw, panel, flags, region_code = position_struct.unpack_from(
                    blob, idx * position_struct.size
                )
                position_entries.append(
                    PositionEntry(
                        start=start,
                        end=end,
                        tile_x_raw=tile_x_raw,
                        tile_y_raw=tile_y_raw,
                        panel=panel,
                        flags=flags,
                        region_code=region_code,
                    )
                )
            position_entries.sort(key=lambda record: record.start)

        for entry in pointer_entries:
            kind = UNIT_POINTER_MAP.get(entry.index)
            if not kind:
                continue
            units = parse_unit_table(entry.data)
            templates = template_library.get(kind, [])

            # Filter out units with invalid template_ids (these are empty/unused slots)
            # The game uses template_id >= len(templates) to mark unused slots
            valid_units = []
            for unit in units:
                if 0 <= unit.template_id < len(templates):
                    unit.template_icon = templates[unit.template_id].icon_index
                    valid_units.append(unit)

            unit_tables[kind] = UnitTable(
                kind=kind,
                pointer_entry=entry,
                units=valid_units,
                max_slots=len(entry.data) // UNIT_FRAME_SIZE,
            )

        return cls(
            path=path,
            regions=regions,
            pointer_entries=pointer_entries,
            unit_tables=unit_tables,
            pointer_blob=pointer_blob,
            template_library=template_library,
            position_entries=position_entries,
        )

    def save(self, path: Optional[Path] = None) -> None:
        target = path or self.path
        if target is None:
            raise ValueError("No path supplied for saving MapFile.")

        # Ensure unit tables are serialised back into their pointer entries.
        for unit_table in self.unit_tables.values():
            unit_table.sync_to_pointer()

        buffer = bytearray()
        buffer.extend(struct.pack("<H", len(self.regions)))
        for region in self.regions:
            buffer.extend(region.to_bytes())

        pointer_table_bytes = bytearray()
        for entry in self.pointer_entries:
            pointer_table_bytes.extend(struct.pack("<HH", entry.start, entry.count))
        buffer.extend(pointer_table_bytes)

        pointer_blob = bytearray(self.pointer_blob)
        for entry in self.pointer_entries:
            chunk = bytes(entry.data)
            if len(chunk) != entry.length:
                raise ValueError(
                    f"Pointer entry {entry.index} length changed ({len(chunk)} -> {entry.length}); resizing not supported."
                )
            start = entry.start
            end = start + entry.length
            if end > len(pointer_blob):
                raise ValueError(
                    f"Pointer entry {entry.index} exceeds pointer blob bounds ({end} > {len(pointer_blob)})."
                )
            pointer_blob[start:end] = chunk
        buffer.extend(pointer_blob)
        target.write_bytes(bytes(buffer))

    def resolve_position_slot(self, slot: int) -> Optional[Tuple[PositionEntry, int]]:
        if not self.position_entries:
            return None
        left, right = 0, len(self.position_entries) - 1
        while left <= right:
            mid = (left + right) // 2
            entry = self.position_entries[mid]
            if slot < entry.start:
                right = mid - 1
            elif slot > entry.end:
                left = mid + 1
            else:
                return entry, mid
        return None


def parse_region_block(block: bytes, index: int) -> MapRegion:
    header_len = REGION_RECORD_LEN - 32  # 33 bytes
    header = block[:header_len]
    name_end = header.find(b"\x00")
    if name_end == -1:
        name_bytes = header.rstrip(b"\x00")
        cursor = len(name_bytes)
    else:
        name_bytes = header[:name_end]
        cursor = name_end + 1

    fields: List[RegionField] = []
    tail_data_start = header_len  # Track where tail data actually starts

    while cursor < header_len:
        next_zero = header.find(b"\x00", cursor)
        if next_zero == -1:
            # Field runs to end of header - check if it continues into tail
            field_bytes = header[cursor:]
            cursor = header_len
            has_null = False

            # If last field doesn't end with NUL and tail starts with printable char,
            # the field spans into the tail section (common pattern in adjacency fields)
            if field_bytes and field_bytes[-1] != 0 and header_len < len(block):
                tail_start = header_len
                # Find the next NUL in the tail
                next_zero_in_tail = block.find(b"\x00", tail_start)
                if next_zero_in_tail != -1 and next_zero_in_tail > tail_start:
                    # Extend field with tail bytes
                    extension = block[tail_start:next_zero_in_tail]
                    # Only extend if extension contains printable/uppercase chars
                    if extension and all(0x41 <= b <= 0x5A for b in extension):
                        field_bytes = field_bytes + extension
                        has_null = True
                        # Update where tail data actually starts (after the extended field + NUL)
                        tail_data_start = next_zero_in_tail + 1
        else:
            field_bytes = header[cursor:next_zero]
            cursor = next_zero + 1
            has_null = True
        fields.append(RegionField(raw=field_bytes, has_trailing_null=has_null))

    # Parse tail words starting from where fields actually end
    # Tail section is 32 bytes, starting at byte 33
    tail_section = block[header_len:REGION_RECORD_LEN]

    # If tail_data_start > header_len, fields spanned into tail
    # We need to skip those bytes when parsing tail_words
    tail_offset = tail_data_start - header_len  # Offset into tail section

    # Parse tail_words from the remaining tail data
    tail_data = tail_section[tail_offset:]

    # Parse as many words as we can from remaining tail data
    word_count = min(16, len(tail_data) // 2)
    if word_count > 0:
        tail_words = list(struct.unpack("<" + "H" * word_count, tail_data[:word_count * 2]))
        # Pad to 16 words if necessary
        while len(tail_words) < 16:
            tail_words.append(0)
    else:
        tail_words = [0] * 16

    adjacency_idx: Optional[int] = None
    region_code_idx: Optional[int] = None
    for idx_field, field in enumerate(fields):
        text = field.text()
        # Skip fields with non-printable characters - these are format control codes
        if adjacency_idx is None and text and text.isupper() and len(text) % 2 == 0:
            if all(c.isprintable() for c in text):
                adjacency_idx = idx_field
        if region_code_idx is None and _find_region_code(text):
            region_code_idx = idx_field

    return MapRegion(
        index=index,
        name=name_bytes.decode(SCENARIO_TEXT_ENCODING, errors="replace"),
        fields=fields,
        tail_words=tail_words,
        tail_data_start=tail_data_start,
        adjacency_field_index=adjacency_idx,
        region_code_field_index=region_code_idx,
    )


def parse_unit_table(chunk: bytearray) -> List[UnitRecord]:
    units: List[UnitRecord] = []
    total_slots = len(chunk) // UNIT_FRAME_SIZE
    for slot in range(total_slots):
        frame = chunk[slot * UNIT_FRAME_SIZE : (slot + 1) * UNIT_FRAME_SIZE]
        if not any(frame):
            continue
        words = list(struct.unpack("<" + "H" * UNIT_FRAME_WORDS, frame))
        template_id = words[0] & 0xFF
        owner_raw = words[0] >> 8
        region_index = words[1]
        tile_x = words[2]
        tile_y = words[3]
        units.append(
            UnitRecord(
                slot=slot,
                template_id=template_id,
                owner_raw=owner_raw,
                region_index=region_index,
                tile_x=tile_x,
                tile_y=tile_y,
                raw_words=words,
            )
        )
    units.sort(key=lambda unit: unit.slot)
    return units


@dataclass
class TemplateRecord:
    name: str
    icon_index: Optional[int]
    raw: bytes
    victory_points: Optional[int] = None


def load_template_library(base_dir: Path) -> Dict[str, List[TemplateRecord]]:
    def parse_file(filename: str, icon_offset: Optional[int], icon_bytes: int, kind: str) -> List[TemplateRecord]:
        source = base_dir / filename
        if not source.exists():
            return []
        blob = source.read_bytes()
        count, offset = _read_word(blob, 0)
        if count <= 0:
            return []
        record_len = (len(blob) - offset) // count
        templates: List[TemplateRecord] = []
        for idx in range(count):
            record = blob[offset + idx * record_len : offset + (idx + 1) * record_len]
            segment, _ = _read_cstring_bytes(record, 0)
            name = segment.decode(SCENARIO_TEXT_ENCODING, errors="replace")
            icon_index: Optional[int] = None
            if icon_offset is not None and icon_offset < len(record):
                if icon_bytes == 1 and icon_offset + 1 <= len(record):
                    icon_index = record[icon_offset]
                elif icon_bytes == 2 and icon_offset + 2 <= len(record):
                    icon_index = struct.unpack_from("<H", record, icon_offset)[0] & 0xFF

            victory_points: Optional[int] = None
            if kind in {"surface", "sub"}:
                vp_offset = 0x72
                if vp_offset + 2 <= len(record):
                    victory_points = struct.unpack_from("<H", record, vp_offset)[0]
            elif kind == "air":
                # Empirically, the last non-zero byte encodes the VP value.
                for byte in reversed(record):
                    if byte != 0:
                        victory_points = byte
                        break

            templates.append(
                TemplateRecord(name=name, icon_index=icon_index, raw=record, victory_points=victory_points)
            )
        return templates

    library: Dict[str, List[TemplateRecord]] = {}
    for fname, (offset, size) in TEMPLATE_ICON_OFFSETS.items():
        kind = "air" if "AIR" in fname else "surface" if "SRF" in fname else "sub"
        library[kind] = parse_file(fname, offset, size, kind)
    return library


def load_template_names(base_dir: Path) -> Dict[str, List[str]]:
    library = load_template_library(base_dir)
    return {kind: [record.name for record in records] for kind, records in library.items()}
