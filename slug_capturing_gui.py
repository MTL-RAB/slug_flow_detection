#!/usr/bin/env python3
"""
Slug Capturing GUI — 1D Two-Fluid Model
=========================================

Simple tkinter GUI for engineers to define multi-segment pipeline geometry
and run a 1D slug capturing simulation based on:

    Issa & Kempf (2003), Int. J. Multiphase Flow, 29, 69-95.

Usage:
    python slug_capturing_gui.py

Features:
    - Segment-based pipeline geometry (any angle -90 to +90 deg)
    - File > New / Open / Save / Save As  (JSON project files)
    - Edit > Undo / Redo  (full parameter-state snapshots)
    - Time-history playback with slider after simulation completes
    - Configurable probe locations
    - Keyboard shortcuts (see Help menu or docstring)
"""

import json
import os
import sys
import copy
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from slug_capturing_solver import SimulationParameters, SlugCapturingSimulation
from version import __app_name__, __version__, __build_date__, __author__
import license_manager

# Default file extension for project files
PROJECT_EXT = ".scproj"
PROJECT_FILETYPES = [("Slug Capturing Project", f"*{PROJECT_EXT}"), ("All Files", "*.*")]

# ============================================================================
# PROJECT STATE  — serializable snapshot of every input parameter
# ============================================================================

DEFAULT_STATE = {
    "segments": [{"length": 36.0, "angle": 0.0}],
    "D": 0.078,
    "rho_L": 998.0,
    "rho_G": 1.2,
    "mu_L": 0.001,
    "mu_G": 1.8e-5,
    "U_sL": 1.0,
    "U_sG": 3.0,
    "N_cells": 500,
    "CFL": 0.45,
    "t_end": 30.0,
    "probe_pcts": "25, 50, 75",
}


def _deep_copy_state(state):
    return copy.deepcopy(state)


# ============================================================================
# UNDO / REDO MANAGER
# ============================================================================

class UndoManager:
    MAX_UNDO = 100

    def __init__(self):
        self._undo_stack = []
        self._redo_stack = []
        self._on_change = None

    def set_change_callback(self, cb):
        self._on_change = cb

    def push(self, state):
        self._undo_stack.append(_deep_copy_state(state))
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._notify()

    def undo(self, current_state):
        if not self._undo_stack:
            return None
        self._redo_stack.append(_deep_copy_state(current_state))
        restored = self._undo_stack.pop()
        self._notify()
        return restored

    def redo(self, current_state):
        if not self._redo_stack:
            return None
        self._undo_stack.append(_deep_copy_state(current_state))
        restored = self._redo_stack.pop()
        self._notify()
        return restored

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify()

    @property
    def can_undo(self):
        return len(self._undo_stack) > 0

    @property
    def can_redo(self):
        return len(self._redo_stack) > 0

    def _notify(self):
        if self._on_change:
            self._on_change(self.can_undo, self.can_redo)


# ============================================================================
# PIPELINE SEGMENT TABLE
# ============================================================================

class SegmentTable(ttk.Frame):
    """Editable table for pipeline segments."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self.rows = []
        self._on_change = on_change
        self._suppress_trace = False

        hdr = ttk.Frame(self)
        hdr.pack(fill="x", pady=(0, 2))
        ttk.Label(hdr, text="#", width=3, anchor="center").pack(side="left")
        ttk.Label(hdr, text="Length (m)", width=12, anchor="center").pack(side="left", padx=2)
        ttk.Label(hdr, text="Angle (\u00b0)", width=12, anchor="center").pack(side="left", padx=2)
        ttk.Label(hdr, text="", width=5).pack(side="left")

        self.table_frame = ttk.Frame(self)
        self.table_frame.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_frame, text="+ Add Segment", command=self._user_add_row).pack(side="left")
        ttk.Button(btn_frame, text="Reset to Default", command=self._user_reset).pack(side="left", padx=4)

        self.preview_canvas = tk.Canvas(self, height=80, bg="white", relief="sunken", bd=1)
        self.preview_canvas.pack(fill="x", pady=(6, 0))

    def add_row(self, length="10.0", angle="0.0"):
        idx = len(self.rows)
        row_frame = ttk.Frame(self.table_frame)
        row_frame.pack(fill="x", pady=1)

        ttk.Label(row_frame, text=str(idx + 1), width=3, anchor="center").pack(side="left")
        length_var = tk.StringVar(value=length)
        angle_var = tk.StringVar(value=angle)
        ttk.Entry(row_frame, textvariable=length_var, width=12, justify="center").pack(side="left", padx=2)
        ttk.Entry(row_frame, textvariable=angle_var, width=12, justify="center").pack(side="left", padx=2)
        ttk.Button(row_frame, text="\u2716", width=3,
                   command=lambda f=row_frame: self._user_delete_row(f)).pack(side="left", padx=2)

        self.rows.append((length_var, angle_var, row_frame))
        length_var.trace_add("write", self._on_var_write)
        angle_var.trace_add("write", self._on_var_write)
        self.update_preview()

    def clear_rows(self):
        for _, _, frame in self.rows:
            frame.destroy()
        self.rows.clear()

    def set_segments(self, seg_list):
        self._suppress_trace = True
        self.clear_rows()
        for seg in seg_list:
            self.add_row(str(seg["length"]), str(seg["angle"]))
        self._suppress_trace = False
        self.update_preview()

    def reset_default(self):
        self.set_segments(DEFAULT_STATE["segments"])

    def get_segments(self):
        segments = []
        for i, (l_var, a_var, _) in enumerate(self.rows):
            try:
                length = float(l_var.get())
            except ValueError:
                raise ValueError(f"Segment {i + 1}: invalid length '{l_var.get()}'")
            try:
                angle = float(a_var.get())
            except ValueError:
                raise ValueError(f"Segment {i + 1}: invalid angle '{a_var.get()}'")
            segments.append((length, angle))
        return segments

    def get_segments_as_dicts(self):
        return [{"length": l, "angle": a} for l, a in self.get_segments()]

    # --- user actions (push undo) ---
    def _user_add_row(self):
        self.add_row()
        self._fire_change()

    def _user_reset(self):
        self.reset_default()
        self._fire_change()

    def _user_delete_row(self, frame):
        for i, (l, a, f) in enumerate(self.rows):
            if f is frame:
                f.destroy()
                self.rows.pop(i)
                self._renumber()
                self.update_preview()
                self._fire_change()
                return

    def _on_var_write(self, *_):
        if not self._suppress_trace:
            self.update_preview()
            self._fire_change()

    def _fire_change(self):
        if self._on_change:
            self._on_change()

    def _renumber(self):
        for i, (_, _, frame) in enumerate(self.rows):
            children = frame.winfo_children()
            if children:
                children[0].config(text=str(i + 1))

    # --- preview ---
    def update_preview(self):
        c = self.preview_canvas
        c.delete("all")
        try:
            segments = self.get_segments()
        except ValueError:
            return
        if not segments:
            return

        points = [(0.0, 0.0)]
        for length, angle_deg in segments:
            x0, y0 = points[-1]
            rad = np.deg2rad(angle_deg)
            points.append((x0 + length * np.cos(rad), y0 + length * np.sin(rad)))

        w = c.winfo_width() or 300
        h = c.winfo_height() or 80
        margin = 20
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        x_range = max(x_max - x_min, 0.1)
        y_range = max(y_max - y_min, 0.1)
        scale = min((w - 2 * margin) / x_range, (h - 2 * margin) / y_range)
        if y_range < 0.01 * x_range:
            scale = (w - 2 * margin) / x_range

        def to_canvas(px, py):
            return margin + (px - x_min) * scale, h / 2 - (py - (y_min + y_max) / 2) * scale

        colors = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336",
                  "#00BCD4", "#795548", "#607D8B"]
        for i, ((x0, y0), (x1, y1)) in enumerate(zip(points[:-1], points[1:])):
            cx0, cy0 = to_canvas(x0, y0)
            cx1, cy1 = to_canvas(x1, y1)
            color = colors[i % len(colors)]
            c.create_line(cx0, cy0, cx1, cy1, fill=color, width=4, capstyle="round")
            mid_cx, mid_cy = (cx0 + cx1) / 2, (cy0 + cy1) / 2 - 10
            c.create_text(mid_cx, mid_cy, text=f"{segments[i][1]}\u00b0",
                          fill=color, font=("Arial", 8, "bold"))

        cx0, cy0 = to_canvas(*points[0])
        c.create_text(cx0, cy0 + 12, text="Inlet", fill="#666", font=("Arial", 7))
        cxN, cyN = to_canvas(*points[-1])
        c.create_text(cxN, cyN + 12, text="Outlet", fill="#666", font=("Arial", 7))


# ============================================================================
# MAIN GUI APPLICATION
# ============================================================================

class SlugCapturingApp:
    """Main application window."""

    def __init__(self, root, license_info=None):
        self.root = root
        self.root.geometry("1280x800")

        self.sim = None
        self._license_info = license_info

        # File state
        self._project_path = None
        self._dirty = False

        # Undo / redo
        self._undo_mgr = UndoManager()
        self._undo_mgr.set_change_callback(self._on_undo_state_change)
        self._suppress_undo = False

        # Playback state
        self._snap_idx = 0
        self._playing = False
        self._play_after_id = None
        self._slider_updating = False

        self._build_menu()
        self._build_gui()
        self._bind_shortcuts()

        self._load_state(DEFAULT_STATE, push_undo=False)
        self._undo_mgr.clear()
        self._set_dirty(False)
        self._enable_playback(False)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================ menu
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New              Ctrl+N", command=self.file_new)
        file_menu.add_command(label="Open...          Ctrl+O", command=self.file_open)
        file_menu.add_separator()
        file_menu.add_command(label="Save             Ctrl+S", command=self.file_save)
        file_menu.add_command(label="Save As...       Ctrl+Shift+S", command=self.file_save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        self._edit_menu = edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo             Ctrl+Z", command=self.edit_undo, state="disabled")
        edit_menu.add_command(label="Redo             Ctrl+Y", command=self.edit_redo, state="disabled")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About...", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _bind_shortcuts(self):
        self.root.bind("<Control-n>", lambda e: self.file_new())
        self.root.bind("<Control-o>", lambda e: self.file_open())
        self.root.bind("<Control-s>", lambda e: self.file_save())
        self.root.bind("<Control-S>", lambda e: self.file_save_as())
        self.root.bind("<Control-z>", lambda e: self.edit_undo())
        self.root.bind("<Control-y>", lambda e: self.edit_redo())
        # Playback shortcuts
        self.root.bind("<space>", lambda e: self._playback_toggle())
        self.root.bind("<Left>", lambda e: self._playback_prev())
        self.root.bind("<Right>", lambda e: self._playback_next())
        self.root.bind("<Home>", lambda e: self._playback_first())
        self.root.bind("<End>", lambda e: self._playback_last())

    # ================================================================ gui
    def _build_gui(self):
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        # ---- LEFT PANEL ----
        left = ttk.Frame(paned, width=370)
        paned.add(left, weight=0)

        left_canvas = tk.Canvas(left, width=350)
        left_scroll = ttk.Scrollbar(left, orient="vertical", command=left_canvas.yview)
        left_inner = ttk.Frame(left_canvas)
        left_inner.bind("<Configure>",
                        lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=left_inner, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scroll.pack(side="right", fill="y")

        ttk.Label(left_inner, text="Pipeline & Fluid Parameters",
                  font=("Arial", 12, "bold")).pack(anchor="w", pady=(4, 8))

        # Pipeline Segments
        geo_frame = ttk.LabelFrame(left_inner, text="Pipeline Segments", padding=6)
        geo_frame.pack(fill="x", padx=4, pady=2)
        self.segment_table = SegmentTable(geo_frame, on_change=self._on_param_change)
        self.segment_table.pack(fill="x")

        diam_frame = ttk.Frame(geo_frame)
        diam_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(diam_frame, text="Pipe diameter D (m):").pack(side="left")
        self.var_D = tk.StringVar(value="0.078")
        ttk.Entry(diam_frame, textvariable=self.var_D, width=10, justify="center").pack(side="right")

        # Fluid Properties
        fluid_frame = ttk.LabelFrame(left_inner, text="Fluid Properties", padding=6)
        fluid_frame.pack(fill="x", padx=4, pady=6)
        self.fluid_vars = {}
        for key, label, default in [
            ("rho_L", "Liquid density \u03c1\u2097 (kg/m\u00b3)", "998.0"),
            ("rho_G", "Gas density \u03c1\u1d33 (kg/m\u00b3)", "1.2"),
            ("mu_L", "Liquid viscosity \u03bc\u2097 (Pa\u00b7s)", "0.001"),
            ("mu_G", "Gas viscosity \u03bc\u1d33 (Pa\u00b7s)", "1.8e-5"),
        ]:
            row = ttk.Frame(fluid_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, width=10, justify="center").pack(side="right")
            self.fluid_vars[key] = var

        # Flow Conditions
        flow_frame = ttk.LabelFrame(left_inner, text="Flow Conditions", padding=6)
        flow_frame.pack(fill="x", padx=4, pady=2)
        self.flow_vars = {}
        for key, label, default in [
            ("U_sL", "Superficial liquid vel. U\u209b\u2097 (m/s)", "1.0"),
            ("U_sG", "Superficial gas vel. U\u209b\u1d33 (m/s)", "3.0"),
        ]:
            row = ttk.Frame(flow_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, width=10, justify="center").pack(side="right")
            self.flow_vars[key] = var

        # Numerical Settings
        num_frame = ttk.LabelFrame(left_inner, text="Numerical Settings", padding=6)
        num_frame.pack(fill="x", padx=4, pady=6)
        self.num_vars = {}
        for key, label, default in [
            ("N_cells", "Number of cells", "500"),
            ("CFL", "Max CFL number", "0.45"),
            ("t_end", "Simulation time (s)", "30.0"),
        ]:
            row = ttk.Frame(num_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, width=10, justify="center").pack(side="right")
            self.num_vars[key] = var

        # Probe locations
        probe_row = ttk.Frame(num_frame)
        probe_row.pack(fill="x", pady=1)
        ttk.Label(probe_row, text="Probe locations (%)").pack(side="left")
        self.var_probes = tk.StringVar(value="25, 50, 75")
        ttk.Entry(probe_row, textvariable=self.var_probes, width=14, justify="center").pack(side="right")

        # Trace all scalar vars for undo
        self.var_D.trace_add("write", self._on_scalar_var_write)
        self.var_probes.trace_add("write", self._on_scalar_var_write)
        for v in self.fluid_vars.values():
            v.trace_add("write", self._on_scalar_var_write)
        for v in self.flow_vars.values():
            v.trace_add("write", self._on_scalar_var_write)
        for v in self.num_vars.values():
            v.trace_add("write", self._on_scalar_var_write)

        # Buttons
        btn_frame = ttk.Frame(left_inner)
        btn_frame.pack(fill="x", padx=4, pady=8)
        self.btn_run = ttk.Button(btn_frame, text="Run Simulation", command=self.run_simulation)
        self.btn_run.pack(fill="x", pady=2)
        self.btn_stop = ttk.Button(btn_frame, text="Stop", command=self.stop_simulation, state="disabled")
        self.btn_stop.pack(fill="x", pady=2)

        # Progress
        self.progress_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(left_inner, variable=self.progress_var, maximum=100).pack(fill="x", padx=4, pady=2)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(left_inner, textvariable=self.status_var, font=("Arial", 9)).pack(anchor="w", padx=4)

        # ---- RIGHT PANEL ----
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Holdup Profile (spatial, scrubbable)
        self.fig_holdup = Figure(figsize=(8, 4), dpi=100)
        self.ax_holdup = self.fig_holdup.add_subplot(111)
        self._init_holdup_ax()
        self.fig_holdup.tight_layout()
        tab1 = ttk.Frame(self.notebook)
        self.canvas_holdup = FigureCanvasTkAgg(self.fig_holdup, tab1)
        self.canvas_holdup.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab1, text="Holdup Profile")

        # Tab 2: Probe Holdup Time Series
        self.fig_probes = Figure(figsize=(8, 4), dpi=100)
        self.ax_probes = self.fig_probes.add_subplot(111)
        self._init_probes_ax()
        self.fig_probes.tight_layout()
        tab2 = ttk.Frame(self.notebook)
        self.canvas_probes = FigureCanvasTkAgg(self.fig_probes, tab2)
        self.canvas_probes.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab2, text="Holdup at Probes")

        # Tab 3: Probe Velocity Time Series  [NEW]
        self.fig_vel_probes = Figure(figsize=(8, 4), dpi=100)
        self.ax_vel_probes = self.fig_vel_probes.add_subplot(111)
        self.ax_vel_probes.set_xlabel("Time (s)")
        self.ax_vel_probes.set_ylabel("Velocity (m/s)")
        self.ax_vel_probes.set_title("Velocity at Probe Locations")
        self.fig_vel_probes.tight_layout()
        tab3 = ttk.Frame(self.notebook)
        self.canvas_vel_probes = FigureCanvasTkAgg(self.fig_vel_probes, tab3)
        self.canvas_vel_probes.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab3, text="Velocity at Probes")

        # Tab 4: Velocity Profiles (spatial, scrubbable)
        self.fig_vel = Figure(figsize=(8, 4), dpi=100)
        self.ax_vel = self.fig_vel.add_subplot(111)
        self.ax_vel.set_xlabel("Position along pipe (m)")
        self.ax_vel.set_ylabel("Velocity (m/s)")
        self.ax_vel.set_title("Velocity Profiles")
        self.fig_vel.tight_layout()
        tab4 = ttk.Frame(self.notebook)
        self.canvas_vel = FigureCanvasTkAgg(self.fig_vel, tab4)
        self.canvas_vel.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab4, text="Velocity Profiles")

        # Tab 5: Pressure Profile (spatial, scrubbable)
        self.fig_pres = Figure(figsize=(8, 4), dpi=100)
        self.ax_pres = self.fig_pres.add_subplot(111)
        self.ax_pres.set_xlabel("Position along pipe (m)")
        self.ax_pres.set_ylabel("Pressure (Pa)")
        self.ax_pres.set_title("Pressure Profile (estimated)")
        self.fig_pres.tight_layout()
        tab5 = ttk.Frame(self.notebook)
        self.canvas_pres = FigureCanvasTkAgg(self.fig_pres, tab5)
        self.canvas_pres.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab5, text="Pressure Profile")

        # Tab 6: Slug Statistics
        tab6 = ttk.Frame(self.notebook)
        self.notebook.add(tab6, text="Slug Statistics")
        self.stats_text = tk.Text(tab6, font=("Courier", 11), wrap="word",
                                  state="disabled", bg="#f5f5f5")
        self.stats_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Tab 7: Pipeline Elevation Profile
        self.fig_elev = Figure(figsize=(8, 3), dpi=100)
        self.ax_elev = self.fig_elev.add_subplot(111)
        self.ax_elev.set_xlabel("Horizontal distance (m)")
        self.ax_elev.set_ylabel("Elevation (m)")
        self.ax_elev.set_title("Pipeline Elevation Profile")
        self.fig_elev.tight_layout()
        tab7 = ttk.Frame(self.notebook)
        self.canvas_elev = FigureCanvasTkAgg(self.fig_elev, tab7)
        self.canvas_elev.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab7, text="Pipeline Profile")

        # ---- PLAYBACK TOOLBAR ----
        pb = ttk.Frame(right)
        pb.pack(fill="x", padx=4, pady=(4, 2))

        self.btn_first = ttk.Button(pb, text="|<", width=3, command=self._playback_first)
        self.btn_first.pack(side="left")
        self.btn_prev = ttk.Button(pb, text="<", width=3, command=self._playback_prev)
        self.btn_prev.pack(side="left", padx=(2, 0))
        self.btn_play = ttk.Button(pb, text="Play", width=5, command=self._playback_toggle)
        self.btn_play.pack(side="left", padx=2)
        self.btn_next = ttk.Button(pb, text=">", width=3, command=self._playback_next)
        self.btn_next.pack(side="left")
        self.btn_last = ttk.Button(pb, text=">|", width=3, command=self._playback_last)
        self.btn_last.pack(side="left", padx=(2, 0))

        self.time_slider = ttk.Scale(pb, from_=0, to=0, orient="horizontal",
                                     command=self._on_slider_move)
        self.time_slider.pack(side="left", fill="x", expand=True, padx=8)

        self.playback_label = ttk.Label(pb, text="No data", width=32, anchor="e")
        self.playback_label.pack(side="right")

    def _init_holdup_ax(self):
        self.ax_holdup.set_xlabel("Position along pipe (m)")
        self.ax_holdup.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_holdup.set_ylim(0, 1.05)
        self.ax_holdup.set_title("Liquid Holdup Profile")

    def _init_probes_ax(self):
        self.ax_probes.set_xlabel("Time (s)")
        self.ax_probes.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_probes.set_ylim(0, 1.05)
        self.ax_probes.set_title("Holdup at Probe Locations")

    # ========================================================== state I/O
    def _get_state(self):
        try:
            segs = self.segment_table.get_segments_as_dicts()
        except ValueError:
            segs = [{"length": 36.0, "angle": 0.0}]
        return {
            "segments": segs,
            "D": self.var_D.get(),
            "rho_L": self.fluid_vars["rho_L"].get(),
            "rho_G": self.fluid_vars["rho_G"].get(),
            "mu_L": self.fluid_vars["mu_L"].get(),
            "mu_G": self.fluid_vars["mu_G"].get(),
            "U_sL": self.flow_vars["U_sL"].get(),
            "U_sG": self.flow_vars["U_sG"].get(),
            "N_cells": self.num_vars["N_cells"].get(),
            "CFL": self.num_vars["CFL"].get(),
            "t_end": self.num_vars["t_end"].get(),
            "probe_pcts": self.var_probes.get(),
        }

    def _load_state(self, state, push_undo=True):
        self._suppress_undo = True
        self.segment_table.set_segments(state.get("segments", DEFAULT_STATE["segments"]))
        self.var_D.set(str(state.get("D", DEFAULT_STATE["D"])))
        self.fluid_vars["rho_L"].set(str(state.get("rho_L", DEFAULT_STATE["rho_L"])))
        self.fluid_vars["rho_G"].set(str(state.get("rho_G", DEFAULT_STATE["rho_G"])))
        self.fluid_vars["mu_L"].set(str(state.get("mu_L", DEFAULT_STATE["mu_L"])))
        self.fluid_vars["mu_G"].set(str(state.get("mu_G", DEFAULT_STATE["mu_G"])))
        self.flow_vars["U_sL"].set(str(state.get("U_sL", DEFAULT_STATE["U_sL"])))
        self.flow_vars["U_sG"].set(str(state.get("U_sG", DEFAULT_STATE["U_sG"])))
        self.num_vars["N_cells"].set(str(state.get("N_cells", DEFAULT_STATE["N_cells"])))
        self.num_vars["CFL"].set(str(state.get("CFL", DEFAULT_STATE["CFL"])))
        self.num_vars["t_end"].set(str(state.get("t_end", DEFAULT_STATE["t_end"])))
        self.var_probes.set(str(state.get("probe_pcts", DEFAULT_STATE["probe_pcts"])))
        self._suppress_undo = False

    # ========================================================== undo / redo
    def _on_scalar_var_write(self, *_):
        if not self._suppress_undo:
            self._on_param_change()

    def _on_param_change(self):
        if self._suppress_undo:
            return
        self._undo_mgr.push(self._get_state())
        self._set_dirty(True)

    def _on_undo_state_change(self, can_undo, can_redo):
        self._edit_menu.entryconfig(0, state="normal" if can_undo else "disabled")
        self._edit_menu.entryconfig(1, state="normal" if can_redo else "disabled")

    def edit_undo(self):
        restored = self._undo_mgr.undo(self._get_state())
        if restored:
            self._load_state(restored, push_undo=False)
            self._set_dirty(True)

    def edit_redo(self):
        restored = self._undo_mgr.redo(self._get_state())
        if restored:
            self._load_state(restored, push_undo=False)
            self._set_dirty(True)

    # ========================================================== file ops
    def _set_dirty(self, dirty):
        self._dirty = dirty
        self._update_title()

    def _update_title(self):
        name = os.path.basename(self._project_path) if self._project_path else "Untitled"
        marker = " *" if self._dirty else ""
        title = f"{name}{marker} \u2014 {__app_name__} v{__version__}"
        if self._license_info:
            org = self._license_info.get("organization", "")
            if org:
                title += f" \u2014 Licensed to: {org}"
        self.root.title(title)

    def _confirm_discard(self):
        if not self._dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved Changes",
                                           "You have unsaved changes. Save before continuing?")
        if answer is None:
            return False
        if answer:
            self.file_save()
            return not self._dirty
        return True

    def file_new(self):
        if not self._confirm_discard():
            return
        self._project_path = None
        self._undo_mgr.clear()
        self._load_state(DEFAULT_STATE, push_undo=False)
        self._set_dirty(False)

    def file_open(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(title="Open Project", filetypes=PROJECT_FILETYPES,
                                          defaultextension=PROJECT_EXT)
        if not path:
            return
        try:
            with open(path, "r") as f:
                state = json.load(f)
        except Exception as exc:
            messagebox.showerror("Open Failed", f"Could not read file:\n{exc}")
            return
        self._project_path = path
        self._undo_mgr.clear()
        self._load_state(state, push_undo=False)
        self._set_dirty(False)

    def file_save(self):
        if self._project_path is None:
            self.file_save_as()
            return
        self._write_project(self._project_path)

    def file_save_as(self):
        path = filedialog.asksaveasfilename(title="Save Project As", filetypes=PROJECT_FILETYPES,
                                            defaultextension=PROJECT_EXT)
        if not path:
            return
        self._project_path = path
        self._write_project(path)

    def _write_project(self, path):
        state = self._get_state()
        try:
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as exc:
            messagebox.showerror("Save Failed", f"Could not write file:\n{exc}")
            return
        self._set_dirty(False)

    def _on_close(self):
        if self._confirm_discard():
            self._playback_stop()
            if self.sim and self.sim.is_running:
                self.sim.stop()
            self.root.destroy()

    def _show_about(self):
        lines = [
            f"{__app_name__}",
            f"Version {__version__}  (built {__build_date__})",
            f"Author: {__author__}",
            "",
            "1D Slug Capturing Two-Fluid Model",
            "Issa & Kempf (2003), Int. J. Multiphase Flow, 29, 69-95.",
        ]
        if self._license_info:
            lines.append("")
            lines.append(f"Licensed to: {self._license_info.get('licensee', 'N/A')}")
            lines.append(f"Organization: {self._license_info.get('organization', 'N/A')}")
            lines.append(f"License type: {self._license_info.get('license_type', 'N/A')}")
            lines.append(f"Expires: {self._license_info.get('expiry_date', 'N/A')}")
        else:
            lines.append("")
            lines.append("(Development mode \u2014 no license)")
        messagebox.showinfo("About", "\n".join(lines))

    # ======================================================= probe parsing
    def _parse_probe_positions(self):
        """Parse probe % entries into fractional positions [0-1]."""
        text = self.var_probes.get().strip()
        fracs = []
        for tok in text.replace(";", ",").split(","):
            tok = tok.strip()
            if tok:
                val = float(tok) / 100.0
                if not (0.0 < val < 1.0):
                    raise ValueError(f"Probe position {tok}% must be between 0 and 100 (exclusive).")
                fracs.append(val)
        if not fracs:
            raise ValueError("At least one probe location is required.")
        return sorted(fracs)

    # ======================================================= sim params
    def _get_params(self):
        segments = self.segment_table.get_segments()
        return SimulationParameters(
            segments=segments,
            D=float(self.var_D.get()),
            rho_L=float(self.fluid_vars["rho_L"].get()),
            rho_G=float(self.fluid_vars["rho_G"].get()),
            mu_L=float(self.fluid_vars["mu_L"].get()),
            mu_G=float(self.fluid_vars["mu_G"].get()),
            U_sL=float(self.flow_vars["U_sL"].get()),
            U_sG=float(self.flow_vars["U_sG"].get()),
            N_cells=int(self.num_vars["N_cells"].get()),
            CFL=float(self.num_vars["CFL"].get()),
            t_end=float(self.num_vars["t_end"].get()),
        )

    # ===================================== spatial plot helpers (reusable)
    def _draw_holdup_spatial(self, x, alpha_L, t, seg_boundaries=None):
        """Draw holdup vs position from given arrays."""
        self.ax_holdup.clear()
        self.ax_holdup.plot(x, alpha_L, "b-", linewidth=0.8)
        self.ax_holdup.set_xlabel("Position along pipe (m)")
        self.ax_holdup.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_holdup.set_ylim(0, 1.05)
        self.ax_holdup.set_title(f"Liquid Holdup Profile at t = {t:.2f} s")
        self.ax_holdup.axhline(y=0.85, color="r", linestyle="--", alpha=0.4, label="Slug threshold")
        if seg_boundaries is not None:
            for b in seg_boundaries[1:-1]:
                self.ax_holdup.axvline(x=x[min(b, len(x) - 1)], color="gray",
                                      linestyle=":", alpha=0.5)
        self.ax_holdup.legend(fontsize=8)
        self.ax_holdup.grid(True, alpha=0.3)
        self.fig_holdup.tight_layout()
        self.canvas_holdup.draw()

    def _draw_velocity_spatial(self, x, u_L, u_G, t):
        """Draw velocity profiles vs position from given arrays."""
        self.ax_vel.clear()
        self.ax_vel.plot(x, u_L, "b-", linewidth=0.8, label="Liquid u\u2097")
        self.ax_vel.plot(x, u_G, "r-", linewidth=0.8, label="Gas u\u1d33")
        self.ax_vel.set_xlabel("Position along pipe (m)")
        self.ax_vel.set_ylabel("Velocity (m/s)")
        self.ax_vel.set_title(f"Velocity Profiles at t = {t:.2f} s")
        self.ax_vel.legend(fontsize=8)
        self.ax_vel.grid(True, alpha=0.3)
        self.fig_vel.tight_layout()
        self.canvas_vel.draw()

    def _draw_pressure_spatial(self, alpha_L, u_L, u_G, t):
        """Compute and draw pressure profile from given field arrays."""
        sim = self.sim
        if sim is None:
            return
        try:
            from slug_capturing_equations import compute_all_geometry, compute_all_shear

            x = sim.mesh["x_cell"]
            dx = sim.mesh["dx"]
            beta = sim.mesh["beta"]
            N = len(x)

            geom = compute_all_geometry(alpha_L, sim.params.D)
            shear = compute_all_shear(u_L, u_G,
                                      sim.params.rho_L, sim.params.rho_G,
                                      sim.params.mu_L, sim.params.mu_G,
                                      geom["D_hL"], geom["D_hG"])

            A_pipe = np.pi * sim.params.D ** 2 / 4.0
            alpha_G = np.maximum(1.0 - alpha_L, 1e-6)
            dp_dx = (
                -sim.params.rho_G * 9.81 * np.sin(beta)
                - (shear["tau_wG"] * geom["S_G"] + shear["tau_i"] * geom["S_i"])
                / (alpha_G * A_pipe)
            )

            p = np.zeros(N)
            for i in range(N - 2, -1, -1):
                p[i] = p[i + 1] - dp_dx[i] * dx[i]

            self.ax_pres.clear()
            self.ax_pres.plot(x, p / 1000.0, "g-", linewidth=0.8)
            self.ax_pres.set_xlabel("Position along pipe (m)")
            self.ax_pres.set_ylabel("Gauge Pressure (kPa)")
            self.ax_pres.set_title(f"Estimated Pressure Profile at t = {t:.2f} s")
            self.ax_pres.grid(True, alpha=0.3)
            self.fig_pres.tight_layout()
            self.canvas_pres.draw()
        except Exception:
            pass  # silently skip if fields are degenerate

    def _draw_probe_holdup(self):
        """Draw holdup time series at all probes."""
        probes = self.sim.probes
        if len(probes.time) < 2:
            return
        self.ax_probes.clear()
        colors_p = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"]
        for k in range(len(probes.positions)):
            self.ax_probes.plot(probes.time, probes.alpha_L[k],
                                color=colors_p[k % len(colors_p)], linewidth=0.6,
                                label=probes.labels[k])
        self.ax_probes.set_xlabel("Time (s)")
        self.ax_probes.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_probes.set_ylim(0, 1.05)
        self.ax_probes.set_title("Holdup at Probe Locations")
        self.ax_probes.legend(fontsize=7)
        self.ax_probes.grid(True, alpha=0.3)
        self.fig_probes.tight_layout()
        self.canvas_probes.draw()

    def _draw_probe_velocity(self):
        """Draw velocity time series at all probes (liquid=solid, gas=dashed)."""
        probes = self.sim.probes
        if len(probes.time) < 2:
            return
        self.ax_vel_probes.clear()
        colors_p = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"]
        for k in range(len(probes.positions)):
            c = colors_p[k % len(colors_p)]
            self.ax_vel_probes.plot(probes.time, probes.u_L[k],
                                    color=c, linewidth=0.6, linestyle="-",
                                    label=f"u_L {probes.labels[k]}")
            self.ax_vel_probes.plot(probes.time, probes.u_G[k],
                                    color=c, linewidth=0.6, linestyle="--",
                                    label=f"u_G {probes.labels[k]}")
        self.ax_vel_probes.set_xlabel("Time (s)")
        self.ax_vel_probes.set_ylabel("Velocity (m/s)")
        self.ax_vel_probes.set_title("Velocity at Probe Locations (solid=liquid, dashed=gas)")
        self.ax_vel_probes.legend(fontsize=7)
        self.ax_vel_probes.grid(True, alpha=0.3)
        self.fig_vel_probes.tight_layout()
        self.canvas_vel_probes.draw()

    def _draw_elevation(self, segments):
        self.ax_elev.clear()
        self.ax_elev.set_xlabel("Horizontal distance (m)")
        self.ax_elev.set_ylabel("Elevation (m)")
        self.ax_elev.set_title("Pipeline Elevation Profile")
        x, y = [0.0], [0.0]
        for length, angle_deg in segments:
            rad = np.deg2rad(angle_deg)
            x.append(x[-1] + length * np.cos(rad))
            y.append(y[-1] + length * np.sin(rad))
        colors = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336",
                  "#00BCD4", "#795548", "#607D8B"]
        for i in range(len(segments)):
            color = colors[i % len(colors)]
            self.ax_elev.plot([x[i], x[i + 1]], [y[i], y[i + 1]],
                             color=color, linewidth=3,
                             label=f"Seg {i + 1}: {segments[i][0]}m @ {segments[i][1]}\u00b0")
        self.ax_elev.legend(fontsize=8)
        self.ax_elev.grid(True, alpha=0.3)
        self.ax_elev.set_aspect("equal", adjustable="datalim")
        self.fig_elev.tight_layout()
        self.canvas_elev.draw()

    # ================================================= playback controls
    def _enable_playback(self, enabled):
        """Enable or disable the playback toolbar."""
        st = "normal" if enabled else "disabled"
        for btn in (self.btn_first, self.btn_prev, self.btn_play, self.btn_next, self.btn_last):
            btn.config(state=st)
        self.time_slider.state(["!disabled"] if enabled else ["disabled"])

    def _playback_first(self):
        self._set_snap_index(0)

    def _playback_prev(self):
        self._set_snap_index(max(0, self._snap_idx - 1))

    def _playback_next(self):
        if self.sim and self.sim.snapshots:
            self._set_snap_index(min(len(self.sim.snapshots) - 1, self._snap_idx + 1))

    def _playback_last(self):
        if self.sim and self.sim.snapshots:
            self._set_snap_index(len(self.sim.snapshots) - 1)

    def _playback_toggle(self):
        if self._playing:
            self._playback_stop()
        else:
            self._playback_start()

    def _playback_start(self):
        if not self.sim or not self.sim.snapshots:
            return
        if self.sim.is_running:
            return
        self._playing = True
        self.btn_play.config(text="Pause")
        # If at end, restart from beginning
        if self._snap_idx >= len(self.sim.snapshots) - 1:
            self._snap_idx = 0
        self._playback_advance()

    def _playback_stop(self):
        self._playing = False
        self.btn_play.config(text="Play")
        if self._play_after_id is not None:
            self.root.after_cancel(self._play_after_id)
            self._play_after_id = None

    def _playback_advance(self):
        if not self._playing or not self.sim:
            return
        n = len(self.sim.snapshots)
        if self._snap_idx < n - 1:
            self._set_snap_index(self._snap_idx + 1)
            self._play_after_id = self.root.after(50, self._playback_advance)
        else:
            self._playback_stop()

    def _set_snap_index(self, idx):
        """Set current snapshot index, update slider, and redraw spatial plots."""
        if not self.sim or not self.sim.snapshots:
            return
        n = len(self.sim.snapshots)
        idx = max(0, min(idx, n - 1))
        self._snap_idx = idx

        self._slider_updating = True
        self.time_slider.configure(to=max(n - 1, 0))
        self.time_slider.set(idx)
        self._slider_updating = False

        self._draw_snapshot(idx)

    def _on_slider_move(self, value):
        """Called when the slider is moved (by user drag or programmatic set)."""
        if self._slider_updating:
            return
        if self.sim and self.sim.is_running:
            return
        if not self.sim or not self.sim.snapshots:
            return
        idx = int(float(value))
        idx = max(0, min(idx, len(self.sim.snapshots) - 1))
        self._snap_idx = idx
        self._draw_snapshot(idx)

    def _draw_snapshot(self, idx):
        """Redraw all spatial plots from a stored snapshot."""
        snap = self.sim.snapshots[idx]
        t = snap["t"]
        alpha_L = snap["alpha_L"]
        u_L = snap["u_L"]
        u_G = snap["u_G"]
        x = self.sim.mesh["x_cell"]
        n = len(self.sim.snapshots)

        self.playback_label.config(
            text=f"{idx + 1} / {n}  |  t = {t:.3f} / {self.sim.params.t_end:.1f} s"
        )

        seg_b = self.sim.mesh.get("seg_boundaries")
        self._draw_holdup_spatial(x, alpha_L, t, seg_b)
        self._draw_velocity_spatial(x, u_L, u_G, t)
        self._draw_pressure_spatial(alpha_L, u_L, u_G, t)

    # ============================================================ simulation
    def run_simulation(self):
        try:
            params = self._get_params()
            probe_fracs = self._parse_probe_positions()
        except (ValueError, Exception) as e:
            messagebox.showerror("Input Error", str(e))
            return

        self._draw_elevation(params.segments)

        self.sim = SlugCapturingSimulation(params, probe_positions=probe_fracs)
        self.sim.initialize()

        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._enable_playback(False)
        self._playback_stop()
        self.status_var.set("Running simulation...")
        self.progress_var.set(0)

        for ax in [self.ax_holdup, self.ax_probes, self.ax_vel_probes, self.ax_vel, self.ax_pres]:
            ax.clear()

        self.sim.run(
            on_step=lambda sim: self.root.after(0, self._update_plots),
            on_done=lambda sim: self.root.after(0, self._on_simulation_done),
            update_interval=50,
        )

    def stop_simulation(self):
        if self.sim and self.sim.is_running:
            self.sim.stop()
            self.status_var.set("Simulation stopped by user")

    def _update_plots(self):
        """Update all plots during live simulation."""
        sim = self.sim
        if sim is None:
            return

        x = sim.mesh["x_cell"]

        # Progress bar
        self.progress_var.set(sim.progress * 100)
        self.status_var.set(
            f"t = {sim.t:.3f} s | step {sim.step_count} | "
            f"dt = {sim.dt:.2e} s | {sim.progress * 100:.1f}%"
        )

        # Spatial plots from live data
        seg_b = sim.mesh.get("seg_boundaries")
        self._draw_holdup_spatial(x, sim.alpha_L, sim.t, seg_b)
        self._draw_velocity_spatial(x, sim.u_L, sim.u_G, sim.t)

        # Probe time series
        self._draw_probe_holdup()
        self._draw_probe_velocity()

        # Keep slider tracking latest snapshot
        if sim.snapshots:
            n = len(sim.snapshots)
            self._slider_updating = True
            self.time_slider.configure(to=max(n - 1, 0))
            self.time_slider.set(n - 1)
            self._slider_updating = False
            self._snap_idx = n - 1
            self.playback_label.config(
                text=f"{n} / {n}  |  t = {sim.t:.3f} / {sim.params.t_end:.1f} s"
            )

    def _on_simulation_done(self):
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.progress_var.set(100)

        if self.sim:
            self.status_var.set(
                f"Completed: t = {self.sim.t:.3f} s, {self.sim.step_count} steps"
            )
            self._update_plots()
            self._update_statistics()

            # Final pressure from live data
            self._draw_pressure_spatial(self.sim.alpha_L, self.sim.u_L, self.sim.u_G, self.sim.t)

            # Enable playback and set slider to end
            n = len(self.sim.snapshots)
            self._slider_updating = True
            self.time_slider.configure(to=max(n - 1, 0))
            self.time_slider.set(n - 1)
            self._slider_updating = False
            self._snap_idx = n - 1
            self._enable_playback(True)

    def _update_statistics(self):
        self.stats_text.config(state="normal")
        self.stats_text.delete("1.0", "end")

        sim = self.sim
        if sim is None:
            return

        lines = []
        lines.append("=" * 60)
        lines.append("  SLUG CAPTURING SIMULATION RESULTS")
        lines.append("  Issa & Kempf (2003) Two-Fluid Model")
        lines.append("=" * 60)
        lines.append("")

        p = sim.params
        lines.append("INPUT PARAMETERS:")
        lines.append(f"  Pipe diameter:     {p.D:.4f} m")
        lines.append(f"  Pipeline segments: {len(p.segments)}")
        total_L = sum(s[0] for s in p.segments)
        lines.append(f"  Total length:      {total_L:.1f} m")
        for i, (length, angle) in enumerate(p.segments):
            lines.append(f"    Seg {i + 1}: {length:.1f} m @ {angle:.1f}\u00b0")
        lines.append(f"  Liquid density:    {p.rho_L:.1f} kg/m\u00b3")
        lines.append(f"  Gas density:       {p.rho_G:.2f} kg/m\u00b3")
        lines.append(f"  Liquid viscosity:  {p.mu_L:.2e} Pa\u00b7s")
        lines.append(f"  Gas viscosity:     {p.mu_G:.2e} Pa\u00b7s")
        lines.append(f"  U_sL:              {p.U_sL:.2f} m/s")
        lines.append(f"  U_sG:              {p.U_sG:.2f} m/s")
        lines.append(f"  Grid cells:        {p.N_cells}")
        lines.append(f"  CFL:               {p.CFL}")
        lines.append(f"  Simulation time:   {p.t_end:.1f} s")
        lines.append(f"  Probe locations:   {self.var_probes.get()}")
        lines.append("")

        lines.append("SIMULATION SUMMARY:")
        lines.append(f"  Final time:        {sim.t:.3f} s")
        lines.append(f"  Total steps:       {sim.step_count}")
        lines.append(f"  Final dt:          {sim.dt:.2e} s")
        lines.append(f"  Snapshots stored:  {len(sim.snapshots)}")
        lines.append("")

        stats = sim.get_slug_statistics()
        lines.append("SLUG STATISTICS:")
        if stats:
            lines.append(f"  Slug events detected:    {stats['n_slug_events']}")
            lines.append(f"  Mean slug length:        {stats['mean_length_m']:.3f} m")
            lines.append(f"  Slug frequency:          {stats['slug_frequency_hz']:.3f} Hz")
            lines.append(f"  Mean slug velocity:      {stats['mean_velocity_m_s']:.3f} m/s")
        else:
            lines.append("  No slug events detected (or too few for statistics).")
            lines.append("  Try increasing simulation time or adjusting flow rates.")
        lines.append("")

        U_m = p.U_sL + p.U_sG
        lines.append("REFERENCE VALUES:")
        lines.append(f"  Mixture velocity U_m = U_sL + U_sG = {U_m:.2f} m/s")
        lines.append(f"  Input liquid fraction = U_sL/U_m = {p.U_sL / U_m:.4f}")
        lines.append("")
        lines.append("=" * 60)

        self.stats_text.insert("1.0", "\n".join(lines))
        self.stats_text.config(state="disabled")


# ============================================================================
# ENTRY POINT
# ============================================================================

def _check_license(root):
    """
    Validate the license at startup (only when running as compiled .exe).

    Returns license_info dict if valid, or None to abort.
    """
    # 1. Load the public key (embedded in the .exe bundle)
    pub_path = license_manager.get_public_key_path()
    if not os.path.isfile(pub_path):
        messagebox.showerror("License Error",
                             "Public key not found.\nThe application cannot verify licenses.",
                             parent=root)
        return None

    try:
        pub_key = license_manager.load_public_key(pub_path)
    except Exception as exc:
        messagebox.showerror("License Error", f"Could not load public key:\n{exc}", parent=root)
        return None

    # 2. Look for license.lic in standard locations
    lic_path = license_manager.find_license_file()

    if lic_path is None:
        # Ask user to browse for it
        messagebox.showinfo("License Required",
                            f"{__app_name__} requires a valid license file.\n\n"
                            "Please locate your license.lic file.",
                            parent=root)
        lic_path = filedialog.askopenfilename(
            title="Select License File",
            filetypes=[("License files", "*.lic"), ("All files", "*.*")],
            parent=root,
        )
        if not lic_path:
            return None

    # 3. Load and validate
    try:
        lic_data = license_manager.load_license(lic_path)
    except Exception as exc:
        messagebox.showerror("License Error",
                             f"Could not read license file:\n{exc}", parent=root)
        return None

    valid, msg = license_manager.validate_license(pub_key, lic_data, __version__)
    if not valid:
        messagebox.showerror("License Invalid", msg, parent=root)
        return None

    return lic_data


def main():
    root = tk.Tk()
    root.withdraw()  # hide while checking license

    license_info = None
    if getattr(sys, "frozen", False):
        # Compiled mode — require valid license
        license_info = _check_license(root)
        if license_info is None:
            root.destroy()
            return
    # Development mode — no license required

    root.deiconify()
    app = SlugCapturingApp(root, license_info=license_info)
    root.mainloop()


if __name__ == "__main__":
    main()
