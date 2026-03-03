"""
Simulation Orchestrator for 1D Slug Capturing Two-Fluid Model
==============================================================

This module sits between the equations (slug_capturing_equations.py) and the
GUI (slug_capturing_gui.py). It manages:
    - Simulation parameter validation
    - Running the time-stepping loop in a background thread
    - Collecting results at probe locations for plotting
    - Detecting slug events (where alpha_L approaches 1.0)
    - Computing slug statistics (frequency, length, translational velocity)
    - Storing periodic field snapshots for post-run time-history scrubbing

Reference:
    Issa & Kempf (2003), Int. J. Multiphase Flow, 29, 69-95.
"""

import threading
import time
import numpy as np

from slug_capturing_equations import (
    build_mesh,
    equilibrium_holdup,
    compute_max_dt,
    time_step,
    GRAVITY,
)


class SimulationParameters:
    """
    Container for all simulation input parameters.
    Validated on creation.
    """

    def __init__(
        self,
        segments,          # list of (length_m, angle_deg) tuples
        D,                 # pipe diameter (m)
        rho_L, rho_G,      # densities (kg/m3)
        mu_L, mu_G,        # viscosities (Pa.s)
        U_sL, U_sG,        # superficial velocities (m/s)
        N_cells=500,       # total number of grid cells
        CFL=0.45,          # CFL number
        t_end=30.0,        # simulation end time (s)
        convergence_tol=1e-6,  # steady-state convergence tolerance
    ):
        self.segments = segments
        self.D = D
        self.rho_L = rho_L
        self.rho_G = rho_G
        self.mu_L = mu_L
        self.mu_G = mu_G
        self.U_sL = U_sL
        self.U_sG = U_sG
        self.N_cells = N_cells
        self.CFL = CFL
        self.t_end = t_end
        self.convergence_tol = convergence_tol
        self._validate()

    def _validate(self):
        errors = []
        if not self.segments or len(self.segments) == 0:
            errors.append("At least one pipeline segment is required.")
        for i, (length, angle) in enumerate(self.segments):
            if length <= 0:
                errors.append(f"Segment {i + 1}: length must be positive.")
            if angle < -90 or angle > 90:
                errors.append(f"Segment {i + 1}: angle must be between -90 and +90 degrees.")
        if self.D <= 0:
            errors.append("Pipe diameter must be positive.")
        if self.rho_L <= 0 or self.rho_G <= 0:
            errors.append("Densities must be positive.")
        if self.mu_L <= 0 or self.mu_G <= 0:
            errors.append("Viscosities must be positive.")
        if self.U_sL <= 0 or self.U_sG <= 0:
            errors.append("Superficial velocities must be positive.")
        if self.N_cells < 10:
            errors.append("Number of cells must be at least 10.")
        if self.CFL <= 0 or self.CFL >= 1:
            errors.append("CFL number must be between 0 and 1.")
        if self.t_end <= 0:
            errors.append("Simulation time must be positive.")
        if errors:
            raise ValueError("\n".join(errors))


class ProbeData:
    """Stores time-series data at fixed probe locations along the pipe."""

    def __init__(self, probe_positions, x_cell):
        """
        Parameters
        ----------
        probe_positions : list of float
            Fractional positions along pipe (e.g. [0.25, 0.50, 0.75])
        x_cell : ndarray
            Cell centre positions
        """
        self.positions = probe_positions
        L = x_cell[-1]
        self.indices = [
            int(np.argmin(np.abs(x_cell - frac * L)))
            for frac in probe_positions
        ]
        self.labels = [f"{int(frac * 100)}% ({x_cell[idx]:.1f} m)"
                       for frac, idx in zip(probe_positions, self.indices)]
        self.time = []
        self.alpha_L = [[] for _ in probe_positions]
        self.u_L = [[] for _ in probe_positions]
        self.u_G = [[] for _ in probe_positions]

    def record(self, t, alpha_L, u_L, u_G):
        self.time.append(t)
        for k, idx in enumerate(self.indices):
            self.alpha_L[k].append(alpha_L[idx])
            self.u_L[k].append(u_L[idx])
            self.u_G[k].append(u_G[idx])


class SlugDetector:
    """
    Detects slug events from the holdup profile and computes statistics.

    A slug is defined as a contiguous region where alpha_L > slug_threshold.
    """

    SLUG_THRESHOLD = 0.85  # holdup above this is considered a slug

    def __init__(self, x_cell):
        self.x_cell = x_cell
        self.slug_events = []  # list of (time, front_position, back_position)

    def detect(self, t, alpha_L):
        """Scan current profile for slugs and record events."""
        in_slug = alpha_L > self.SLUG_THRESHOLD
        slugs = []
        start = None
        for i in range(len(alpha_L)):
            if in_slug[i] and start is None:
                start = i
            elif not in_slug[i] and start is not None:
                slugs.append((start, i - 1))
                start = None
        if start is not None:
            slugs.append((start, len(alpha_L) - 1))

        for (s, e) in slugs:
            x_front = self.x_cell[e]
            x_back = self.x_cell[s]
            length = x_front - x_back
            if length > 0:
                self.slug_events.append({
                    "time": t,
                    "front": x_front,
                    "back": x_back,
                    "length": length,
                })

    def compute_statistics(self):
        """
        Compute slug statistics from recorded events.

        Returns
        -------
        dict with: n_slugs, mean_length, mean_frequency, mean_velocity
              or None if not enough data
        """
        if len(self.slug_events) < 2:
            return None

        lengths = [e["length"] for e in self.slug_events]
        times = [e["time"] for e in self.slug_events]

        # Estimate frequency from number of slugs passing the midpoint
        L = self.x_cell[-1]
        mid_x = L / 2.0
        mid_pass_times = []
        for e in self.slug_events:
            if e["back"] <= mid_x <= e["front"]:
                mid_pass_times.append(e["time"])

        # Remove duplicates within 0.5s window
        unique_times = []
        for t in mid_pass_times:
            if not unique_times or t - unique_times[-1] > 0.5:
                unique_times.append(t)

        freq = 0.0
        if len(unique_times) >= 2:
            dt_total = unique_times[-1] - unique_times[0]
            if dt_total > 0:
                freq = (len(unique_times) - 1) / dt_total

        # Estimate translational velocity from front movement
        velocities = []
        prev_front = None
        prev_time = None
        for e in self.slug_events:
            if prev_front is not None:
                dt = e["time"] - prev_time
                if dt > 0.01:
                    v = (e["front"] - prev_front) / dt
                    if 0 < v < 50:  # reasonable range
                        velocities.append(v)
            prev_front = e["front"]
            prev_time = e["time"]

        return {
            "n_slug_events": len(self.slug_events),
            "mean_length_m": np.mean(lengths) if lengths else 0,
            "slug_frequency_hz": freq,
            "mean_velocity_m_s": np.mean(velocities) if velocities else 0,
        }


class SlugCapturingSimulation:
    """
    Main simulation class. Runs the 1D two-fluid model time-marching loop.
    """

    def __init__(self, params: SimulationParameters,
                 probe_positions=None, max_snapshots=500):
        self.params = params
        self.mesh = build_mesh(params.segments, params.N_cells)

        probe_pos = probe_positions if probe_positions is not None else [0.25, 0.50, 0.75]
        self.probes = ProbeData(probe_pos, self.mesh["x_cell"])
        self.slug_detector = SlugDetector(self.mesh["x_cell"])

        # Solution fields (initialized later)
        self.alpha_L = None
        self.u_L = None
        self.u_G = None
        self.t = 0.0
        self.dt = 0.0
        self.step_count = 0

        # Residual tracking for convergence monitoring
        self.residual_alpha = 0.0   # max |Δα_L| / Δt  (current step)
        self.residual_uL = 0.0     # max |Δu_L| / Δt
        self.residual_uG = 0.0     # max |Δu_G| / Δt
        self.residual_history = {   # time-series for plotting
            "time": [],
            "step": [],
            "alpha": [],
            "u_L": [],
            "u_G": [],
        }
        self.converged = False      # True if steady-state reached

        # Snapshot storage for post-run time-history scrubbing
        self.snapshots = []
        self._max_snapshots = max_snapshots

        # Threading control
        self._running = False
        self._stop_flag = threading.Event()
        self._thread = None

        # Callbacks
        self._on_step = None    # called every N steps with (sim,)
        self._on_done = None    # called when simulation finishes

    def _record_snapshot(self):
        """Store a copy of the current fields for time-history playback."""
        self.snapshots.append({
            "t": self.t,
            "step": self.step_count,
            "alpha_L": self.alpha_L.copy(),
            "u_L": self.u_L.copy(),
            "u_G": self.u_G.copy(),
        })
        # Thin by decimation when exceeding budget
        if len(self.snapshots) > self._max_snapshots:
            self.snapshots = self.snapshots[::2]

    def initialize(self):
        """
        Set initial conditions: uniform stratified flow with small
        perturbation to trigger instabilities (per paper Section 4).
        """
        N = self.mesh["N"]
        x = self.mesh["x_cell"]
        beta = self.mesh["beta"]
        p = self.params

        # Compute equilibrium holdup at the first segment's inclination
        alpha_eq = equilibrium_holdup(
            p.U_sL, p.U_sG, p.D,
            p.rho_L, p.rho_G, p.mu_L, p.mu_G,
            beta[0]
        )

        # Initialize with equilibrium + small sinusoidal perturbation
        # (Issa & Kempf, Section 4: perturbation triggers instabilities)
        L_total = self.mesh["L_total"]
        perturbation = 0.01 * alpha_eq * np.sin(2.0 * np.pi * x / L_total * 4.0)
        self.alpha_L = np.clip(alpha_eq + perturbation, 1e-6, 1.0 - 1e-6)

        # Velocities from superficial velocities
        self.u_L = p.U_sL / self.alpha_L
        self.u_G = p.U_sG / (1.0 - self.alpha_L)

        self.t = 0.0
        self.step_count = 0

        # Record initial snapshot (t=0)
        self.snapshots.clear()
        self._record_snapshot()

    def run(self, on_step=None, on_done=None, update_interval=20):
        """
        Run the simulation in a background thread.

        Parameters
        ----------
        on_step : callable(sim) or None
            Called every `update_interval` steps for GUI updates.
        on_done : callable(sim) or None
            Called when simulation finishes or is stopped.
        update_interval : int
            Number of time steps between GUI update callbacks.
        """
        self._on_step = on_step
        self._on_done = on_done
        self._stop_flag.clear()
        self._running = True

        def _run_loop():
            p = self.params
            m = self.mesh
            conv_tol = p.convergence_tol
            # Number of consecutive steps below tolerance before declaring converged
            CONV_WINDOW = 100

            conv_count = 0  # consecutive steps below tolerance

            while self.t < p.t_end and not self._stop_flag.is_set():
                # Adaptive time step (pass alpha_L to ignore slug body cells)
                self.dt = compute_max_dt(
                    self.u_L, self.u_G, m["dx"], p.CFL, self.alpha_L
                )
                # Don't overshoot end time
                self.dt = min(self.dt, p.t_end - self.t)

                # Save previous fields for residual calculation
                alpha_old = self.alpha_L.copy()
                uL_old = self.u_L.copy()
                uG_old = self.u_G.copy()

                # Advance one step
                self.alpha_L, self.u_L, self.u_G = time_step(
                    self.alpha_L, self.u_L, self.u_G,
                    self.dt, m["dx"], m["beta"], p.D,
                    p.rho_L, p.rho_G, p.mu_L, p.mu_G,
                    p.U_sL, p.U_sG,
                )

                self.t += self.dt
                self.step_count += 1

                # Compute residuals (max absolute change rate per step)
                if self.dt > 0:
                    self.residual_alpha = float(np.max(np.abs(self.alpha_L - alpha_old)) / self.dt)
                    self.residual_uL = float(np.max(np.abs(self.u_L - uL_old)) / self.dt)
                    self.residual_uG = float(np.max(np.abs(self.u_G - uG_old)) / self.dt)

                # Record residual history periodically (every 5 steps)
                if self.step_count % 5 == 0:
                    self.residual_history["time"].append(self.t)
                    self.residual_history["step"].append(self.step_count)
                    self.residual_history["alpha"].append(self.residual_alpha)
                    self.residual_history["u_L"].append(self.residual_uL)
                    self.residual_history["u_G"].append(self.residual_uG)

                # Check convergence: all residuals below tolerance
                max_res = max(self.residual_alpha, self.residual_uL, self.residual_uG)
                if conv_tol > 0 and max_res < conv_tol:
                    conv_count += 1
                    if conv_count >= CONV_WINDOW:
                        self.converged = True
                        break
                else:
                    conv_count = 0

                # Record probe data periodically
                if self.step_count % 5 == 0:
                    self.probes.record(self.t, self.alpha_L, self.u_L, self.u_G)

                # Detect slugs and record snapshots periodically
                if self.step_count % 10 == 0:
                    self.slug_detector.detect(self.t, self.alpha_L)
                    self._record_snapshot()

                # GUI update callback
                if self._on_step and self.step_count % update_interval == 0:
                    self._on_step(self)

            # Record final snapshot so last state is always available
            self._record_snapshot()

            self._running = False
            if self._on_done:
                self._on_done(self)

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the simulation to stop."""
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._running = False

    @property
    def is_running(self):
        return self._running

    @property
    def progress(self):
        """Simulation progress as fraction 0-1."""
        if self.params.t_end <= 0:
            return 1.0
        return min(self.t / self.params.t_end, 1.0)

    def get_slug_statistics(self):
        """Return slug statistics dict or None."""
        return self.slug_detector.compute_statistics()
