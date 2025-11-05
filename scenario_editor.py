#!/usr/bin/env python3
"""
Tkinter-based scenario editor for SSI's 5th Fleet.

Features:
    - Edit SCENARIO.DAT narrative text, metadata strings, and trailing parameters.
    - Inspect and tweak map region metadata (names, adjacency, highlight coordinates).
    - Manage order-of-battle unit tables (air, surface, submarine).
    - View and edit raw victory parameter words stored in scenario trailing bytes.

This tool leverages the parsing/writing helpers in editor.data, preserving unknown
binary sections so that files can be round-tripped safely.
"""

from __future__ import annotations

import struct
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional, Tuple

from PIL import ImageTk

from editor.data import (
    MapFile,
    ScenarioFile,
    ScenarioRecord,
    TemplateRecord,
    UnitRecord,
    create_blank_scenario,
    load_template_library,
    MetadataEntry,
)
from editor.icons import MiconIcon, load_micon_icons
from editor.gxl import load_gxl_archive
from editor.objectives import (
    parse_objective_script as parse_objective_script_proper,
    objective_script_bytes,
)

try:
    from tkinter import ttk
except ImportError:  # pragma: no cover - ttk is bundled with Tk in CPython.
    ttk = None  # type: ignore


# Opcode decoder ring from reverse engineering
OPCODE_MAP = {
    0x00: ("END", "Region index", "End-of-script / victory check for region"),
    0x01: ("TURNS", "Side marker", "Player objective delimiter (0x0d=Green, 0x00=Red)"),
    0x03: ("SCORE", "VP ref", "Victory point objective"),
    0x04: ("CONVOY_RULE", "Flags", "Convoy delivery rule flags"),
    0x05: ("SPECIAL_RULE", "Code", "Special engagement rule"),
    0x06: ("SHIP_DEST", "Port idx", "Ships must reach port"),
    0x07: ("UNKNOWN_07", "?", "Unknown (used in setup)"),
    0x08: ("UNKNOWN_08", "?", "Unknown"),
    0x09: ("ZONE_CONTROL", "Zone idx", "Zone must be controlled/occupied"),
    0x0a: ("ZONE_CHECK", "Zone idx", "Check zone status"),
    0x0c: ("TASK_FORCE", "TF ref", "Task force objective"),
    0x0e: ("BASE_RULE", "Base ID", "Airfield/base objective"),
    0x0f: ("UNKNOWN_0F", "?", "Unknown"),
    0x13: ("PORT_RESTRICT", "Flags", "Replenishment port restrictions"),
    0x18: ("CONVOY_PORT", "Port idx", "Convoy destination port"),
    0x1d: ("SHIP_OBJECTIVE", "Ship type", "Ship-specific objective"),
    0x29: ("REGION_RULE", "Region idx", "Region-based victory rule"),
    0x2d: ("ALT_TURNS", "Turn count", "Alternate turn limit (some scenarios use this)"),
    0x3a: ("CONVOY_FALLBACK", "List ref", "Fallback port list"),
    0x3c: ("DELIVERY_CHECK", "Flags", "Delivery success/failure check"),
    0x3d: ("PORT_LIST", "List idx", "Port list (multi-destination)"),
    0x41: ("FLEET_POSITION", "?", "Fleet positioning requirement"),
    0x6d: ("SUPPLY_LIMIT", "Port mask", "Supply port restrictions"),
    0xbb: ("ZONE_ENTRY", "Zone idx", "Zone entry requirement"),
}

SPECIAL_OPERANDS = {
    0xfe: "PROHIBITED/ALL",
    0xff: "UNLIMITED",
    0x00: "NONE/STANDARD",
}


def _default_game_dir() -> Path:
    candidate = Path("game")
    if candidate.exists():
        return candidate
    return Path.cwd()


class ScenarioEditorApp:
    def __init__(self, root: tk.Tk) -> None:
        if ttk is None:
            raise RuntimeError("ttk is required for this application.")

        self.root = root
        self.root.title("5th Fleet Scenario Editor")

        self.game_dir = _default_game_dir()
        self.scenario_file: Optional[ScenarioFile] = None
        self.map_file: Optional[MapFile] = None
        self.map_file_path: Optional[Path] = None
        self.template_library: Dict[str, List[TemplateRecord]] = {
            "air": [],
            "surface": [],
            "sub": [],
        }

        self.icon_library: List[MiconIcon] = []
        self.icon_load_error: Optional[str] = None
        self.icon_photo_cache: Dict[Tuple[int, int], ImageTk.PhotoImage] = {}
        self.selected_icon_index: Optional[int] = None
        self.icon_preview_photo: Optional[ImageTk.PhotoImage] = None
        self.icon_side_var = tk.IntVar(value=0)

        self.unit_icon_photo: Optional[ImageTk.PhotoImage] = None
        self.unit_icon_info_var = tk.StringVar(value="Icon: n/a")

        self._load_micon_library()
        try:
            self.template_library = load_template_library(self.game_dir)
        except Exception:  # pragma: no cover - defensive
            self.template_library = {"air": [], "surface": [], "sub": []}

        self.selected_scenario_index: Optional[int] = None
        self.selected_region_index: Optional[int] = None
        self.selected_unit_kind: str = "air"
        self.selected_unit_slot: Optional[int] = None

        self.oob_map_filename_var = tk.StringVar(value="")

        self._build_menu()
        self._build_notebook()

        default_scenario = self.game_dir / "SCENARIO.DAT"
        if default_scenario.exists():
            self.load_scenario_file(default_scenario)

    # ------------------------------------------------------------------#
    # UI construction
    # ------------------------------------------------------------------#
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open Scenario…", command=self._open_scenario_dialog)
        file_menu.add_command(label="Open Map…", command=self._open_map_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Save Scenario", command=self.save_scenario)
        file_menu.add_command(label="Save Map", command=self.save_map)
        file_menu.add_command(label="Save All", command=self.save_all)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

    def _build_notebook(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook = notebook

        self._build_scenario_tab()
        self._build_map_tab()
        self._build_oob_tab()
        self._build_win_tab()
        self._build_counters_tab()
        self._build_gxl_tab("FLAGS.GXL", "Flags")
        self._build_gxl_tab("GRAFIX.GXL", "Graphics")
        self._build_gxl_tab("TRM.GXL", "Tactical Reference")

    def _load_micon_library(self) -> None:
        """Load the counter icons from MICONRES.RES if present."""
        self.icon_photo_cache.clear()
        self.icon_preview_photo = None

        res_path = self.game_dir / "MICONRES.RES"
        if not res_path.exists():
            self.icon_load_error = f"{res_path.name} not found."
            self.icon_library = []
            self._update_icon_status()
            return
        try:
            self.icon_library = load_micon_icons(res_path)
        except Exception as exc:  # pragma: no cover - defensive
            self.icon_library = []
            self.icon_load_error = f"Failed to load {res_path.name}: {exc}"
        else:
            self.icon_load_error = None
        self._update_icon_status()
        self._populate_icon_list()

    def _update_icon_status(self) -> None:
        if hasattr(self, "icon_status_var"):
            if self.icon_load_error:
                self.icon_status_var.set(self.icon_load_error)
            elif self.icon_library:
                self.icon_status_var.set(
                    f"Loaded {len(self.icon_library)} counter icons from MICONRES.RES."
                )
            else:
                self.icon_status_var.set("No counter icons loaded.")

    def _build_scenario_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Scenario")

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # Use PanedWindow for resizable split
        paned = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Left pane - scenario list
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=0)

        self.scenario_count_var = tk.StringVar(value="Scenarios: 0")
        ttk.Label(list_frame, textvariable=self.scenario_count_var).pack(
            anchor="w", padx=4, pady=(4, 4)
        )

        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self.scenario_listbox = tk.Listbox(list_container, width=45, exportselection=False)
        self.scenario_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scenario_scroll = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.scenario_listbox.yview)
        scenario_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.scenario_listbox.config(yscrollcommand=scenario_scroll.set)
        self.scenario_listbox.bind("<<ListboxSelect>>", self._on_select_scenario)

        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill=tk.X, pady=4)
        ttk.Button(button_frame, text="Add", command=self.add_scenario).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Duplicate", command=self.duplicate_scenario).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(button_frame, text="Delete", command=self.delete_scenario).pack(
            side=tk.LEFT, padx=2
        )

        # Right pane - scenario editor panel
        editor = ttk.Frame(paned)
        paned.add(editor, weight=1)
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(6, weight=1)

        ttk.Label(editor, text="Title").grid(row=0, column=0, sticky="w")
        self.scenario_title_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.scenario_title_var).grid(
            row=0, column=1, sticky="ew", pady=2
        )

        ttk.Label(editor, text="Forces").grid(row=1, column=0, sticky="nw")
        self.forces_text = tk.Text(editor, height=6, width=60)
        self.forces_text.grid(row=1, column=1, sticky="nsew", pady=2)

        ttk.Label(editor, text="Objectives").grid(row=2, column=0, sticky="nw")
        self.objectives_text = tk.Text(editor, height=6, width=60)
        self.objectives_text.grid(row=2, column=1, sticky="nsew", pady=2)

        ttk.Label(editor, text="Special Notes").grid(row=3, column=0, sticky="nw")
        self.notes_text = tk.Text(editor, height=6, width=60)
        self.notes_text.grid(row=3, column=1, sticky="nsew", pady=2)

        ttk.Label(editor, text="Trailing Bytes (hex)").grid(row=4, column=0, sticky="nw")
        self.trailing_text = tk.Text(editor, height=3, width=60)
        self.trailing_text.grid(row=4, column=1, sticky="ew", pady=2)

        info_frame = ttk.Frame(editor)
        info_frame.grid(row=5, column=1, sticky="ew")
        info_frame.columnconfigure(1, weight=1)
        ttk.Label(info_frame, text="Scenario Key:").grid(row=0, column=0, sticky="w")
        self.scenario_key_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.scenario_key_var).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(info_frame, text="Difficulty Token:").grid(row=1, column=0, sticky="w")
        self.scenario_difficulty_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.scenario_difficulty_var).grid(
            row=1, column=1, sticky="w"
        )

        ttk.Button(editor, text="Apply Scenario Changes", command=self.apply_scenario_changes).grid(
            row=7, column=1, sticky="e", pady=4
        )

    def _build_map_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Map")
        self.map_tab_index = len(self.notebook.tabs()) - 1  # Track tab index for updating

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(frame)
        list_frame.grid(row=0, column=0, sticky="ns")
        ttk.Label(list_frame, text="Regions").pack(anchor="w", padx=4, pady=(4, 0))
        self.region_listbox = tk.Listbox(list_frame, width=28, exportselection=False)
        self.region_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.region_listbox.bind("<<ListboxSelect>>", self._on_select_region)

        region_buttons = ttk.Frame(list_frame)
        region_buttons.pack(fill=tk.X, pady=4)
        ttk.Button(region_buttons, text="Add", command=self.add_region).pack(side=tk.LEFT, padx=2)
        ttk.Button(region_buttons, text="Duplicate", command=self.duplicate_region).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(region_buttons, text="Delete", command=self.delete_region).pack(
            side=tk.LEFT, padx=2
        )

        editor = ttk.Frame(frame)
        editor.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="Region Name").grid(row=0, column=0, sticky="w")
        self.region_name_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.region_name_var).grid(
            row=0, column=1, sticky="ew", pady=2
        )

        ttk.Label(editor, text="Region Code (rpXX)").grid(row=1, column=0, sticky="w")
        self.region_code_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.region_code_var).grid(
            row=1, column=1, sticky="ew", pady=2
        )

        ttk.Label(editor, text="Adjacency Codes (comma separated)").grid(
            row=2, column=0, sticky="w"
        )
        self.region_adj_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.region_adj_var).grid(
            row=2, column=1, sticky="ew", pady=2
        )

        pos_frame = ttk.LabelFrame(editor, text="Map Highlight")
        pos_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=6)
        for idx, label in enumerate(("Panel", "X", "Y", "Width")):
            ttk.Label(pos_frame, text=label).grid(row=0, column=idx, padx=4, pady=2)
        self.region_panel_var = tk.IntVar()
        self.region_x_var = tk.IntVar()
        self.region_y_var = tk.IntVar()
        self.region_width_var = tk.IntVar()
        ttk.Spinbox(pos_frame, from_=0, to=3, width=6, textvariable=self.region_panel_var).grid(
            row=1, column=0, padx=4, pady=2
        )
        ttk.Entry(pos_frame, width=8, textvariable=self.region_x_var).grid(
            row=1, column=1, padx=4, pady=2
        )
        ttk.Entry(pos_frame, width=8, textvariable=self.region_y_var).grid(
            row=1, column=2, padx=4, pady=2
        )
        ttk.Entry(pos_frame, width=8, textvariable=self.region_width_var).grid(
            row=1, column=3, padx=4, pady=2
        )

        ttk.Button(editor, text="Apply Region Changes", command=self.apply_region_changes).grid(
            row=4, column=1, sticky="e", pady=4
        )

    def _build_oob_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Order of Battle")
        self.oob_tab_index = len(self.notebook.tabs()) - 1  # Track tab index for updating

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Kind selector
        selector = ttk.Frame(frame)
        selector.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        ttk.Label(selector, text="Unit Table").pack(side=tk.LEFT)
        self.oob_kind_var = tk.StringVar(value="air")
        ttk.Combobox(
            selector,
            textvariable=self.oob_kind_var,
            state="readonly",
            values=("air", "surface", "sub"),
        ).pack(side=tk.LEFT, padx=4)
        ttk.Label(selector, textvariable=self.oob_map_filename_var).pack(side=tk.LEFT, padx=4)
        self.oob_kind_var.trace_add("write", lambda *_: self.refresh_unit_table())

        self.oob_status_var = tk.StringVar(value="Load a map to view unit tables.")
        ttk.Label(frame, textvariable=self.oob_status_var).grid(
            row=1, column=0, sticky="w", padx=6, pady=(0, 2)
        )

        # Units table
        columns = ("slot", "template", "side", "region", "tile")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        for col, label in zip(columns, ("Slot", "Template", "Side", "Region", "Tile (x,y)")):
            tree.heading(col, text=label)
            tree.column(col, width=110 if col == "template" else 80, anchor=tk.W)
        tree.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        tree.bind("<<TreeviewSelect>>", self._on_select_unit)
        self.unit_tree = tree

        # Unit editor
        editor = ttk.LabelFrame(frame, text="Unit Details")
        editor.grid(row=3, column=0, sticky="ew", padx=4, pady=4)
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="Template").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.unit_template_var = tk.StringVar()
        self.unit_template_combo = ttk.Combobox(
            editor, textvariable=self.unit_template_var, state="readonly"
        )
        self.unit_template_combo.grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        ttk.Label(editor, text="Side (0-3)").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.unit_side_var = tk.IntVar()
        ttk.Spinbox(editor, textvariable=self.unit_side_var, from_=0, to=3, width=5).grid(
            row=1, column=1, sticky="w", padx=2, pady=2
        )

        ttk.Label(editor, text="Region").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.unit_region_var = tk.StringVar()
        self.unit_region_combo = ttk.Combobox(
            editor, textvariable=self.unit_region_var, state="readonly"
        )
        self.unit_region_combo.grid(row=2, column=1, sticky="ew", padx=2, pady=2)

        ttk.Label(editor, text="Tile X").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.unit_x_var = tk.IntVar()
        ttk.Entry(editor, textvariable=self.unit_x_var, width=8).grid(
            row=3, column=1, sticky="w", padx=2, pady=2
        )

        ttk.Label(editor, text="Tile Y").grid(row=4, column=0, sticky="w", padx=2, pady=2)
        self.unit_y_var = tk.IntVar()
        ttk.Entry(editor, textvariable=self.unit_y_var, width=8).grid(
            row=4, column=1, sticky="w", padx=2, pady=2
        )

        ttk.Label(editor, textvariable=self.unit_icon_info_var).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=2, pady=(4, 2)
        )
        # Frame to hold icon preview with fixed minimum size to prevent jumping
        icon_frame = ttk.Frame(editor, height=100)
        icon_frame.grid(row=6, column=0, columnspan=2, pady=(0, 4))
        icon_frame.grid_propagate(False)  # Prevent frame from shrinking
        self.unit_icon_preview_label = ttk.Label(icon_frame)
        self.unit_icon_preview_label.pack(expand=True)

        button_row = ttk.Frame(editor)
        button_row.grid(row=7, column=0, columnspan=2, sticky="e", pady=4)
        ttk.Button(button_row, text="Add Unit", command=self.add_unit).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_row, text="Apply Unit", command=self.apply_unit).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(button_row, text="Delete Unit", command=self.delete_unit).pack(
            side=tk.LEFT, padx=2
        )

    def _build_win_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Objectives")

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        # Decoded objectives display
        decoded_frame = ttk.LabelFrame(frame, text="Decoded Objectives")
        decoded_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 4))
        decoded_frame.columnconfigure(0, weight=1)

        self.decoded_objectives_text = tk.Text(decoded_frame, height=6, width=80, wrap=tk.WORD)
        decoded_scroll = ttk.Scrollbar(decoded_frame, orient=tk.VERTICAL, command=self.decoded_objectives_text.yview)
        self.decoded_objectives_text.config(yscrollcommand=decoded_scroll.set)
        self.decoded_objectives_text.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        decoded_scroll.grid(row=0, column=1, sticky="ns")

        # Configure tags for player-specific objective coloring
        self.decoded_objectives_text.tag_configure("green_bg", background="#e8f5e9")  # Light green
        self.decoded_objectives_text.tag_configure("red_bg", background="#ffebee")    # Light red
        self.decoded_objectives_text.tag_configure("green_header", background="#c8e6c9", font=("TkDefaultFont", 10, "bold"))
        self.decoded_objectives_text.tag_configure("red_header", background="#ffcdd2", font=("TkDefaultFont", 10, "bold"))

        self.decoded_objectives_text.config(state=tk.DISABLED)

        columns = ("index", "opcode", "operand", "mnemonic", "description")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        tree.heading("index", text="#")
        tree.heading("opcode", text="Opcode")
        tree.heading("operand", text="Operand")
        tree.heading("mnemonic", text="Mnemonic")
        tree.heading("description", text="Description")
        tree.column("index", width=40, anchor=tk.CENTER)
        tree.column("opcode", width=80, anchor=tk.W)
        tree.column("operand", width=80, anchor=tk.W)
        tree.column("mnemonic", width=140, anchor=tk.W)
        tree.column("description", width=280, anchor=tk.W)

        # Configure tags for player-specific row coloring
        tree.tag_configure("green_row", background="#e8f5e9")  # Light green
        tree.tag_configure("red_row", background="#ffebee")    # Light red
        tree.tag_configure("green_header_row", background="#c8e6c9")  # Darker green for TURNS(0x0d)
        tree.tag_configure("red_header_row", background="#ffcdd2")    # Darker red for TURNS(0x00)

        tree.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        tree.bind("<<TreeviewSelect>>", self._on_select_win_word)
        self.win_tree = tree

        editor = ttk.Frame(frame)
        editor.grid(row=2, column=0, sticky="ew", padx=6, pady=4)
        editor.columnconfigure(3, weight=1)
        ttk.Label(editor, text="Selected #").grid(row=0, column=0, sticky="w")
        self.win_index_var = tk.StringVar(value="-")
        ttk.Label(editor, textvariable=self.win_index_var).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(editor, text="Opcode (0x00-0xFF)").grid(row=0, column=2, sticky="w")
        self.win_opcode_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.win_opcode_var, width=8).grid(row=0, column=3, sticky="w", padx=2)
        ttk.Label(editor, text="Operand (0-255)").grid(row=0, column=4, sticky="w", padx=(8, 0))
        self.win_operand_var = tk.IntVar()
        ttk.Spinbox(editor, textvariable=self.win_operand_var, from_=0, to=255, width=8).grid(row=0, column=5, sticky="w", padx=2)
        ttk.Button(editor, text="Apply", command=self.apply_win_word).grid(
            row=0, column=6, sticky="w", padx=4
        )
        ttk.Button(editor, text="Add Opcode", command=self.add_win_word).grid(
            row=0, column=7, sticky="w", padx=2
        )
        ttk.Button(editor, text="Remove", command=self.remove_win_word).grid(
            row=0, column=8, sticky="w", padx=2
        )

    def _build_counters_tab(self) -> None:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Map Icons (MICONRES.RES)")

        frame.columnconfigure(0, weight=0, minsize=200)  # List column with minimum size
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)

        self.icon_status_var = tk.StringVar()
        self._update_icon_status()
        ttk.Label(frame, textvariable=self.icon_status_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 2)
        )

        ttk.Label(frame, text="Note: Larger unit detail cards are in TRM.GXL (248×165 PCX files)",
                  font=("TkDefaultFont", 8)).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4)
        )

        # Use PanedWindow for resizable split
        paned = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        paned.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=4)

        # Left pane - icon list
        list_container = ttk.Frame(paned)
        paned.add(list_container, weight=0)
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)

        self.icon_listbox = tk.Listbox(list_container, width=30, exportselection=False)
        self.icon_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.icon_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.icon_listbox.configure(yscrollcommand=scrollbar.set)
        self.icon_listbox.bind("<<ListboxSelect>>", self._on_select_icon)

        # Right pane - preview
        preview_frame = ttk.Frame(paned)
        paned.add(preview_frame, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self.icon_info_var = tk.StringVar(value="No icon selected.")
        ttk.Label(preview_frame, textvariable=self.icon_info_var).grid(
            row=0, column=0, sticky="w"
        )

        side_frame = ttk.Frame(preview_frame)
        side_frame.grid(row=1, column=0, sticky="w", pady=(6, 4))
        ttk.Label(side_frame, text="Side preview:").pack(side=tk.LEFT)
        for side_value, side_label in enumerate(["Green", "Red", "Blue", "Yellow"]):
            ttk.Radiobutton(
                side_frame,
                text=side_label,
                value=side_value,
                variable=self.icon_side_var,
                command=self._update_icon_preview,
            ).pack(side=tk.LEFT, padx=2)

        self.icon_preview_label = ttk.Label(preview_frame)
        self.icon_preview_label.grid(row=2, column=0, sticky="n", pady=(6, 4))

        self._populate_icon_list()

    # ------------------------------------------------------------------#
    # Scenario handling
    # ------------------------------------------------------------------#
    def load_scenario_file(self, path: Path) -> None:
        if path.parent != self.game_dir:
            self.game_dir = path.parent
            self._load_micon_library()
            try:
                self.template_library = load_template_library(self.game_dir)
            except Exception:  # pragma: no cover
                self.template_library = {"air": [], "surface": [], "sub": []}
        try:
            self.scenario_file = ScenarioFile.load(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load scenario file:\n{exc}")
            return
        self.root.title(f"5th Fleet Scenario Editor — {path}")
        self.map_file = None
        self.map_file_path = None
        self.oob_map_filename_var.set("")
        self.refresh_region_list()
        self.refresh_unit_table()
        self.refresh_scenario_list()
        if self.scenario_file.records:
            self.scenario_listbox.selection_set(0)
            self._on_select_scenario()
        self.refresh_win_table()

    def refresh_scenario_list(self) -> None:
        self.scenario_listbox.delete(0, tk.END)
        count = 0
        if not self.scenario_file:
            self.scenario_count_var.set("Scenarios: 0")
            return
        for record in self.scenario_file.records:
            count += 1
            title = record.metadata_strings()[0] if record.metadata_entries else f"Scenario {record.index}"
            key_hint = record.scenario_key or "?"
            if record.raw_block is not None:
                title = f"{title} [raw]"
            self.scenario_listbox.insert(tk.END, f"[{record.index}] {title} ({key_hint})")
        self.scenario_count_var.set(f"Scenarios: {count}")

    def _on_select_scenario(self, *_args) -> None:
        if not self.scenario_file:
            return
        selection = self.scenario_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        record = self.scenario_file.records[index]
        self.selected_scenario_index = index

        self.scenario_title_var.set(record.metadata_entries[0].text if record.metadata_entries else "")
        self.forces_text.delete("1.0", tk.END)
        self.forces_text.insert(tk.END, record.forces)
        self.objectives_text.delete("1.0", tk.END)
        self.objectives_text.insert(tk.END, record.objectives)
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert(tk.END, record.notes)
        self.trailing_text.delete("1.0", tk.END)
        self.trailing_text.insert(tk.END, record.trailing_bytes.hex())
        self.scenario_key_var.set(record.scenario_key or "<unknown>")
        self.scenario_difficulty_var.set(record.difficulty_token or "<unknown>")
        self.refresh_win_table()
        self._ensure_map_for_scenario(record)

    def apply_scenario_changes(self) -> None:
        if self.scenario_file is None or self.selected_scenario_index is None:
            return
        record = self.scenario_file.records[self.selected_scenario_index]
        if record.raw_block is not None:
            messagebox.showwarning(
                "Unparsed Record",
                "This scenario block could not be parsed automatically. Editing is disabled to avoid corrupting data.",
            )
            return

        record.forces = self.forces_text.get("1.0", tk.END).rstrip("\n")
        record.objectives = self.objectives_text.get("1.0", tk.END).rstrip("\n")
        record.notes = self.notes_text.get("1.0", tk.END).rstrip("\n")

        # Update title (first metadata entry)
        title = self.scenario_title_var.get().strip()
        if not title:
            title = "Untitled Scenario"

        # Keep existing metadata entries but update the first one (title)
        if record.metadata_entries:
            record.metadata_entries[0].text = title
        else:
            record.metadata_entries = [MetadataEntry(text=title)]

        trailing_hex = self.trailing_text.get("1.0", tk.END).strip().replace(" ", "")
        if len(trailing_hex) % 2 != 0:
            messagebox.showerror("Invalid Hex", "Trailing bytes must contain an even number of hex characters.")
            return
        try:
            record.trailing_bytes = bytes.fromhex(trailing_hex)
        except ValueError:
            messagebox.showerror("Invalid Hex", "Trailing bytes contain invalid hexadecimal characters.")
            return

        self.refresh_scenario_list()
        self.refresh_win_table()
        messagebox.showinfo("Scenario Updated", "Scenario changes applied in memory.")

    def add_scenario(self) -> None:
        if self.scenario_file is None:
            return
        new_index = len(self.scenario_file.records)
        record = create_blank_scenario(new_index)
        self.scenario_file.records.append(record)
        self.refresh_scenario_list()
        self.scenario_listbox.selection_clear(0, tk.END)
        self.scenario_listbox.selection_set(new_index)
        self._on_select_scenario()

    def duplicate_scenario(self) -> None:
        if self.scenario_file is None or self.selected_scenario_index is None:
            return
        original = self.scenario_file.records[self.selected_scenario_index]
        clone = create_blank_scenario(len(self.scenario_file.records))
        if original.raw_block is not None:
            clone.raw_block = bytes(original.raw_block)
        else:
            clone.forces = original.forces
            clone.objectives = original.objectives
            clone.notes = original.notes
            clone.metadata_entries = [
                MetadataEntry(text=entry.text, extra_zero_count=entry.extra_zero_count)
                for entry in original.metadata_entries
            ]
            clone.metadata_leading_zeros = original.metadata_leading_zeros
            clone.trailing_bytes = bytes(original.trailing_bytes)
            clone.has_special_notes_marker = original.has_special_notes_marker
        self.scenario_file.records.append(clone)
        self.refresh_scenario_list()

    def delete_scenario(self) -> None:
        if self.scenario_file is None or self.selected_scenario_index is None:
            return
        if len(self.scenario_file.records) <= 1:
            messagebox.showwarning("Cannot Delete", "At least one scenario must remain.")
            return
        del self.scenario_file.records[self.selected_scenario_index]
        for idx, record in enumerate(self.scenario_file.records):
            record.index = idx
        self.refresh_scenario_list()
        self.selected_scenario_index = None
        self.scenario_listbox.selection_clear(0, tk.END)
        self.win_tree.delete(*self.win_tree.get_children())

    # ------------------------------------------------------------------#
    # Map handling
    # ------------------------------------------------------------------#
    def load_map_file(self, path: Path) -> None:
        if path.parent != self.game_dir:
            self.game_dir = path.parent
            self._load_micon_library()
        try:
            self.map_file = MapFile.load(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load map file:\n{exc}")
            return
        self.map_file_path = path
        self.oob_map_filename_var.set(f"({path.name})")

        # Update tab labels to show filenames
        self.notebook.tab(self.map_tab_index, text=f"Map ({path.name})")
        self.notebook.tab(self.oob_tab_index, text=f"Order of Battle ({path.name})")

        try:
            self.template_library = load_template_library(path.parent)
        except Exception:  # pragma: no cover
            self.template_library = {"air": [], "surface": [], "sub": []}
        self.refresh_region_list()
        self.refresh_unit_table()
        self._populate_region_names_for_units()

    def refresh_region_list(self) -> None:
        self.region_listbox.delete(0, tk.END)
        if not self.map_file:
            return
        for region in self.map_file.regions:
            self.region_listbox.insert(tk.END, f"[{region.index:02}] {region.name}")

    def _on_select_region(self, *_args) -> None:
        if not self.map_file:
            return
        selection = self.region_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        region = self.map_file.regions[index]
        self.selected_region_index = index

        self.region_name_var.set(region.name)
        code = region.region_code() or ""
        self.region_code_var.set(code)
        self.region_adj_var.set(", ".join(region.adjacent_codes()))
        position = region.map_position() or {"panel": 0, "x_raw": 0, "y_raw": 0, "width_raw": 0}
        self.region_panel_var.set(position["panel"])
        self.region_x_var.set(position["x_raw"])
        self.region_y_var.set(position["y_raw"])
        self.region_width_var.set(position["width_raw"])

    def apply_region_changes(self) -> None:
        if self.map_file is None or self.selected_region_index is None:
            return
        region = self.map_file.regions[self.selected_region_index]
        region.name = self.region_name_var.get().strip()

        code = self.region_code_var.get().strip().upper()
        if code and not code.startswith("RP"):
            code = f"rp{code}"
        if region.region_code_field_index is None and code:
            messagebox.showwarning(
                "Untracked Field",
                "This region lacks a region-code field in its header; manual adjustments may be required.",
            )
        elif region.region_code_field_index is not None:
            prefix = region.fields[region.region_code_field_index].text()
            if "rp" in prefix:
                updated = re_sub_region_code(prefix, code[-2:])
            else:
                updated = code
            region.fields[region.region_code_field_index].set_text(updated)

        adjacency_tokens = [
            token.strip().upper()
            for token in self.region_adj_var.get().split(",")
            if token.strip()
        ]
        region.set_adjacent_codes(adjacency_tokens)

        panel = self.region_panel_var.get()
        x_raw = self.region_x_var.get()
        y_raw = self.region_y_var.get()
        width_raw = self.region_width_var.get()
        region.set_map_position(panel, x_raw, y_raw, width_raw)
        self.refresh_region_list()
        messagebox.showinfo("Region Updated", "Region changes applied in memory.")

    def add_region(self) -> None:
        if self.map_file is None:
            return
        template = self.map_file.regions[-1].clone() if self.map_file.regions else None
        if template is None:
            messagebox.showerror("Error", "Cannot add region without a template.")
            return
        template.name = "New Region"
        template.set_adjacent_codes([])
        template.set_map_position(0, 0, 0, 0)
        template.index = len(self.map_file.regions)
        self.map_file.regions.append(template)
        self.refresh_region_list()

    def duplicate_region(self) -> None:
        if self.map_file is None or self.selected_region_index is None:
            return
        original = self.map_file.regions[self.selected_region_index]
        clone = original.clone()
        clone.index = len(self.map_file.regions)
        clone.name = f"{original.name} Copy"
        self.map_file.regions.append(clone)
        self.refresh_region_list()

    def delete_region(self) -> None:
        if self.map_file is None or self.selected_region_index is None:
            return
        if len(self.map_file.regions) <= 1:
            messagebox.showwarning("Cannot Delete", "At least one region must remain.")
            return
        del self.map_file.regions[self.selected_region_index]
        for idx, region in enumerate(self.map_file.regions):
            region.index = idx
        self.refresh_region_list()
        self.selected_region_index = None
        self.region_listbox.selection_clear(0, tk.END)
        self._populate_region_names_for_units()

    # ------------------------------------------------------------------#
    # Order of battle handling
    # ------------------------------------------------------------------#
    def refresh_unit_table(self) -> None:
        self.unit_tree.delete(*self.unit_tree.get_children())
        self._populate_region_names_for_units()
        unit_table = self._current_unit_table()
        if unit_table is None:
            if self.map_file is None:
                self.oob_status_var.set("Load a map to view unit tables.")
            else:
                self.oob_status_var.set("No unit data available for this map.")
            self._clear_unit_icon_preview()
            return

        if not unit_table.units:
            self.oob_status_var.set(f"No units found in {unit_table.kind} table.")
            self._clear_unit_icon_preview()
            return

        self.oob_status_var.set("")
        template_records = self._template_records(unit_table.kind)
        for unit in unit_table.units:
            if template_records and 0 <= unit.template_id < len(template_records):
                template = template_records[unit.template_id]
                name_display = template.name
                if template.icon_index is not None:
                    name_display = f"{template.name} (#{template.icon_index})"
            else:
                template = None
                max_id = len(template_records) - 1 if template_records else 0
                name_display = f"Template {unit.template_id} (out of range 0-{max_id})"
            region_name = (
                self._region_name(unit.region_index)
                if self.map_file
                else f"{unit.region_index}"
            )
            self.unit_tree.insert(
                "",
                tk.END,
                iid=str(unit.slot),
                values=(
                    unit.slot,
                    name_display,
                    unit.owner_raw & 0x03,
                    region_name,
                    f"{unit.tile_x}, {unit.tile_y}",
                ),
            )
        self._refresh_unit_template_combo()
        current_selection = self.unit_tree.selection()
        if current_selection:
            self._on_select_unit()
        elif unit_table.units:
            self.unit_tree.selection_set(str(unit_table.units[0].slot))
            self._on_select_unit()

    def _refresh_unit_template_combo(self) -> None:
        kind = self.oob_kind_var.get()
        names = self._template_names(kind)
        if not names:
            self.unit_template_combo["values"] = []
            self.unit_template_combo.set("")
        else:
            self.unit_template_combo["values"] = names
            if self.unit_template_var.get() not in names:
                self.unit_template_combo.current(0)

    def _populate_region_names_for_units(self) -> None:
        if self.map_file is None:
            self.unit_region_combo["values"] = []
            return
        names = [f"{idx}: {region.name}" for idx, region in enumerate(self.map_file.regions)]
        self.unit_region_combo["values"] = names
        if names:
            self.unit_region_combo.current(0)

    def _current_unit_table(self):
        if self.map_file is None:
            return None
        return self.map_file.unit_tables.get(self.oob_kind_var.get())

    def _on_select_unit(self, *_args) -> None:
        unit_table = self._current_unit_table()
        if unit_table is None:
            return
        selection = self.unit_tree.selection()
        if not selection:
            self._clear_unit_icon_preview()
            return
        slot = int(selection[0])
        self.selected_unit_slot = slot
        unit = next((u for u in unit_table.units if u.slot == slot), None)
        if unit is None:
            self._clear_unit_icon_preview()
            return
        names = self._template_names(unit_table.kind)
        template_name = names[unit.template_id] if 0 <= unit.template_id < len(names) else ""
        self.unit_template_var.set(template_name)
        self.unit_side_var.set(unit.owner_raw & 0x03)
        region_name = self._region_name(unit.region_index)
        if region_name:
            self.unit_region_var.set(f"{unit.region_index}: {region_name}")
        else:
            self.unit_region_var.set(str(unit.region_index))
        self.unit_x_var.set(unit.tile_x)
        self.unit_y_var.set(unit.tile_y)
        self._update_unit_icon_preview(unit_table.kind, unit)

    def add_unit(self) -> None:
        unit_table = self._current_unit_table()
        if unit_table is None:
            messagebox.showerror("No Table", "No map loaded or unit table unavailable.")
            return
        try:
            unit_table.add_unit(
                UnitRecord(
                    slot=len(unit_table.units),
                    template_id=0,
                    owner_raw=0,
                    region_index=0,
                    tile_x=0,
                    tile_y=0,
                    raw_words=[0] * 16,
                )
            )
        except ValueError as exc:
            messagebox.showerror("Cannot Add Unit", str(exc))
            return
        self.refresh_unit_table()

    def apply_unit(self) -> None:
        unit_table = self._current_unit_table()
        if unit_table is None or self.selected_unit_slot is None:
            return
        unit = next((u for u in unit_table.units if u.slot == self.selected_unit_slot), None)
        if unit is None:
            return
        template_names = self._template_names(unit_table.kind)
        template_name = self.unit_template_var.get()
        if template_names:
            try:
                template_id = template_names.index(template_name)
            except ValueError:
                messagebox.showerror("Template", "Select a valid template.")
                return
        else:
            template_id = 0
        unit.template_id = template_id
        unit.owner_raw = (unit.owner_raw & 0xFFFC) | (self.unit_side_var.get() & 0x03)
        region_entry = self.unit_region_var.get()
        try:
            region_index = int(region_entry.split(":", 1)[0])
        except (ValueError, IndexError):
            messagebox.showerror("Region", "Select a valid region entry.")
            return
        unit.region_index = region_index
        unit.tile_x = self.unit_x_var.get()
        unit.tile_y = self.unit_y_var.get()
        self._update_unit_icon_preview(unit_table.kind, unit)
        self.refresh_unit_table()

    def delete_unit(self) -> None:
        unit_table = self._current_unit_table()
        if unit_table is None or self.selected_unit_slot is None:
            return
        unit_table.remove_unit(self.selected_unit_slot)
        self.selected_unit_slot = None
        self.refresh_unit_table()

    def _region_name(self, index: int) -> str:
        if self.map_file is None:
            return ""
        if 0 <= index < len(self.map_file.regions):
            return self.map_file.regions[index].name
        return ""

    def _extract_base_name(self, base_rule_operand: int) -> Optional[str]:
        """Extract base/airfield name from pointer section 9 using BASE_RULE operand.

        BASE_RULE mapping: operand → pointer_section_9[operand - 1] → base name

        Pointer section 9 contains null-terminated strings. We parse ALL strings
        (including single-char fragments) and index using (operand - 1).
        """
        if self.map_file is None:
            return None

        # Find pointer section 9
        pointer_section_9 = None
        for entry in self.map_file.pointer_entries:
            if entry.index == 9:
                pointer_section_9 = entry
                break

        if pointer_section_9 is None:
            return None

        # Extract the raw data for pointer section 9
        start_offset = pointer_section_9.start
        # Calculate actual size by finding end of section
        # The pointer_blob starts at pointer_data_base
        section_data = self.map_file.pointer_blob[start_offset:start_offset + pointer_section_9.count]

        # Parse ALL null-terminated strings (including fragments)
        strings = []
        i = 0
        while i < len(section_data):
            if section_data[i] == 0:
                i += 1
                continue

            start = i
            while i < len(section_data) and section_data[i] != 0:
                i += 1

            string = section_data[start:i].decode('latin1', errors='replace')
            strings.append(string)
            i += 1

        # Apply the mapping formula: string_index = operand - 1
        string_index = base_rule_operand - 1

        if 0 <= string_index < len(strings):
            base_name = strings[string_index]
            # Filter out obvious garbage (single chars, control chars, etc)
            # but return the name even if it looks odd for debugging
            if len(base_name) >= 4 and base_name[0].isupper():
                return base_name
            # Return even if it doesn't look right, with a marker
            return f"{base_name} [idx:{string_index}]"

        return None

    def _extract_port_name(self, port_operand: int) -> Optional[str]:
        """Extract port name from pointer section 9 using CONVOY_PORT/SHIP_DEST operand.

        Port mapping: Tests multiple formulas as indexing may differ from BASE_RULE:
        - Try operand - 2 (observed in Scenario 6)
        - Try operand - 1 (BASE_RULE formula)
        - Try operand (direct index)

        Returns the first valid-looking port name found.
        """
        if self.map_file is None:
            return None

        # Find pointer section 9
        pointer_section_9 = None
        for entry in self.map_file.pointer_entries:
            if entry.index == 9:
                pointer_section_9 = entry
                break

        if pointer_section_9 is None:
            return None

        section_data = self.map_file.pointer_blob[pointer_section_9.start:pointer_section_9.start + pointer_section_9.count]

        # Extract all strings
        strings = []
        i = 0
        while i < len(section_data):
            if section_data[i] == 0:
                i += 1
                continue
            start = i
            while i < len(section_data) and section_data[i] != 0:
                i += 1
            string = section_data[start:i].decode('latin1', errors='replace')
            strings.append(string)
            i += 1

        # Try multiple formulas
        for formula_offset in [-2, -1, 0]:
            string_index = port_operand + formula_offset
            if 0 <= string_index < len(strings):
                port_name = strings[string_index]
                # Accept if it looks like a place name (length >= 4, starts with capital)
                if len(port_name) >= 4 and port_name[0].isupper():
                    return port_name

        return None

    def _extract_convoy_ship_names(self) -> List[str]:
        """Extract convoy ship names from MAP pointer section 14.

        Searches for ships with "Fast Convoy" classification and extracts their names.
        Returns list of ship names (e.g., ["Antares", "Capella"]).
        """
        if self.map_file is None:
            return []

        # Find pointer section 14 (unit names/classifications)
        pointer_section_14 = None
        for entry in self.map_file.pointer_entries:
            if entry.index == 14:
                pointer_section_14 = entry
                break

        if pointer_section_14 is None:
            return []

        data = pointer_section_14.data
        convoy_ships = []

        # Search for pattern: "ShipName\x00...\x00Fast Convoy\x00"
        # The ship name appears shortly before "Fast Convoy" classification
        i = 0
        while i < len(data) - 20:
            # Look for start of alphabetic string
            if data[i] >= 0x41 and data[i] <= 0x7A:  # A-Z, a-z
                start = i
                while i < len(data) and data[i] != 0:
                    i += 1
                if i > start:
                    potential_name = data[start:i].decode('latin1', errors='replace')
                    # Look ahead for "Fast Convoy" within next 20 bytes
                    search_end = min(len(data), i + 20)
                    if b'Fast Convoy' in data[i:search_end]:
                        # Filter out garbage strings (must be reasonable ship name)
                        if len(potential_name) >= 3 and potential_name[0].isupper():
                            convoy_ships.append(potential_name)
            i += 1

        # Return unique names only (each ship appears twice in section 14)
        return sorted(set(convoy_ships))

    # ------------------------------------------------------------------#
    # Win conditions handling
    # ------------------------------------------------------------------#
    def refresh_win_table(self) -> None:
        self.win_tree.delete(*self.win_tree.get_children())
        record = self._current_record()
        if record is None:
            if hasattr(self, "decoded_objectives_text"):
                self.decoded_objectives_text.config(state=tk.NORMAL)
                self.decoded_objectives_text.delete("1.0", tk.END)
                self.decoded_objectives_text.config(state=tk.DISABLED)
            return

        # Parse objective script from trailing bytes
        script = self._parse_objective_script(record.trailing_bytes)

        # Update decoded objectives text
        if hasattr(self, "decoded_objectives_text"):
            self._render_decoded_objectives(script, record)

        # Populate tree with opcode details
        current_player = None  # Track which player context we're in
        for idx, (opcode, operand) in enumerate(script):
            if opcode in OPCODE_MAP:
                mnemonic, op_type, _ = OPCODE_MAP[opcode]
            else:
                mnemonic = f"UNKNOWN_{opcode:02x}"
                op_type = "?"

            operand_display = self._format_operand(operand)

            # Decode the actual description based on opcode and operand value
            description = self._decode_opcode_description(opcode, operand)

            # Determine row color based on TURNS opcode and current player context
            tags = ()
            if opcode == 0x01:  # TURNS opcode
                if operand == 0x0d:
                    current_player = "Green"
                    tags = ("green_header_row",)
                elif operand == 0x00:
                    current_player = "Red"
                    tags = ("red_header_row",)
            else:
                # Apply player-specific background to non-TURNS opcodes
                if current_player == "Green":
                    tags = ("green_row",)
                elif current_player == "Red":
                    tags = ("red_row",)

            self.win_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    idx,
                    f"0x{opcode:02x}",
                    operand_display,
                    f"{mnemonic}({operand})",
                    description
                ),
                tags=tags,
            )
        self.win_index_var.set("-")

    def _decode_opcode_description(self, opcode: int, operand: int) -> str:
        """Decode a single opcode/operand pair into a human-readable description.

        This decodes the actual meaning based on the operand value, not just the
        generic opcode description.
        """
        if opcode == 0x01:  # TURNS
            if operand == 0x0d:
                return "Green player objectives start"
            elif operand == 0x00:
                return "Red player objectives start"
            elif operand == 0xfe:
                return "No turn limit (play until objectives complete)"
            else:
                return f"Player objective delimiter: {operand}"

        elif opcode == 0x2d:  # ALT_TURNS
            return f"Turn limit: {operand} turns"

        elif opcode == 0x05:  # SPECIAL_RULE
            if operand == 0xfe:
                return "No cruise missile attacks allowed"
            elif operand == 0x06:
                return "Convoy delivery mission active"
            elif operand == 0x00:
                return "Standard engagement rules"
            else:
                return f"Special rule: code {operand}"

        elif opcode == 0x0c:  # TASK_FORCE
            if operand == 0xfe:
                return "All task forces must survive"
            else:
                return f"Task force survival/destination (ref: {operand})"

        elif opcode == 0x09 or opcode == 0x0a:  # ZONE_CONTROL/CHECK
            region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
            return f"Control or occupy {region_name}"

        elif opcode == 0x00:  # END
            if operand > 0:
                region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
                return f"Victory check: {region_name}"
            else:
                return "End of script"

        elif opcode == 0x03:  # SCORE
            return f"Victory points objective (ref: {operand})"

        elif opcode == 0x06:  # SHIP_DEST
            port_name = self._extract_port_name(operand)
            if port_name:
                return f"Ships must reach {port_name}"
            else:
                return f"Ships must reach port (index: {operand})"

        elif opcode == 0x0e:  # BASE_RULE
            base_name = self._extract_base_name(operand)
            if base_name:
                return f"Airfield/base objective: {base_name}"
            else:
                return f"Airfield/base objective (base ID {operand})"

        elif opcode == 0x18:  # CONVOY_PORT
            port_name = self._extract_port_name(operand)
            if port_name:
                return f"Convoy destination: {port_name}"
            else:
                return f"Convoy destination (port ref: {operand})"

        elif opcode == 0xbb:  # ZONE_ENTRY
            region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
            return f"Zone entry requirement: {region_name}"

        elif opcode == 0x29:  # REGION_RULE
            region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
            return f"Region-based victory rule: {region_name}"

        elif opcode == 0x3a:  # CONVOY_FALLBACK
            return f"Convoy fallback port list (ref: {operand})"

        elif opcode == 0x3c:  # DELIVERY_CHECK
            return f"Delivery success/failure check (flags: {operand})"

        elif opcode == 0x3d:  # PORT_LIST
            return f"Multi-destination port list (ref: {operand})"

        elif opcode in OPCODE_MAP:
            _, _, description = OPCODE_MAP[opcode]
            return f"{description} (param: {operand})"

        else:
            return f"Unknown opcode 0x{opcode:02x}, operand {operand}"

    def _parse_objective_script(self, trailing_bytes: bytes) -> List[Tuple[int, int]]:
        """Parse objective script from trailing bytes into (opcode, operand) tuples.

        Uses the proper parser that skips metadata strings and finds the actual
        objective script after the difficulty token.
        """
        return parse_objective_script_proper(trailing_bytes)

    def _encode_objective_script(self, original_trailing_bytes: bytes, script: List[Tuple[int, int]]) -> bytes:
        """Encode objective script back to trailing bytes, preserving metadata.

        The trailing bytes contain metadata strings followed by the objective script.
        This function preserves the metadata portion and only replaces the script.
        """
        # Find where the script starts in the original bytes
        script_bytes = objective_script_bytes(original_trailing_bytes)
        if script_bytes:
            # Calculate the offset where script starts
            script_offset = len(original_trailing_bytes) - len(script_bytes)
            metadata_portion = original_trailing_bytes[:script_offset]
        else:
            # No script found, keep all as metadata
            metadata_portion = original_trailing_bytes

        # Encode the new script
        words = [(opcode << 8) | operand for opcode, operand in script]
        new_script_bytes = struct.pack("<" + "H" * len(words), *words)

        # Combine metadata + new script
        return metadata_portion + new_script_bytes

    def _format_operand(self, operand: int) -> str:
        """Format an operand value with special value notation."""
        if operand in SPECIAL_OPERANDS:
            return f"{operand} ({SPECIAL_OPERANDS[operand]})"
        return str(operand)

    def _decode_objectives(self, script: List[Tuple[int, int]], record: ScenarioRecord) -> str:
        """Decode objective script into human-readable text."""
        if not script:
            return "No objective script found in trailing bytes."

        lines = []

        # Add descriptive objectives text from SCENARIO.DAT first
        if record.objectives and record.objectives.strip():
            lines.append("═══════════════════════════════════════════════════")
            lines.append("SCENARIO OBJECTIVES (Descriptive Text)")
            lines.append("═══════════════════════════════════════════════════")
            lines.append("")
            lines.append(record.objectives.strip())
            lines.append("")
            lines.append("═══════════════════════════════════════════════════")
            lines.append("BINARY OPCODE IMPLEMENTATION")
            lines.append("═══════════════════════════════════════════════════")
            lines.append("")

        # Extract turn count from byte offset 45 in trailing bytes
        turn_count_from_byte45 = None
        if len(record.trailing_bytes) > 45:
            turn_count_from_byte45 = record.trailing_bytes[45]
            lines.append(f"**Turn Limit: {turn_count_from_byte45} turns**")
            lines.append("")

        # Track if we find turn-related opcodes
        found_turns_01 = False
        found_alt_turns = False
        current_player = None  # Track which player's objectives we're in

        # Pre-scan for convoy-related opcodes and section markers
        has_convoy_rule = any(op == 0x05 and oper == 0x06 for op, oper in script)
        has_convoy_port = any(op == 0x18 for op, oper in script)
        has_ship_dest = any(op == 0x06 for op, oper in script)
        has_explicit_red_marker = any(op == 0x01 and oper == 0x00 for op, oper in script)

        # Pre-scan to find END(0) as potential section separator
        end_zero_index = None
        for idx, (op, oper) in enumerate(script):
            if op == 0x00 and oper == 0x00:
                # Check if there are more opcodes after this END(0)
                if idx + 1 < len(script):
                    end_zero_index = idx
                break

        for idx, (opcode, operand) in enumerate(script):
            if opcode == 0x01:  # TURNS - player objective delimiter
                found_turns_01 = True
                if operand == 0x0d:
                    lines.append("")
                    lines.append("═══ GREEN PLAYER OBJECTIVES ═══")
                    current_player = "Green"
                elif operand == 0x00:
                    lines.append("")
                    lines.append("═══ RED PLAYER OBJECTIVES ═══")
                    current_player = "Red"
                elif operand == 0xfe:
                    lines.append("• No turn limit (play until objectives complete)")
                else:
                    lines.append(f"• Player objective delimiter: {operand}")

            elif opcode == 0x2d:  # ALT_TURNS
                found_alt_turns = True
                lines.append(f"• Turn limit: {operand} turns")
                if turn_count_from_byte45 and turn_count_from_byte45 != operand:
                    lines.append(f"  ⚠ WARNING: Mismatch detected!")

            elif opcode == 0x05:  # SPECIAL_RULE
                if operand == 0xfe:
                    lines.append("• Special: No cruise missile attacks allowed")
                elif operand == 0x06:
                    # Extract convoy ship names from MAP data
                    convoy_ships = self._extract_convoy_ship_names()

                    # Find destination if CONVOY_PORT exists
                    convoy_port_opcode = next((o for o in script if o[0] == 0x18), None)
                    destination = None
                    if convoy_port_opcode:
                        destination = self._extract_port_name(convoy_port_opcode[1])

                    # Build convoy objective description
                    if convoy_ships and destination:
                        ship_list = ", ".join(convoy_ships)
                        lines.append(f"• Convoy objective: {ship_list} must reach {destination}")
                    elif convoy_ships:
                        ship_list = ", ".join(convoy_ships)
                        lines.append(f"• Convoy objective: {ship_list}")
                        lines.append("    ⚠ WARNING: No CONVOY_PORT or SHIP_DEST opcode found")
                        lines.append("    Destination only specified in narrative text above")
                    else:
                        lines.append("• Special: Convoy delivery mission active")
                        if not has_convoy_port and not has_ship_dest:
                            lines.append("    ⚠ WARNING: No CONVOY_PORT or SHIP_DEST opcode found")
                            lines.append("    Destination only specified in narrative text above")
                elif operand == 0x00:
                    lines.append("• Special: Standard engagement rules")
                else:
                    lines.append(f"• Special rule: code {operand}")

            elif opcode == 0x0c:  # TASK_FORCE
                if operand == 0xfe:
                    lines.append("• All task forces must survive")
                else:
                    lines.append(f"• Task force must survive/reach destination (ref: {operand})")

            elif opcode == 0x09 or opcode == 0x0a:  # ZONE_CONTROL/CHECK
                if self.map_file and operand < len(self.map_file.regions):
                    region_name = self._region_name(operand)
                elif operand == 254:
                    region_name = "ALL zones (special value 0xfe)"
                elif self.map_file and operand > len(self.map_file.regions):
                    # Operand exceeds region count but game handles it (doesn't crash)
                    # May be special victory condition ID, or game bounds-checks before use
                    region_name = f"zone/condition {operand} (exceeds map region count; meaning unclear)"
                else:
                    region_name = f"region {operand}"
                lines.append(f"• Control or occupy {region_name}")

            elif opcode == 0x00:  # END
                if operand == 0 and end_zero_index is not None and idx == end_zero_index:
                    # END(0) with more opcodes after it - treat as Red Player section separator
                    if not has_explicit_red_marker and current_player == "Green":
                        lines.append("")
                        lines.append("═══ RED PLAYER OBJECTIVES ═══")
                        current_player = "Red"
                    # Don't display END(0) as a victory check when it's a section separator
                elif operand > 0:
                    region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
                    lines.append(f"• Victory check region: {region_name}")
                    lines.append("    (May be global end-game trigger, not player-specific objective)")

            elif opcode == 0x03:  # SCORE
                # Provide generic description since VP table format is undocumented
                vp_desc = "Destroy as many enemy units as possible"
                lines.append(f"• Victory points: {vp_desc}")
                lines.append(f"    (VP reference: {operand} - see narrative text for specifics)")

            elif opcode == 0x06:  # SHIP_DEST
                port_name = self._extract_port_name(operand)
                if port_name:
                    lines.append(f"• Ships must reach {port_name}")
                else:
                    lines.append(f"• Ships must reach port (index: {operand})")

            elif opcode == 0x0e:  # BASE_RULE
                base_name = self._extract_base_name(operand)
                # Add contextual hint based on player
                if current_player == "Red":
                    action_hint = " (likely: attack/destroy)"
                elif current_player == "Green":
                    action_hint = " (likely: defend)"
                else:
                    action_hint = ""

                if base_name:
                    lines.append(f"• Airfield/base objective: {base_name}{action_hint}")
                else:
                    lines.append(f"• Airfield/base objective (base ID {operand}){action_hint}")

            elif opcode == 0x18:  # CONVOY_PORT
                port_name = self._extract_port_name(operand)
                convoy_ships = self._extract_convoy_ship_names()

                if convoy_ships and port_name:
                    ship_list = ", ".join(convoy_ships)
                    lines.append(f"• Convoy objective: {ship_list} must reach {port_name}")
                elif convoy_ships:
                    ship_list = ", ".join(convoy_ships)
                    lines.append(f"• Convoy ships: {ship_list}")
                    if port_name:
                        lines.append(f"• Convoy destination: {port_name}")
                    else:
                        lines.append(f"• Convoy destination (port ref: {operand})")
                else:
                    if port_name:
                        lines.append(f"• Convoy destination: {port_name}")
                    else:
                        lines.append(f"• Convoy destination (port ref: {operand})")

            elif opcode == 0xbb:  # ZONE_ENTRY
                if self.map_file and operand < len(self.map_file.regions):
                    region_name = self._region_name(operand)
                else:
                    region_name = f"region {operand}"
                    if self.map_file and operand >= len(self.map_file.regions):
                        region_name += f" (not found in map)"
                lines.append(f"• Zone entry requirement: {region_name}")

            elif opcode == 0x29:  # REGION_RULE
                if self.map_file and operand < len(self.map_file.regions):
                    region_name = self._region_name(operand)
                else:
                    region_name = f"region {operand}"
                    if self.map_file and operand >= len(self.map_file.regions):
                        region_name += f" (not found in map)"
                lines.append(f"• Region-based victory rule: {region_name}")

            elif opcode == 0x3a:  # CONVOY_FALLBACK
                lines.append(f"• Convoy fallback port list (ref: {operand})")

            elif opcode == 0x3c:  # DELIVERY_CHECK
                lines.append(f"• Delivery success/failure check (flags: {operand})")

            elif opcode == 0x3d:  # PORT_LIST
                lines.append(f"• Multi-destination port list (ref: {operand})")

            elif opcode in OPCODE_MAP:
                mnemonic, _, description = OPCODE_MAP[opcode]
                lines.append(f"• {description} (param: {operand})")
            else:
                lines.append(f"• Unknown: opcode 0x{opcode:02x}, operand {operand}")

        return "\n".join(lines)

    def _render_decoded_objectives(self, script: List[Tuple[int, int]], record: ScenarioRecord) -> None:
        """Render decoded objectives with color-coded backgrounds for each player."""
        text_widget = self.decoded_objectives_text
        text_widget.config(state=tk.NORMAL)
        text_widget.delete("1.0", tk.END)

        if not script:
            text_widget.insert(tk.END, "No objective script found in trailing bytes.")
            text_widget.config(state=tk.DISABLED)
            return

        # Add descriptive objectives text from SCENARIO.DAT first
        if record.objectives and record.objectives.strip():
            text_widget.insert(tk.END, "═══════════════════════════════════════════════════\n")
            text_widget.insert(tk.END, "SCENARIO OBJECTIVES (Descriptive Text)\n")
            text_widget.insert(tk.END, "═══════════════════════════════════════════════════\n\n")
            text_widget.insert(tk.END, record.objectives.strip() + "\n\n")
            text_widget.insert(tk.END, "═══════════════════════════════════════════════════\n")
            text_widget.insert(tk.END, "BINARY OPCODE IMPLEMENTATION\n")
            text_widget.insert(tk.END, "═══════════════════════════════════════════════════\n\n")

        # Extract turn count from byte offset 45 in trailing bytes
        turn_count_from_byte45 = None
        if len(record.trailing_bytes) > 45:
            turn_count_from_byte45 = record.trailing_bytes[45]
            text_widget.insert(tk.END, f"**Turn Limit: {turn_count_from_byte45} turns**\n\n")

        # Track current player for background coloring
        current_player = None  # None, "Green", or "Red"
        current_bg_tag = None

        # Pre-scan for convoy-related opcodes and section markers
        has_convoy_rule = any(op == 0x05 and oper == 0x06 for op, oper in script)
        has_convoy_port = any(op == 0x18 for op, oper in script)
        has_ship_dest = any(op == 0x06 for op, oper in script)
        has_explicit_red_marker = any(op == 0x01 and oper == 0x00 for op, oper in script)

        # Pre-scan to find END(0) as potential section separator
        end_zero_index = None
        for idx, (op, oper) in enumerate(script):
            if op == 0x00 and oper == 0x00:
                # Check if there are more opcodes after this END(0)
                if idx + 1 < len(script):
                    end_zero_index = idx
                break

        for idx, (opcode, operand) in enumerate(script):
            if opcode == 0x01:  # TURNS - player objective delimiter
                if operand == 0x0d:
                    # Green player section
                    current_player = "Green"
                    current_bg_tag = "green_bg"
                    text_widget.insert(tk.END, "\n")
                    start_pos = text_widget.index(tk.INSERT)
                    text_widget.insert(tk.END, "═══ GREEN PLAYER OBJECTIVES ═══\n")
                    end_pos = text_widget.index(tk.INSERT)
                    text_widget.tag_add("green_header", start_pos, end_pos)

                elif operand == 0x00:
                    # Red player section
                    current_player = "Red"
                    current_bg_tag = "red_bg"
                    text_widget.insert(tk.END, "\n")
                    start_pos = text_widget.index(tk.INSERT)
                    text_widget.insert(tk.END, "═══ RED PLAYER OBJECTIVES ═══\n")
                    end_pos = text_widget.index(tk.INSERT)
                    text_widget.tag_add("red_header", start_pos, end_pos)

                elif operand == 0xfe:
                    start_pos = text_widget.index(tk.INSERT)
                    text_widget.insert(tk.END, "• No turn limit (play until objectives complete)\n")
                    if current_bg_tag:
                        text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))
                else:
                    start_pos = text_widget.index(tk.INSERT)
                    text_widget.insert(tk.END, f"• Turn limit marker: {operand}\n")
                    if current_bg_tag:
                        text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x2d:  # ALT_TURNS
                start_pos = text_widget.index(tk.INSERT)
                text_widget.insert(tk.END, f"• Turn limit: {operand} turns\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x05:  # SPECIAL_RULE
                start_pos = text_widget.index(tk.INSERT)
                if operand == 0xfe:
                    text_widget.insert(tk.END, "• Special: No cruise missile attacks allowed\n")
                elif operand == 0x06:
                    # Extract convoy ship names from MAP data
                    convoy_ships = self._extract_convoy_ship_names()

                    # Find destination if CONVOY_PORT exists
                    convoy_port_opcode = next((o for o in script if o[0] == 0x18), None)
                    destination = None
                    if convoy_port_opcode:
                        destination = self._extract_port_name(convoy_port_opcode[1])

                    # Build convoy objective description
                    if convoy_ships and destination:
                        ship_list = ", ".join(convoy_ships)
                        text_widget.insert(tk.END, f"• Convoy objective: {ship_list} must reach {destination}\n")
                    elif convoy_ships:
                        ship_list = ", ".join(convoy_ships)
                        text_widget.insert(tk.END, f"• Convoy objective: {ship_list}\n")
                        text_widget.insert(tk.END, "    ⚠ WARNING: No CONVOY_PORT or SHIP_DEST opcode found\n")
                        text_widget.insert(tk.END, "    Destination only specified in narrative text above\n")
                    else:
                        text_widget.insert(tk.END, "• Special: Convoy delivery mission active\n")
                        if not has_convoy_port and not has_ship_dest:
                            text_widget.insert(tk.END, "    ⚠ WARNING: No CONVOY_PORT or SHIP_DEST opcode found\n")
                            text_widget.insert(tk.END, "    Destination only specified in narrative text above\n")
                elif operand == 0x00:
                    text_widget.insert(tk.END, "• Special: Standard engagement rules\n")
                else:
                    text_widget.insert(tk.END, f"• Special rule: code {operand}\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x0c:  # TASK_FORCE
                start_pos = text_widget.index(tk.INSERT)
                if operand == 0xfe:
                    text_widget.insert(tk.END, "• All task forces must survive\n")
                else:
                    text_widget.insert(tk.END, f"• Task force must survive/reach destination (ref: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x09 or opcode == 0x0a:  # ZONE_CONTROL/CHECK
                start_pos = text_widget.index(tk.INSERT)
                if self.map_file and operand < len(self.map_file.regions):
                    region_name = self._region_name(operand)
                elif operand == 254:
                    region_name = "ALL zones (special value 0xfe)"
                elif self.map_file and operand > len(self.map_file.regions):
                    # Operand exceeds region count but game handles it (doesn't crash)
                    # May be special victory condition ID, or game bounds-checks before use
                    region_name = f"zone/condition {operand} (exceeds map region count; meaning unclear)"
                else:
                    region_name = f"region {operand}"
                text_widget.insert(tk.END, f"• Control or occupy {region_name}\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x00:  # END
                if operand == 0 and end_zero_index is not None and idx == end_zero_index:
                    # END(0) with more opcodes after it - treat as Red Player section separator
                    if not has_explicit_red_marker and current_player == "Green":
                        current_player = "Red"
                        current_bg_tag = "red_bg"
                        text_widget.insert(tk.END, "\n")
                        start_pos = text_widget.index(tk.INSERT)
                        text_widget.insert(tk.END, "═══ RED PLAYER OBJECTIVES ═══\n")
                        end_pos = text_widget.index(tk.INSERT)
                        text_widget.tag_add("red_header", start_pos, end_pos)
                    # Don't display END(0) as a victory check when it's a section separator
                elif operand > 0:
                    start_pos = text_widget.index(tk.INSERT)
                    region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
                    text_widget.insert(tk.END, f"• Victory check region: {region_name}\n")
                    text_widget.insert(tk.END, "    (May be global end-game trigger, not player-specific objective)\n")
                    if current_bg_tag:
                        text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x03:  # SCORE
                start_pos = text_widget.index(tk.INSERT)
                vp_desc = "Destroy as many enemy units as possible"
                text_widget.insert(tk.END, f"• Victory points: {vp_desc}\n")
                text_widget.insert(tk.END, f"    (VP reference: {operand} - see narrative text for specifics)\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x06:  # SHIP_DEST
                start_pos = text_widget.index(tk.INSERT)
                port_name = self._extract_port_name(operand)
                if port_name:
                    text_widget.insert(tk.END, f"• Ships must reach {port_name}\n")
                else:
                    text_widget.insert(tk.END, f"• Ships must reach port (index: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x0e:  # BASE_RULE
                start_pos = text_widget.index(tk.INSERT)
                base_name = self._extract_base_name(operand)
                # Add contextual hint based on player
                if current_player == "Red":
                    action_hint = " (likely: attack/destroy)"
                elif current_player == "Green":
                    action_hint = " (likely: defend)"
                else:
                    action_hint = ""

                if base_name:
                    text_widget.insert(tk.END, f"• Airfield/base objective: {base_name}{action_hint}\n")
                else:
                    text_widget.insert(tk.END, f"• Airfield/base objective (base ID: {operand}){action_hint}\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x18:  # CONVOY_PORT
                start_pos = text_widget.index(tk.INSERT)
                port_name = self._extract_port_name(operand)
                convoy_ships = self._extract_convoy_ship_names()

                if convoy_ships and port_name:
                    ship_list = ", ".join(convoy_ships)
                    text_widget.insert(tk.END, f"• Convoy objective: {ship_list} must reach {port_name}\n")
                elif convoy_ships:
                    ship_list = ", ".join(convoy_ships)
                    text_widget.insert(tk.END, f"• Convoy ships: {ship_list}\n")
                    if port_name:
                        text_widget.insert(tk.END, f"• Convoy destination: {port_name}\n")
                    else:
                        text_widget.insert(tk.END, f"• Convoy destination (port ref: {operand})\n")
                else:
                    if port_name:
                        text_widget.insert(tk.END, f"• Convoy destination: {port_name}\n")
                    else:
                        text_widget.insert(tk.END, f"• Convoy destination (port ref: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0xbb:  # ZONE_ENTRY
                start_pos = text_widget.index(tk.INSERT)
                region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
                text_widget.insert(tk.END, f"• Zone entry requirement: {region_name}\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x29:  # REGION_RULE
                start_pos = text_widget.index(tk.INSERT)
                region_name = self._region_name(operand) if self.map_file and operand < len(self.map_file.regions) else f"region {operand}"
                text_widget.insert(tk.END, f"• Region-based victory rule: {region_name}\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x3a:  # CONVOY_FALLBACK
                start_pos = text_widget.index(tk.INSERT)
                text_widget.insert(tk.END, f"• Convoy fallback port list (ref: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x3c:  # DELIVERY_CHECK
                start_pos = text_widget.index(tk.INSERT)
                text_widget.insert(tk.END, f"• Delivery success/failure check (flags: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode == 0x3d:  # PORT_LIST
                start_pos = text_widget.index(tk.INSERT)
                text_widget.insert(tk.END, f"• Multi-destination port list (ref: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

            elif opcode in OPCODE_MAP:
                start_pos = text_widget.index(tk.INSERT)
                mnemonic, _, description = OPCODE_MAP[opcode]
                text_widget.insert(tk.END, f"• {description} (param: {operand})\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))
            else:
                start_pos = text_widget.index(tk.INSERT)
                text_widget.insert(tk.END, f"• Unknown: opcode 0x{opcode:02x}, operand {operand}\n")
                if current_bg_tag:
                    text_widget.tag_add(current_bg_tag, start_pos, text_widget.index(tk.INSERT))

        text_widget.config(state=tk.DISABLED)

    def _trailing_words(self, record: ScenarioRecord) -> List[int]:
        if len(record.trailing_bytes) % 2 != 0:
            # Pad odd trailing byte count to preserve parsing.
            return list(struct.unpack("<" + "B" * len(record.trailing_bytes), record.trailing_bytes))
        if not record.trailing_bytes:
            return []
        count = len(record.trailing_bytes) // 2
        return list(struct.unpack("<" + "H" * count, record.trailing_bytes))

    def _on_select_win_word(self, *_args) -> None:
        selection = self.win_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        record = self._current_record()
        if record is None:
            return

        script = self._parse_objective_script(record.trailing_bytes)
        if index >= len(script):
            return

        opcode, operand = script[index]
        self.win_index_var.set(str(index))
        self.win_opcode_var.set(f"0x{opcode:02x}")
        self.win_operand_var.set(operand)

    def apply_win_word(self) -> None:
        record = self._current_record()
        if record is None:
            return
        index_text = self.win_index_var.get()
        if not index_text.isdigit():
            messagebox.showerror("Selection", "Select an opcode to edit.")
            return
        index = int(index_text)

        # Parse opcode
        opcode_text = self.win_opcode_var.get().strip()
        try:
            if opcode_text.startswith("0x"):
                opcode = int(opcode_text, 16)
            else:
                opcode = int(opcode_text)
            if opcode < 0 or opcode > 0xFF:
                raise ValueError("Opcode out of range")
        except ValueError:
            messagebox.showerror("Invalid Opcode", "Opcode must be 0x00-0xFF (0-255).")
            return

        operand = self.win_operand_var.get() & 0xFF

        # Rebuild script
        script = self._parse_objective_script(record.trailing_bytes)
        if index >= len(script):
            messagebox.showerror("Index", "Selected index out of range.")
            return

        script[index] = (opcode, operand)

        # Encode back to trailing bytes, preserving metadata
        record.trailing_bytes = self._encode_objective_script(record.trailing_bytes, script)

        self.refresh_win_table()
        self.trailing_text.delete("1.0", tk.END)
        self.trailing_text.insert(tk.END, record.trailing_bytes.hex())

    def add_win_word(self) -> None:
        record = self._current_record()
        if record is None:
            return

        # Add a new TURNS(0) opcode as default
        script = self._parse_objective_script(record.trailing_bytes)
        script.append((0x01, 0x00))  # TURNS(0) = unlimited

        # Encode back, preserving metadata
        record.trailing_bytes = self._encode_objective_script(record.trailing_bytes, script)

        self.refresh_win_table()
        self.trailing_text.delete("1.0", tk.END)
        self.trailing_text.insert(tk.END, record.trailing_bytes.hex())

    def remove_win_word(self) -> None:
        record = self._current_record()
        if record is None:
            return

        index_text = self.win_index_var.get()
        if not index_text.isdigit():
            # Remove last opcode if none selected
            script = self._parse_objective_script(record.trailing_bytes)
            if not script:
                return
            script.pop()
        else:
            index = int(index_text)
            script = self._parse_objective_script(record.trailing_bytes)
            if index >= len(script):
                return
            del script[index]

        # Encode back, preserving metadata
        if script:
            record.trailing_bytes = self._encode_objective_script(record.trailing_bytes, script)
        else:
            # If no script left, preserve metadata but remove script portion
            script_bytes = objective_script_bytes(record.trailing_bytes)
            if script_bytes:
                script_offset = len(record.trailing_bytes) - len(script_bytes)
                record.trailing_bytes = record.trailing_bytes[:script_offset]

        self.refresh_win_table()
        self.trailing_text.delete("1.0", tk.END)
        self.trailing_text.insert(tk.END, record.trailing_bytes.hex())

    def _populate_icon_list(self) -> None:
        if not hasattr(self, "icon_listbox"):
            return

        self.icon_listbox.delete(0, tk.END)
        if not self.icon_library:
            self.icon_info_var.set(
                self.icon_load_error or "No counter icons available."
            )
            self.icon_preview_label.configure(image="")
            self.icon_preview_photo = None
            return

        for icon in self.icon_library:
            # Try to find which templates use this icon
            using_templates = []
            for kind in ["air", "surface", "sub"]:
                for template in self._template_records(kind):
                    if template.icon_index == icon.index:
                        using_templates.append(f"{template.name[:8]}")
                        if len(using_templates) >= 2:  # Limit display
                            break
                if len(using_templates) >= 2:
                    break

            if using_templates:
                template_hint = f" ({', '.join(using_templates)}...)"
            else:
                template_hint = ""

            entry = f"[{icon.index:02d}] {icon.width}×{icon.height}{template_hint}"
            self.icon_listbox.insert(tk.END, entry)

        self.icon_listbox.selection_set(0)
        self._on_select_icon()

    def _on_select_icon(self, *_args) -> None:
        if not self.icon_library:
            self.selected_icon_index = None
            return
        selection = self.icon_listbox.curselection()
        if not selection:
            self.selected_icon_index = None
            self.icon_preview_label.configure(image="")
            self.icon_info_var.set("No icon selected.")
            return

        index = selection[0]
        if index >= len(self.icon_library):
            return
        self.selected_icon_index = index
        self._update_icon_preview()

    def _update_icon_preview(self) -> None:
        if not self.icon_library or self.selected_icon_index is None:
            return
        if self.selected_icon_index >= len(self.icon_library):
            return

        icon = self.icon_library[self.selected_icon_index]
        side = self.icon_side_var.get()
        photo = self._get_icon_photo(icon.index, side)
        self.icon_preview_photo = photo
        self.icon_preview_label.configure(image=photo)
        self.icon_info_var.set(
            f"Index {icon.index} • {icon.width}×{icon.height} • background={icon.background_index} • side={side}"
        )

    def _template_records(self, kind: str) -> List[TemplateRecord]:
        return self.template_library.get(kind, [])

    def _template_names(self, kind: str) -> List[str]:
        return [record.name for record in self._template_records(kind)]

    def _template_icon_index(self, kind: str, template_id: int) -> Optional[int]:
        records = self._template_records(kind)
        if 0 <= template_id < len(records):
            return records[template_id].icon_index
        return None

    def _update_unit_icon_preview(self, kind: str, unit: UnitRecord) -> None:
        if not hasattr(self, "unit_icon_preview_label"):
            return

        # Check if template is in range
        template_records = self._template_records(kind)
        if not template_records or unit.template_id >= len(template_records):
            max_id = len(template_records) - 1 if template_records else 0
            self.unit_icon_info_var.set(f"Template {unit.template_id} out of range (max {max_id})")
            self.unit_icon_preview_label.configure(image="")
            self.unit_icon_photo = None
            return

        icon_index = self._template_icon_index(kind, unit.template_id)
        if icon_index is None:
            self.unit_icon_info_var.set(f"Template {unit.template_id}: no icon assigned")
            self.unit_icon_preview_label.configure(image="")
            self.unit_icon_photo = None
            return

        if icon_index >= len(self.icon_library):
            self.unit_icon_info_var.set(f"Icon #{icon_index} out of range (max {len(self.icon_library)-1})")
            self.unit_icon_preview_label.configure(image="")
            self.unit_icon_photo = None
            return

        side = unit.owner_raw & 0x03
        photo = self._get_icon_photo(icon_index, side)
        self.unit_icon_photo = photo
        self.unit_icon_preview_label.configure(image=photo)
        self.unit_icon_info_var.set(f"Icon #{icon_index} (side {side})")

    def _clear_unit_icon_preview(self) -> None:
        self.unit_icon_info_var.set("Icon: n/a")
        if hasattr(self, "unit_icon_preview_label"):
            self.unit_icon_preview_label.configure(image="")
        self.unit_icon_photo = None

    def _get_icon_photo(self, icon_index: int, side: int) -> ImageTk.PhotoImage:
        key = (icon_index, side)
        if key not in self.icon_photo_cache:
            icon = self.icon_library[icon_index]
            image = icon.render_image(side=side, scale=4)
            self.icon_photo_cache[key] = ImageTk.PhotoImage(image)
        return self.icon_photo_cache[key]

    # ------------------------------------------------------------------#
    # File dialogs and helpers
    # ------------------------------------------------------------------#
    def _open_scenario_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open SCENARIO.DAT",
            filetypes=[("Scenario DAT", "*.DAT"), ("All files", "*.*")],
            initialdir=self.game_dir,
        )
        if path:
            self.load_scenario_file(Path(path))

    def _open_map_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Scenario Map (*.DAT)",
            filetypes=[("Map DAT", "*.DAT"), ("All files", "*.*")],
            initialdir=self.game_dir,
        )
        if path:
            self.load_map_file(Path(path))

    def save_scenario(self) -> None:
        if self.scenario_file is None:
            messagebox.showerror("No Scenario", "Load a scenario file first.")
            return
        target = (
            self.scenario_file.path
            if self.scenario_file.path
            else filedialog.asksaveasfilename(
                title="Save SCENARIO.DAT",
                defaultextension=".DAT",
                initialdir=self.game_dir,
            )
        )
        if not target:
            return
        try:
            self.scenario_file.save(Path(target))
        except Exception as exc:
            messagebox.showerror("Save Error", f"Unable to save scenario file:\n{exc}")
            return
        messagebox.showinfo("Saved", f"Scenario saved to {target}")

    def save_map(self) -> None:
        if self.map_file is None:
            messagebox.showerror("No Map", "Load a map file first.")
            return
        target = (
            self.map_file.path
            if self.map_file.path
            else filedialog.asksaveasfilename(
                title="Save Map DAT",
                defaultextension=".DAT",
                initialdir=self.game_dir,
            )
        )
        if not target:
            return
        try:
            self.map_file.save(Path(target))
        except Exception as exc:
            messagebox.showerror("Save Error", f"Unable to save map file:\n{exc}")
            return
        messagebox.showinfo("Saved", f"Map saved to {target}")

    def save_all(self) -> None:
        self.save_scenario()
        self.save_map()

    def _current_record(self) -> Optional[ScenarioRecord]:
        if self.scenario_file is None or self.selected_scenario_index is None:
            return None
        return self.scenario_file.records[self.selected_scenario_index]

    def _ensure_map_for_scenario(self, record: ScenarioRecord) -> None:
        if not record.scenario_key:
            self.oob_status_var.set("Scenario has no map key; load a map manually.")
            self.oob_map_filename_var.set("")
            return

        candidates = [
            self.game_dir / f"{record.scenario_key}.DAT",
            self.game_dir / f"{record.scenario_key.upper()}.DAT",
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            self.oob_status_var.set(
                f"Map file for '{record.scenario_key}' not found; load a map manually."
            )
            self.oob_map_filename_var.set("")
            return

        if self.map_file_path and self.map_file_path.resolve() == path.resolve():
            return

        self.load_map_file(path)

    def _build_gxl_tab(self, filename: str, tab_name: str) -> None:
        """Build a tab for browsing PCX images in a GXL archive."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=f"{tab_name} ({filename})")

        frame.columnconfigure(0, weight=0, minsize=200)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)

        # Status label
        status_var = tk.StringVar()
        ttk.Label(frame, textvariable=status_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 2)
        )

        # Use PanedWindow for resizable split
        paned = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=4)

        # Left pane - file list
        list_container = ttk.Frame(paned)
        paned.add(list_container, weight=0)
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)

        listbox = tk.Listbox(list_container, width=30, exportselection=False)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)

        # Right pane - image preview
        preview_frame = ttk.Frame(paned)
        paned.add(preview_frame, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)

        info_var = tk.StringVar(value="No image selected.")
        ttk.Label(preview_frame, textvariable=info_var).grid(
            row=0, column=0, sticky="w", padx=4, pady=4
        )

        # Canvas for scrollable image display
        canvas = tk.Canvas(preview_frame, bg="gray")
        canvas.grid(row=1, column=0, sticky="nsew")
        h_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        h_scroll.grid(row=2, column=0, sticky="ew")
        v_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=canvas.yview)
        v_scroll.grid(row=1, column=1, sticky="ns")
        canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        # Load and populate
        gxl_path = self.game_dir / filename
        if not gxl_path.exists():
            status_var.set(f"{filename} not found.")
            return

        try:
            entries = load_gxl_archive(gxl_path)
            status_var.set(f"Loaded {len(entries)} entries from {filename}")

            # Store data for this tab
            photo_cache: Dict[int, ImageTk.PhotoImage] = {}

            for entry in entries:
                listbox.insert(tk.END, f"{entry.name} ({entry.size} bytes)")

            def on_select(*_args):
                selection = listbox.curselection()
                if not selection:
                    return
                idx = selection[0]
                entry = entries[idx]

                # Try to load as PCX
                try:
                    from PIL import Image
                    import io

                    img = Image.open(io.BytesIO(entry.data))
                    info_var.set(f"{entry.name}: {img.size[0]}×{img.size[1]}, {img.mode}")

                    # Cache photo
                    if idx not in photo_cache:
                        photo_cache[idx] = ImageTk.PhotoImage(img)

                    photo = photo_cache[idx]

                    # Update canvas
                    canvas.delete("all")
                    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
                    canvas.configure(scrollregion=canvas.bbox("all"))

                    # Keep reference
                    canvas.image = photo  # type: ignore

                except Exception as exc:
                    info_var.set(f"{entry.name}: Unable to display ({exc})")
                    canvas.delete("all")

            listbox.bind("<<ListboxSelect>>", on_select)

            # Select first item
            if entries:
                listbox.selection_set(0)
                on_select()

        except Exception as exc:
            status_var.set(f"Error loading {filename}: {exc}")


def re_sub_region_code(text: str, new_code: str) -> str:
    prefix = text
    if "rp" in prefix:
        start = prefix.index("rp")
        return prefix[: start + 2] + new_code.upper() + prefix[start + 4 :]
    return f"rp{new_code.upper()}"


def main() -> None:
    root = tk.Tk()
    app = ScenarioEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
