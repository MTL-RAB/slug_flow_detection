#!/usr/bin/env python3
"""
Slug Capturing GUI — 1D Two-Fluid Model
=========================================

Simple tkinter GUI for engineers to define multi-segment pipeline geometry
and run a 1D slug capturing simulation based on:

    Issa & Kempf (2003), Int. J. Multiphase Flow, 29, 69-95.

Usage:
    python slug_capturing_gui.py

The pipeline is defined segment-by-segment. Each segment has:
    - Length (m)
    - Inclination angle (degrees from horizontal)
      Positive = uphill, negative = downhill
      +90 = vertical riser, -90 = vertical downcomer
"""

import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import threading

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from slug_capturing_solver import SimulationParameters, SlugCapturingSimulation


# ============================================================================
# PIPELINE SEGMENT TABLE
# ============================================================================

class SegmentTable(ttk.Frame):
    """
    Editable table for defining pipeline segments.
    Each row: [Segment #] [Length (m)] [Angle (deg)] [Delete button]
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []  # list of (length_var, angle_var, frame)

        # Header
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", pady=(0, 2))
        ttk.Label(hdr, text="#", width=3, anchor="center").pack(side="left")
        ttk.Label(hdr, text="Length (m)", width=12, anchor="center").pack(side="left", padx=2)
        ttk.Label(hdr, text="Angle (\u00b0)", width=12, anchor="center").pack(side="left", padx=2)
        ttk.Label(hdr, text="", width=5).pack(side="left")

        self.table_frame = ttk.Frame(self)
        self.table_frame.pack(fill="both", expand=True)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_frame, text="+ Add Segment", command=self.add_row).pack(side="left")
        ttk.Button(btn_frame, text="Reset to Default", command=self.reset_default).pack(side="left", padx=4)

        # Pipeline preview canvas
        self.preview_canvas = tk.Canvas(self, height=80, bg="white", relief="sunken", bd=1)
        self.preview_canvas.pack(fill="x", pady=(6, 0))

        self.reset_default()

    def add_row(self, length="10.0", angle="0.0"):
        """Add a new segment row."""
        idx = len(self.rows)
        row_frame = ttk.Frame(self.table_frame)
        row_frame.pack(fill="x", pady=1)

        ttk.Label(row_frame, text=str(idx + 1), width=3, anchor="center").pack(side="left")

        length_var = tk.StringVar(value=length)
        angle_var = tk.StringVar(value=angle)

        e_len = ttk.Entry(row_frame, textvariable=length_var, width=12, justify="center")
        e_len.pack(side="left", padx=2)
        e_ang = ttk.Entry(row_frame, textvariable=angle_var, width=12, justify="center")
        e_ang.pack(side="left", padx=2)

        del_btn = ttk.Button(row_frame, text="\u2716", width=3,
                             command=lambda: self.delete_row(row_frame))
        del_btn.pack(side="left", padx=2)

        self.rows.append((length_var, angle_var, row_frame))

        # Bind change events to update preview
        length_var.trace_add("write", lambda *_: self.update_preview())
        angle_var.trace_add("write", lambda *_: self.update_preview())
        self.update_preview()

    def delete_row(self, frame):
        """Remove a segment row."""
        for i, (l, a, f) in enumerate(self.rows):
            if f is frame:
                f.destroy()
                self.rows.pop(i)
                self._renumber()
                self.update_preview()
                return

    def _renumber(self):
        """Re-number segment labels after deletion."""
        for i, (_, _, frame) in enumerate(self.rows):
            children = frame.winfo_children()
            if children:
                children[0].config(text=str(i + 1))

    def reset_default(self):
        """Reset to single 36m horizontal segment (Issa & Kempf test case)."""
        for _, _, frame in self.rows:
            frame.destroy()
        self.rows.clear()
        self.add_row("36.0", "0.0")

    def get_segments(self):
        """
        Parse and return segment list.

        Returns
        -------
        list of (length_m, angle_deg) tuples

        Raises
        ------
        ValueError if any input is invalid
        """
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

    def update_preview(self):
        """Draw a simple side-view sketch of the pipeline segments."""
        c = self.preview_canvas
        c.delete("all")

        try:
            segments = self.get_segments()
        except ValueError:
            return

        if not segments:
            return

        # Compute polyline in physical coordinates
        points = [(0.0, 0.0)]
        for length, angle_deg in segments:
            x0, y0 = points[-1]
            angle_rad = np.deg2rad(angle_deg)
            x1 = x0 + length * np.cos(angle_rad)
            y1 = y0 + length * np.sin(angle_rad)
            points.append((x1, y1))

        # Scale to fit canvas
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
        # If pipeline is flat, use a fixed scale
        if y_range < 0.01 * x_range:
            scale = (w - 2 * margin) / x_range

        def to_canvas(px, py):
            cx = margin + (px - x_min) * scale
            cy = h / 2 - (py - (y_min + y_max) / 2) * scale
            return cx, cy

        # Draw segments with color coding
        colors = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336",
                  "#00BCD4", "#795548", "#607D8B"]
        for i, ((x0, y0), (x1, y1)) in enumerate(zip(points[:-1], points[1:])):
            cx0, cy0 = to_canvas(x0, y0)
            cx1, cy1 = to_canvas(x1, y1)
            color = colors[i % len(colors)]
            c.create_line(cx0, cy0, cx1, cy1, fill=color, width=4, capstyle="round")
            # Label with angle
            mid_cx = (cx0 + cx1) / 2
            mid_cy = (cy0 + cy1) / 2 - 10
            angle = segments[i][1]
            c.create_text(mid_cx, mid_cy, text=f"{angle}\u00b0",
                          fill=color, font=("Arial", 8, "bold"))

        # Flow direction arrow
        cx0, cy0 = to_canvas(*points[0])
        c.create_text(cx0, cy0 + 12, text="Inlet", fill="#666", font=("Arial", 7))
        cxN, cyN = to_canvas(*points[-1])
        c.create_text(cxN, cyN + 12, text="Outlet", fill="#666", font=("Arial", 7))


# ============================================================================
# MAIN GUI APPLICATION
# ============================================================================

class SlugCapturingApp:
    """Main application window."""

    def __init__(self, root):
        self.root = root
        self.root.title("1D Slug Capturing Model — Issa & Kempf (2003)")
        self.root.geometry("1280x800")

        self.sim = None  # current simulation

        self._build_gui()

    def _build_gui(self):
        # Main horizontal paned window
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        # --- LEFT PANEL: Inputs ---
        left = ttk.Frame(paned, width=370)
        paned.add(left, weight=0)

        # Scrollable left panel
        left_canvas = tk.Canvas(left, width=350)
        left_scroll = ttk.Scrollbar(left, orient="vertical", command=left_canvas.yview)
        left_inner = ttk.Frame(left_canvas)

        left_inner.bind("<Configure>",
                        lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=left_inner, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scroll.set)

        left_canvas.pack(side="left", fill="both", expand=True)
        left_scroll.pack(side="right", fill="y")

        # Title
        ttk.Label(left_inner, text="Pipeline & Fluid Parameters",
                  font=("Arial", 12, "bold")).pack(anchor="w", pady=(4, 8))

        # --- Pipeline Geometry ---
        geo_frame = ttk.LabelFrame(left_inner, text="Pipeline Segments", padding=6)
        geo_frame.pack(fill="x", padx=4, pady=2)

        self.segment_table = SegmentTable(geo_frame)
        self.segment_table.pack(fill="x")

        # Pipe diameter
        diam_frame = ttk.Frame(geo_frame)
        diam_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(diam_frame, text="Pipe diameter D (m):").pack(side="left")
        self.var_D = tk.StringVar(value="0.078")
        ttk.Entry(diam_frame, textvariable=self.var_D, width=10, justify="center").pack(side="right")

        # --- Fluid Properties ---
        fluid_frame = ttk.LabelFrame(left_inner, text="Fluid Properties", padding=6)
        fluid_frame.pack(fill="x", padx=4, pady=6)

        self.fluid_vars = {}
        fluid_fields = [
            ("rho_L", "Liquid density \u03c1\u2097 (kg/m\u00b3)", "998.0"),
            ("rho_G", "Gas density \u03c1\u1d33 (kg/m\u00b3)", "1.2"),
            ("mu_L", "Liquid viscosity \u03bc\u2097 (Pa\u00b7s)", "0.001"),
            ("mu_G", "Gas viscosity \u03bc\u1d33 (Pa\u00b7s)", "1.8e-5"),
        ]
        for key, label, default in fluid_fields:
            row = ttk.Frame(fluid_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, width=10, justify="center").pack(side="right")
            self.fluid_vars[key] = var

        # --- Flow Conditions ---
        flow_frame = ttk.LabelFrame(left_inner, text="Flow Conditions", padding=6)
        flow_frame.pack(fill="x", padx=4, pady=2)

        self.flow_vars = {}
        flow_fields = [
            ("U_sL", "Superficial liquid vel. U\u209b\u2097 (m/s)", "1.0"),
            ("U_sG", "Superficial gas vel. U\u209b\u1d33 (m/s)", "3.0"),
        ]
        for key, label, default in flow_fields:
            row = ttk.Frame(flow_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, width=10, justify="center").pack(side="right")
            self.flow_vars[key] = var

        # --- Numerical Settings ---
        num_frame = ttk.LabelFrame(left_inner, text="Numerical Settings", padding=6)
        num_frame.pack(fill="x", padx=4, pady=6)

        self.num_vars = {}
        num_fields = [
            ("N_cells", "Number of cells", "500"),
            ("CFL", "Max CFL number", "0.45"),
            ("t_end", "Simulation time (s)", "30.0"),
        ]
        for key, label, default in num_fields:
            row = ttk.Frame(num_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, width=10, justify="center").pack(side="right")
            self.num_vars[key] = var

        # --- Buttons ---
        btn_frame = ttk.Frame(left_inner)
        btn_frame.pack(fill="x", padx=4, pady=8)

        self.btn_run = ttk.Button(btn_frame, text="Run Simulation",
                                  command=self.run_simulation)
        self.btn_run.pack(fill="x", pady=2)

        self.btn_stop = ttk.Button(btn_frame, text="Stop", command=self.stop_simulation,
                                   state="disabled")
        self.btn_stop.pack(fill="x", pady=2)

        # --- Progress ---
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(left_inner, variable=self.progress_var,
                                            maximum=100)
        self.progress_bar.pack(fill="x", padx=4, pady=2)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(left_inner, textvariable=self.status_var,
                  font=("Arial", 9)).pack(anchor="w", padx=4)

        # --- RIGHT PANEL: Results ---
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Holdup Profile
        self.fig_holdup = Figure(figsize=(8, 4), dpi=100)
        self.ax_holdup = self.fig_holdup.add_subplot(111)
        self.ax_holdup.set_xlabel("Position along pipe (m)")
        self.ax_holdup.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_holdup.set_ylim(0, 1.05)
        self.ax_holdup.set_title("Liquid Holdup Profile")
        self.fig_holdup.tight_layout()
        tab1 = ttk.Frame(self.notebook)
        self.canvas_holdup = FigureCanvasTkAgg(self.fig_holdup, tab1)
        self.canvas_holdup.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab1, text="Holdup Profile")

        # Tab 2: Holdup Time Series at Probes
        self.fig_probes = Figure(figsize=(8, 4), dpi=100)
        self.ax_probes = self.fig_probes.add_subplot(111)
        self.ax_probes.set_xlabel("Time (s)")
        self.ax_probes.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_probes.set_ylim(0, 1.05)
        self.ax_probes.set_title("Holdup at Probe Locations")
        self.fig_probes.tight_layout()
        tab2 = ttk.Frame(self.notebook)
        self.canvas_probes = FigureCanvasTkAgg(self.fig_probes, tab2)
        self.canvas_probes.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab2, text="Probe Time Series")

        # Tab 3: Velocity Profiles
        self.fig_vel = Figure(figsize=(8, 4), dpi=100)
        self.ax_vel = self.fig_vel.add_subplot(111)
        self.ax_vel.set_xlabel("Position along pipe (m)")
        self.ax_vel.set_ylabel("Velocity (m/s)")
        self.ax_vel.set_title("Velocity Profiles")
        self.fig_vel.tight_layout()
        tab3 = ttk.Frame(self.notebook)
        self.canvas_vel = FigureCanvasTkAgg(self.fig_vel, tab3)
        self.canvas_vel.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab3, text="Velocity Profiles")

        # Tab 4: Pressure Profile
        self.fig_pres = Figure(figsize=(8, 4), dpi=100)
        self.ax_pres = self.fig_pres.add_subplot(111)
        self.ax_pres.set_xlabel("Position along pipe (m)")
        self.ax_pres.set_ylabel("Pressure (Pa)")
        self.ax_pres.set_title("Pressure Profile (estimated)")
        self.fig_pres.tight_layout()
        tab4 = ttk.Frame(self.notebook)
        self.canvas_pres = FigureCanvasTkAgg(self.fig_pres, tab4)
        self.canvas_pres.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab4, text="Pressure Profile")

        # Tab 5: Slug Statistics
        tab5 = ttk.Frame(self.notebook)
        self.notebook.add(tab5, text="Slug Statistics")

        self.stats_text = tk.Text(tab5, font=("Courier", 11), wrap="word",
                                  state="disabled", bg="#f5f5f5")
        self.stats_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Tab 6: Pipeline Elevation Profile
        self.fig_elev = Figure(figsize=(8, 3), dpi=100)
        self.ax_elev = self.fig_elev.add_subplot(111)
        self.ax_elev.set_xlabel("Horizontal distance (m)")
        self.ax_elev.set_ylabel("Elevation (m)")
        self.ax_elev.set_title("Pipeline Elevation Profile")
        self.fig_elev.tight_layout()
        tab6 = ttk.Frame(self.notebook)
        self.canvas_elev = FigureCanvasTkAgg(self.fig_elev, tab6)
        self.canvas_elev.get_tk_widget().pack(fill="both", expand=True)
        self.notebook.add(tab6, text="Pipeline Profile")

    # --- Helpers ---

    def _get_params(self):
        """Parse all GUI inputs into a SimulationParameters object."""
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

    def _draw_elevation(self, segments):
        """Draw the pipeline elevation profile on the elevation tab."""
        self.ax_elev.clear()
        self.ax_elev.set_xlabel("Horizontal distance (m)")
        self.ax_elev.set_ylabel("Elevation (m)")
        self.ax_elev.set_title("Pipeline Elevation Profile")

        x, y = [0.0], [0.0]
        for length, angle_deg in segments:
            angle_rad = np.deg2rad(angle_deg)
            x.append(x[-1] + length * np.cos(angle_rad))
            y.append(y[-1] + length * np.sin(angle_rad))

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

    # --- Simulation Control ---

    def run_simulation(self):
        """Parse inputs, initialize simulation, and start running."""
        try:
            params = self._get_params()
        except (ValueError, Exception) as e:
            messagebox.showerror("Input Error", str(e))
            return

        # Draw elevation profile
        self._draw_elevation(params.segments)

        # Create and initialize simulation
        self.sim = SlugCapturingSimulation(params)
        self.sim.initialize()

        # Update UI state
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("Running simulation...")
        self.progress_var.set(0)

        # Clear previous plots
        for ax in [self.ax_holdup, self.ax_probes, self.ax_vel, self.ax_pres]:
            ax.clear()

        # Start simulation
        self.sim.run(
            on_step=lambda sim: self.root.after(0, self._update_plots),
            on_done=lambda sim: self.root.after(0, self._on_simulation_done),
            update_interval=50,
        )

    def stop_simulation(self):
        """Stop a running simulation."""
        if self.sim and self.sim.is_running:
            self.sim.stop()
            self.status_var.set("Simulation stopped by user")

    def _update_plots(self):
        """Update all plots with current simulation state (called from main thread)."""
        sim = self.sim
        if sim is None:
            return

        x = sim.mesh["x_cell"]

        # Progress
        self.progress_var.set(sim.progress * 100)
        self.status_var.set(
            f"t = {sim.t:.3f} s | step {sim.step_count} | "
            f"dt = {sim.dt:.2e} s | {sim.progress * 100:.1f}%"
        )

        # Tab 1: Holdup profile
        self.ax_holdup.clear()
        self.ax_holdup.plot(x, sim.alpha_L, "b-", linewidth=0.8)
        self.ax_holdup.set_xlabel("Position along pipe (m)")
        self.ax_holdup.set_ylabel("Liquid holdup \u03b1\u2097")
        self.ax_holdup.set_ylim(0, 1.05)
        self.ax_holdup.set_title(f"Liquid Holdup Profile at t = {sim.t:.2f} s")
        self.ax_holdup.axhline(y=0.85, color="r", linestyle="--", alpha=0.4,
                               label="Slug threshold")
        # Mark segment boundaries
        for b in sim.mesh["seg_boundaries"][1:-1]:
            self.ax_holdup.axvline(x=x[min(b, len(x) - 1)], color="gray",
                                  linestyle=":", alpha=0.5)
        self.ax_holdup.legend(fontsize=8)
        self.ax_holdup.grid(True, alpha=0.3)
        self.fig_holdup.tight_layout()
        self.canvas_holdup.draw()

        # Tab 2: Probe time series
        probes = sim.probes
        if len(probes.time) > 1:
            self.ax_probes.clear()
            colors_p = ["#2196F3", "#4CAF50", "#FF9800"]
            for k in range(len(probes.positions)):
                self.ax_probes.plot(probes.time, probes.alpha_L[k],
                                   color=colors_p[k % 3], linewidth=0.6,
                                   label=probes.labels[k])
            self.ax_probes.set_xlabel("Time (s)")
            self.ax_probes.set_ylabel("Liquid holdup \u03b1\u2097")
            self.ax_probes.set_ylim(0, 1.05)
            self.ax_probes.set_title("Holdup at Probe Locations")
            self.ax_probes.legend(fontsize=8)
            self.ax_probes.grid(True, alpha=0.3)
            self.fig_probes.tight_layout()
            self.canvas_probes.draw()

        # Tab 3: Velocity profiles
        self.ax_vel.clear()
        self.ax_vel.plot(x, sim.u_L, "b-", linewidth=0.8, label="Liquid u\u2097")
        self.ax_vel.plot(x, sim.u_G, "r-", linewidth=0.8, label="Gas u\u1d33")
        self.ax_vel.set_xlabel("Position along pipe (m)")
        self.ax_vel.set_ylabel("Velocity (m/s)")
        self.ax_vel.set_title(f"Velocity Profiles at t = {sim.t:.2f} s")
        self.ax_vel.legend(fontsize=8)
        self.ax_vel.grid(True, alpha=0.3)
        self.fig_vel.tight_layout()
        self.canvas_vel.draw()

    def _on_simulation_done(self):
        """Called when simulation finishes."""
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.progress_var.set(100)

        if self.sim:
            self.status_var.set(
                f"Completed: t = {self.sim.t:.3f} s, {self.sim.step_count} steps"
            )
            self._update_plots()
            self._update_statistics()
            self._update_pressure()

    def _update_statistics(self):
        """Update the slug statistics tab."""
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

        # Input summary
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
        lines.append("")

        # Simulation summary
        lines.append("SIMULATION SUMMARY:")
        lines.append(f"  Final time:        {sim.t:.3f} s")
        lines.append(f"  Total steps:       {sim.step_count}")
        lines.append(f"  Final dt:          {sim.dt:.2e} s")
        lines.append("")

        # Slug statistics
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

        # Mixture velocity for reference
        U_m = p.U_sL + p.U_sG
        lines.append("REFERENCE VALUES:")
        lines.append(f"  Mixture velocity U_m = U_sL + U_sG = {U_m:.2f} m/s")
        lines.append(f"  Input liquid fraction = U_sL/U_m = {p.U_sL / U_m:.4f}")
        lines.append("")
        lines.append("=" * 60)

        self.stats_text.insert("1.0", "\n".join(lines))
        self.stats_text.config(state="disabled")

    def _update_pressure(self):
        """Estimate and plot pressure profile from gas momentum balance."""
        sim = self.sim
        if sim is None:
            return

        x = sim.mesh["x_cell"]
        dx = sim.mesh["dx"]
        beta = sim.mesh["beta"]
        N = len(x)

        # Estimate pressure gradient from gas momentum source terms:
        # dp/dx ~ -rho_G * g * sin(beta) - (tau_wG * S_G + tau_i * S_i) / (alpha_G * A)
        from slug_capturing_equations import compute_all_geometry, compute_all_shear

        geom = compute_all_geometry(sim.alpha_L, sim.params.D)
        shear = compute_all_shear(
            sim.u_L, sim.u_G,
            sim.params.rho_L, sim.params.rho_G,
            sim.params.mu_L, sim.params.mu_G,
            geom["D_hL"], geom["D_hG"]
        )

        A_pipe = np.pi * sim.params.D ** 2 / 4.0
        alpha_G = np.maximum(1.0 - sim.alpha_L, 1e-6)

        dp_dx = (
            -sim.params.rho_G * 9.81 * np.sin(beta)
            - (shear["tau_wG"] * geom["S_G"] + shear["tau_i"] * geom["S_i"])
            / (alpha_G * A_pipe)
        )

        # Integrate from outlet (p=0) backwards
        p = np.zeros(N)
        for i in range(N - 2, -1, -1):
            p[i] = p[i + 1] - dp_dx[i] * dx[i]

        self.ax_pres.clear()
        self.ax_pres.plot(x, p / 1000.0, "g-", linewidth=0.8)
        self.ax_pres.set_xlabel("Position along pipe (m)")
        self.ax_pres.set_ylabel("Gauge Pressure (kPa)")
        self.ax_pres.set_title(f"Estimated Pressure Profile at t = {sim.t:.2f} s")
        self.ax_pres.grid(True, alpha=0.3)
        self.fig_pres.tight_layout()
        self.canvas_pres.draw()


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    root = tk.Tk()
    app = SlugCapturingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
