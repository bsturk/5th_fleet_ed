from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from PIL import Image

# EGA 16-colour palette (BGI default). Values are 0-255 RGB triples.
EGA_PALETTE: Sequence[Tuple[int, int, int]] = (
    (0, 0, 0),  # 0 black
    (0, 0, 170),  # 1 blue
    (0, 170, 0),  # 2 green
    (0, 170, 170),  # 3 cyan
    (170, 0, 0),  # 4 red
    (170, 0, 170),  # 5 magenta
    (170, 85, 0),  # 6 brown
    (170, 170, 170),  # 7 light gray
    (85, 85, 85),  # 8 dark gray
    (85, 85, 255),  # 9 light blue
    (85, 255, 85),  # 10 light green
    (85, 255, 255),  # 11 light cyan
    (255, 85, 85),  # 12 light red
    (255, 85, 255),  # 13 light magenta
    (255, 255, 85),  # 14 yellow
    (255, 255, 255),  # 15 white
)

# Approximate side colours (these are swapped in for the background index).
TEAM_COLOURS: Dict[int, Tuple[int, int, int]] = {
    0: (48, 190, 96),   # green
    1: (208, 40, 40),   # red
    2: (54, 120, 210),  # blue
    3: (215, 190, 60),  # yellow
}


@dataclass
class MiconIcon:
    """Decoded counter icon extracted from MICONRES.RES."""

    index: int
    width: int
    height: int
    background_index: int
    pixels: List[List[int]]  # row-major 4-bit colour indices

    def render_image(
        self,
        side: int | None = None,
        scale: int = 2,
        palette: Sequence[Tuple[int, int, int]] = EGA_PALETTE,
    ) -> Image.Image:
        """
        Convert the icon to a Pillow RGBA image.

        Parameters
        ----------
        side:
            When provided, replaces occurrences of the icon's background index
            with the requested side colour (0=green, 1=red, 2=blue, 3=yellow).
        scale:
            Optional integer scale factor; the image is upscaled with nearest-neighbour
            filtering for easier viewing in Tkinter.
        palette:
            Sequence of base colours to fall back to (defaults to EGA palette).
        """

        width, height = self.width, self.height
        img = Image.new("RGBA", (width, height))
        background_rgba: Tuple[int, int, int] | None = None
        if side is not None and side in TEAM_COLOURS:
            background_rgba = TEAM_COLOURS[side]

        for y, row in enumerate(self.pixels):
            for x, colour_index in enumerate(row):
                if colour_index == 0:
                    img.putpixel((x, y), (0, 0, 0, 0))
                    continue

                if (
                    background_rgba is not None
                    and colour_index == self.background_index
                ):
                    r, g, b = background_rgba
                    img.putpixel((x, y), (r, g, b, 255))
                else:
                    base = palette[colour_index % len(palette)]
                    img.putpixel((x, y), (*base, 255))

        if scale > 1:
            img = img.resize((width * scale, height * scale), Image.NEAREST)
        return img


def load_micon_icons(path: Path) -> List[MiconIcon]:
    """
    Parse MICONRES.RES and return decoded counter icons.

    The file is a sequence of records tagged with the ASCII signature ``MICN``.
    Each record uses a packed header and stores 16-colour bitplanes identical to
    Borland's BGI ``getimage`` format (four bit-planes, little-endian, 16 colours).
    """

    blob = path.read_bytes()
    icons: List[MiconIcon] = []
    search_pos = 0
    record_index = 0

    while True:
        marker_pos = blob.find(b"MICN", search_pos)
        if marker_pos == -1:
            break

        # Header layout:
        #   bytes 0..3  : "MICN"
        #   bytes 4..7  : reserved/pointer (always zero in retail data)
        #   bytes 8..11 : packed value (height << 24 | width << 16 | size)
        #   bytes 12..15: background colour (low nibble) + reserved
        packed = int.from_bytes(blob[marker_pos + 8 : marker_pos + 12], "little")
        size = packed & 0xFFFF
        width = (packed >> 16) & 0xFF
        height = (packed >> 24) & 0xFF
        background = int.from_bytes(
            blob[marker_pos + 12 : marker_pos + 16], "little"
        ) & 0x0F

        # Pixel data: NOT planar! Data is packed 4-bit pixels (2 pixels per byte).
        # Has an 8-byte header (appears to be mostly zeros), then packed pixel data.
        # High nibble = first pixel, low nibble = second pixel.
        data_offset = marker_pos + 16
        raw = blob[data_offset : data_offset + size]

        # Skip 8-byte header
        data = raw[8:]

        pixels: List[List[int]] = []
        pix_idx = -1  # Start at -1 to skip the first pixel (alignment offset)
        total_pixels = width * height

        for byte_val in data:
            # High nibble = first pixel, low nibble = second pixel
            pix1 = (byte_val >> 4) & 0x0F
            pix2 = byte_val & 0x0F

            for pix in [pix1, pix2]:
                if 0 <= pix_idx < total_pixels:
                    x = pix_idx % width
                    y = pix_idx // width

                    # Ensure we have a row for this y
                    while len(pixels) <= y:
                        pixels.append([])

                    pixels[y].append(pix)

                pix_idx += 1
                if pix_idx >= total_pixels:
                    break

            if pix_idx >= total_pixels:
                break

        icons.append(
            MiconIcon(
                index=record_index,
                width=width,
                height=height,
                background_index=background,
                pixels=pixels,
            )
        )

        record_index += 1
        search_pos = marker_pos + 4  # continue scanning beyond this marker

    return icons
