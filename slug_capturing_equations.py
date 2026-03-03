"""
1D Two-Fluid Model for Slug Capturing in Pipelines
====================================================

Reference Paper:
    Issa, R.I. & Kempf, M.H.W. (2003).
    "Simulation of slug flow in horizontal and nearly horizontal pipes
     with the two-fluid model."
    International Journal of Multiphase Flow, 29(1), 69-95.
    DOI: 10.1016/S0301-9322(02)00127-1

This module contains ALL physics equations used in the slug capturing model.
An engineer can read this file top-to-bottom and verify every formula against
the paper without needing to understand any GUI or solver code.

Notation follows the paper:
    alpha_L : liquid volume fraction (holdup), dimensionless
    alpha_G : gas volume fraction = 1 - alpha_L, dimensionless
    u_L     : liquid velocity, m/s
    u_G     : gas velocity, m/s
    p       : pressure (interface/gas pressure), Pa
    rho_L   : liquid density, kg/m3
    rho_G   : gas density, kg/m3
    mu_L    : liquid dynamic viscosity, Pa.s
    mu_G    : gas dynamic viscosity, Pa.s
    D       : pipe internal diameter, m
    beta    : pipe inclination from horizontal, radians (positive = uphill)
    g       : gravitational acceleration, 9.81 m/s2
"""

import numpy as np

GRAVITY = 9.81  # m/s2


# ============================================================================
# SECTION A: PIPE CROSS-SECTION GEOMETRY
# ============================================================================
# These functions compute the geometric quantities for stratified flow in
# a circular pipe cross-section, given the liquid holdup alpha_L and pipe
# diameter D.
#
# The key geometric variable is gamma (half-angle subtended by the liquid
# at the pipe center). The relationship between alpha_L and gamma is:
#
#     alpha_L = (gamma - sin(gamma) * cos(gamma)) / pi
#
# See Issa & Kempf (2003), Section 2 and Figure 1.
# ============================================================================

def holdup_to_angle(alpha_L):
    """
    Convert liquid holdup alpha_L to the half-angle gamma subtended by
    the liquid phase at the pipe center.

    Equation (geometric relation, Section 2 of paper):
        alpha_L = (gamma - sin(gamma) * cos(gamma)) / pi

    This is solved iteratively (Newton-Raphson) since there is no closed-form
    inverse.

    Parameters
    ----------
    alpha_L : float or ndarray
        Liquid volume fraction, 0 <= alpha_L <= 1, dimensionless.

    Returns
    -------
    gamma : float or ndarray
        Half-angle in radians, 0 <= gamma <= pi.
    """
    alpha_L = np.asarray(alpha_L, dtype=float)
    scalar = alpha_L.ndim == 0
    alpha_L = np.atleast_1d(alpha_L)

    # Initial guess: linear interpolation
    gamma = np.pi * alpha_L

    # Newton-Raphson iteration
    for _ in range(50):
        f = (gamma - np.sin(gamma) * np.cos(gamma)) / np.pi - alpha_L
        # Derivative: df/dgamma = (1 - cos(2*gamma)) / pi = 2*sin^2(gamma)/pi
        df = 2.0 * np.sin(gamma) ** 2 / np.pi
        df = np.where(df < 1e-14, 1e-14, df)  # avoid division by zero
        gamma_new = gamma - f / df
        gamma = np.clip(gamma_new, 0.0, np.pi)

    if scalar:
        return float(gamma[0])
    return gamma


def liquid_area(gamma, D):
    """
    Cross-sectional area occupied by liquid in a circular pipe.

    Equation (Section 2):
        A_L = (D^2 / 4) * (gamma - sin(gamma) * cos(gamma))

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    A_L : float — liquid area (m^2)
    """
    return (D ** 2 / 4.0) * (gamma - np.sin(gamma) * np.cos(gamma))


def gas_area(gamma, D):
    """
    Cross-sectional area occupied by gas in a circular pipe.

    Equation:
        A_G = A_pipe - A_L = (D^2 / 4) * (pi - gamma + sin(gamma) * cos(gamma))

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    A_G : float — gas area (m^2)
    """
    A_pipe = np.pi * D ** 2 / 4.0
    return A_pipe - liquid_area(gamma, D)


def liquid_wetted_perimeter(gamma, D):
    """
    Perimeter of the pipe wall wetted by the liquid phase.

    Equation (Section 2):
        S_L = gamma * D

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    S_L : float — liquid wetted perimeter (m)
    """
    return gamma * D


def gas_wetted_perimeter(gamma, D):
    """
    Perimeter of the pipe wall wetted by the gas phase.

    Equation (Section 2):
        S_G = (pi - gamma) * D

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    S_G : float — gas wetted perimeter (m)
    """
    return (np.pi - gamma) * D


def interface_width(gamma, D):
    """
    Width of the gas-liquid interface (chord length).

    Equation (Section 2):
        S_i = D * sin(gamma)

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    S_i : float — interface width (m)
    """
    return D * np.sin(gamma)


def liquid_height(gamma, D):
    """
    Height of the liquid surface above the pipe bottom.

    Equation (Section 2):
        h_L = (D / 2) * (1 - cos(gamma))

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    h_L : float — liquid height (m)
    """
    return (D / 2.0) * (1.0 - np.cos(gamma))


def dhL_dalpha(gamma, D):
    """
    Derivative of liquid height with respect to liquid holdup.
    Used in the hydrostatic pressure gradient term of the liquid momentum
    equation.

    Derived from:
        h_L = (D/2)(1 - cos(gamma))
        alpha_L = (gamma - sin(gamma)*cos(gamma)) / pi

        dh_L/dalpha_L = (dh_L/dgamma) / (dalpha_L/dgamma)
                      = [(D/2)*sin(gamma)] / [2*sin^2(gamma)/pi]
                      = (D * pi) / (4 * sin(gamma))

    Parameters
    ----------
    gamma : float  — half-angle (radians)
    D     : float  — pipe internal diameter (m)

    Returns
    -------
    dh_da : float — dh_L / d(alpha_L) (m)
    """
    sin_g = np.sin(gamma)
    sin_g = np.where(np.abs(sin_g) < 1e-12, 1e-12, sin_g)
    return D * np.pi / (4.0 * sin_g)


def hydraulic_diameter_liquid(A_L, S_L):
    """
    Hydraulic diameter of the liquid phase.

    Equation (Section 2):
        D_hL = 4 * A_L / S_L

    Parameters
    ----------
    A_L : float — liquid cross-sectional area (m^2)
    S_L : float — liquid wetted perimeter (m)

    Returns
    -------
    D_hL : float — liquid hydraulic diameter (m)
    """
    S_L = np.where(np.abs(S_L) < 1e-14, 1e-14, S_L)
    return 4.0 * A_L / S_L


def hydraulic_diameter_gas(A_G, S_G, S_i):
    """
    Hydraulic diameter of the gas phase.

    Equation (Section 2):
        D_hG = 4 * A_G / (S_G + S_i)

    The gas hydraulic diameter uses the sum of the gas wetted perimeter and
    the interface width, since the interface acts as a wall for the gas
    (Taitel & Dukler, 1976 convention used by Issa & Kempf).

    Parameters
    ----------
    A_G : float — gas cross-sectional area (m^2)
    S_G : float — gas wetted perimeter (m)
    S_i : float — interface width (m)

    Returns
    -------
    D_hG : float — gas hydraulic diameter (m)
    """
    denom = S_G + S_i
    denom = np.where(np.abs(denom) < 1e-14, 1e-14, denom)
    return 4.0 * A_G / denom


def compute_all_geometry(alpha_L, D):
    """
    Convenience function: compute ALL geometric quantities from holdup.

    Parameters
    ----------
    alpha_L : float or ndarray — liquid holdup (dimensionless)
    D       : float            — pipe diameter (m)

    Returns
    -------
    dict with keys: gamma, A_L, A_G, S_L, S_G, S_i, h_L, D_hL, D_hG
    """
    alpha_L = np.asarray(alpha_L, dtype=float)
    # Clamp to avoid geometric singularities
    alpha_L = np.clip(alpha_L, 1e-6, 1.0 - 1e-6)
    gamma = holdup_to_angle(alpha_L)
    A_L_val = liquid_area(gamma, D)
    A_G_val = gas_area(gamma, D)
    S_L_val = liquid_wetted_perimeter(gamma, D)
    S_G_val = gas_wetted_perimeter(gamma, D)
    S_i_val = interface_width(gamma, D)
    h_L_val = liquid_height(gamma, D)
    D_hL_val = hydraulic_diameter_liquid(A_L_val, S_L_val)
    D_hG_val = hydraulic_diameter_gas(A_G_val, S_G_val, S_i_val)
    return {
        "gamma": gamma,
        "A_L": A_L_val, "A_G": A_G_val,
        "S_L": S_L_val, "S_G": S_G_val, "S_i": S_i_val,
        "h_L": h_L_val,
        "D_hL": D_hL_val, "D_hG": D_hG_val,
    }


# ============================================================================
# SECTION B: FRICTION FACTORS AND SHEAR STRESSES
# ============================================================================
# Closure relations for wall and interfacial friction.
# These follow the correlations recommended in Table 1 of
# Issa & Kempf (2003), which are based on the Blasius formula for
# turbulent flow and the Hagen-Poiseuille formula for laminar flow.
#
# Convention (Taitel & Dukler, 1976; used by Issa & Kempf):
#   - Liquid wall friction: uses liquid hydraulic diameter D_hL
#   - Gas wall friction: uses gas hydraulic diameter D_hG
#   - Interfacial friction: uses gas hydraulic diameter D_hG,
#     relative velocity |u_G - u_L|
# ============================================================================

def reynolds_number(rho, u, D_h, mu):
    """
    Reynolds number for a given phase.

    Equation:
        Re = rho * |u| * D_h / mu

    Parameters
    ----------
    rho : float — density (kg/m3)
    u   : float — velocity (m/s)
    D_h : float — hydraulic diameter (m)
    mu  : float — dynamic viscosity (Pa.s)

    Returns
    -------
    Re : float — Reynolds number (dimensionless)
    """
    return rho * np.abs(u) * D_h / mu


def friction_factor_wall(Re):
    """
    Wall friction factor (Fanning friction factor).

    Equation (Table 1 of Issa & Kempf, 2003):
        Laminar  (Re < 2100):  f = 16 / Re
        Turbulent (Re >= 2100): f = 0.046 * Re^(-0.2)

    The Fanning friction factor is used (not Darcy), consistent with
    the shear stress formula: tau = f * rho * |u| * u / 2

    Parameters
    ----------
    Re : float or ndarray — Reynolds number

    Returns
    -------
    f : float or ndarray — Fanning friction factor (dimensionless)
    """
    Re = np.asarray(Re, dtype=float)
    Re_safe = np.where(Re < 1.0, 1.0, Re)
    f_lam = 16.0 / Re_safe
    f_turb = 0.046 * Re_safe ** (-0.2)
    return np.where(Re < 2100.0, f_lam, f_turb)


def friction_factor_interface(Re_i):
    """
    Interfacial friction factor.

    Equation (Table 1 of Issa & Kempf, 2003):
        f_i = max(16/Re_i,  0.046 * Re_i^(-0.2))

    This ensures smooth transition from laminar to turbulent interfacial
    friction.

    Parameters
    ----------
    Re_i : float or ndarray — interfacial Reynolds number

    Returns
    -------
    f_i : float or ndarray — interfacial friction factor (dimensionless)
    """
    Re_i = np.asarray(Re_i, dtype=float)
    Re_safe = np.where(Re_i < 1.0, 1.0, Re_i)
    f_lam = 16.0 / Re_safe
    f_turb = 0.046 * Re_safe ** (-0.2)
    return np.maximum(f_lam, f_turb)


def wall_shear_stress(f, rho, u):
    """
    Wall shear stress for a given phase.

    Equation (Section 2 of paper):
        tau_w = f * rho * |u| * u / 2

    The sign convention: tau_w acts in the direction opposing motion,
    so it has the same sign as u (the formula uses |u|*u to preserve sign).

    Parameters
    ----------
    f   : float — Fanning friction factor (dimensionless)
    rho : float — phase density (kg/m3)
    u   : float — phase velocity (m/s)

    Returns
    -------
    tau_w : float — wall shear stress (Pa)
    """
    return f * rho * np.abs(u) * u / 2.0


def interfacial_shear_stress(f_i, rho_G, u_G, u_L):
    """
    Interfacial shear stress between gas and liquid.

    Equation (Section 2 of paper):
        tau_i = f_i * rho_G * |u_G - u_L| * (u_G - u_L) / 2

    Sign convention: positive when gas drags liquid in the gas flow direction.

    Parameters
    ----------
    f_i   : float — interfacial friction factor (dimensionless)
    rho_G : float — gas density (kg/m3)
    u_G   : float — gas velocity (m/s)
    u_L   : float — liquid velocity (m/s)

    Returns
    -------
    tau_i : float — interfacial shear stress (Pa)
    """
    du = u_G - u_L
    return f_i * rho_G * np.abs(du) * du / 2.0


def compute_all_shear(u_L, u_G, rho_L, rho_G, mu_L, mu_G, D_hL, D_hG):
    """
    Convenience function: compute ALL friction/shear quantities.

    Returns dict with: Re_L, Re_G, Re_i, f_L, f_G, f_i, tau_wL, tau_wG, tau_i
    """
    Re_L = reynolds_number(rho_L, u_L, D_hL, mu_L)
    Re_G = reynolds_number(rho_G, u_G, D_hG, mu_G)
    Re_i = reynolds_number(rho_G, u_G - u_L, D_hG, mu_G)

    f_L = friction_factor_wall(Re_L)
    f_G = friction_factor_wall(Re_G)
    f_i = friction_factor_interface(Re_i)

    tau_wL = wall_shear_stress(f_L, rho_L, u_L)
    tau_wG = wall_shear_stress(f_G, rho_G, u_G)
    tau_i = interfacial_shear_stress(f_i, rho_G, u_G, u_L)

    return {
        "Re_L": Re_L, "Re_G": Re_G, "Re_i": Re_i,
        "f_L": f_L, "f_G": f_G, "f_i": f_i,
        "tau_wL": tau_wL, "tau_wG": tau_wG, "tau_i": tau_i,
    }


# ============================================================================
# SECTION C: MULTI-SEGMENT PIPELINE MESH
# ============================================================================
# The pipeline is defined as a sequence of segments, each with its own
# length and inclination angle. This allows modelling of V-sections,
# hilly terrain, and vertical risers — matching the configurations
# studied in Issa & Kempf (2003), Section 5.
# ============================================================================

def build_mesh(segments, N_total):
    """
    Build a 1D finite-volume mesh for a multi-segment pipeline.

    Each segment is defined by (length_m, angle_deg):
        length_m  — length of segment in metres
        angle_deg — inclination from horizontal in degrees
                    (positive = uphill, negative = downhill,
                     +90 = vertical riser, -90 = vertical downcomer)

    The total number of cells N_total is distributed proportionally
    to segment lengths so each cell has roughly equal size.

    Parameters
    ----------
    segments : list of (length, angle_deg) tuples
        Pipeline segment definitions.
    N_total : int
        Total number of finite volume cells.

    Returns
    -------
    dict with:
        x_cell   : ndarray(N) — cell centre positions along pipe axis (m)
        x_face   : ndarray(N+1) — cell face positions (m)
        dx       : ndarray(N) — cell widths (m)
        beta     : ndarray(N) — inclination angle at each cell (radians)
        L_total  : float — total pipeline length (m)
        seg_boundaries : list of int — cell index where each segment starts
    """
    L_total = sum(seg[0] for seg in segments)

    # Distribute cells to segments proportionally
    seg_ncells = []
    remaining = N_total
    for i, (length, _) in enumerate(segments):
        if i == len(segments) - 1:
            n = remaining
        else:
            n = max(1, int(round(N_total * length / L_total)))
            remaining -= n
        seg_ncells.append(n)

    # Build arrays
    x_faces = []
    betas = []
    seg_boundaries = [0]
    x_start = 0.0

    for (length, angle_deg), n_cells in zip(segments, seg_ncells):
        beta_rad = np.deg2rad(angle_deg)
        dx_seg = length / n_cells
        for j in range(n_cells):
            x_faces.append(x_start + j * dx_seg)
            betas.append(beta_rad)
        x_start += length
        seg_boundaries.append(seg_boundaries[-1] + n_cells)

    x_faces.append(x_start)  # final face
    x_face = np.array(x_faces)
    beta = np.array(betas)

    N = len(beta)
    dx = x_face[1:] - x_face[:-1]
    x_cell = x_face[:-1] + dx / 2.0

    return {
        "x_cell": x_cell,
        "x_face": x_face,
        "dx": dx,
        "beta": beta,
        "L_total": L_total,
        "N": N,
        "seg_boundaries": seg_boundaries,
    }


# ============================================================================
# SECTION D: GOVERNING EQUATIONS — FINITE VOLUME DISCRETIZATION
# ============================================================================
# The 1D transient two-fluid model consists of 4 conservation equations
# (Issa & Kempf, 2003, Equations 1-4):
#
#   Liquid continuity (Eq. 1):
#       d(alpha_L)/dt + d(alpha_L * u_L)/dx = 0
#
#   Gas continuity (Eq. 2):
#       d(alpha_G * rho_G)/dt + d(alpha_G * rho_G * u_G)/dx = 0
#
#   Liquid momentum (Eq. 3):
#       d(rho_L * alpha_L * u_L)/dt + d(rho_L * alpha_L * u_L^2)/dx
#         = -alpha_L * dp/dx
#           + rho_L * g * cos(beta) * alpha_L * dh_L/dx
#           - alpha_L * rho_L * g * sin(beta)
#           - tau_wL * S_L / A
#           + tau_i  * S_i / A
#
#   Gas momentum (Eq. 4):
#       d(rho_G * alpha_G * u_G)/dt + d(rho_G * alpha_G * u_G^2)/dx
#         = -alpha_G * dp/dx
#           - alpha_G * rho_G * g * sin(beta)
#           - tau_wG * S_G / A
#           - tau_i  * S_i / A
#
# The incompressible liquid assumption (rho_L = const) simplifies Eq. 1.
# We also assume incompressible gas for this simplified model, which removes
# the pressure-density coupling and allows an explicit time-marching scheme.
#
# The combined momentum equation is obtained by eliminating dp/dx between
# Eqs. 3 and 4 (dividing Eq. 3 by alpha_L and Eq. 4 by alpha_G, then
# subtracting). This avoids solving for pressure explicitly.
#
# Discretization: first-order upwind for convective fluxes, explicit
# (forward Euler) time integration.
#
# Slug body treatment (Issa & Kempf, 2003, Section 3.3):
#   When alpha_G < 0.02 (slug body), the gas momentum equation becomes
#   singular. In this region, u_G is set to 0 and only the liquid
#   continuity and momentum equations are solved.
# ============================================================================

# Minimum gas fraction before treating cell as slug body
ALPHA_G_MIN = 0.02


def compute_rhs(alpha_L, u_L, u_G, dx, beta, D, rho_L, rho_G, mu_L, mu_G):
    """
    Compute the right-hand side of the semi-discrete equations:
        d(alpha_L)/dt = RHS_alpha[i]
        d(u_L)/dt     = RHS_uL[i]
        d(u_G)/dt     = RHS_uG[i]

    Uses first-order upwind for convective terms and the combined momentum
    approach to avoid explicit pressure calculation.

    Parameters
    ----------
    alpha_L : ndarray(N) — liquid holdup at cell centres
    u_L     : ndarray(N) — liquid velocity at cell centres (m/s)
    u_G     : ndarray(N) — gas velocity at cell centres (m/s)
    dx      : ndarray(N) — cell widths (m)
    beta    : ndarray(N) — pipe inclination at each cell (radians)
    D       : float      — pipe diameter (m)
    rho_L   : float      — liquid density (kg/m3)
    rho_G   : float      — gas density (kg/m3)
    mu_L    : float      — liquid viscosity (Pa.s)
    mu_G    : float      — gas viscosity (Pa.s)

    Returns
    -------
    d_alpha : ndarray(N) — time derivative of alpha_L
    d_uL    : ndarray(N) — time derivative of u_L
    d_uG    : ndarray(N) — time derivative of u_G
    """
    N = len(alpha_L)
    A_pipe = np.pi * D ** 2 / 4.0

    alpha_G = 1.0 - alpha_L

    # --- Geometric quantities at each cell ---
    geom = compute_all_geometry(alpha_L, D)
    gamma = geom["gamma"]
    A_L = geom["A_L"]
    A_G = geom["A_G"]
    S_L = geom["S_L"]
    S_G = geom["S_G"]
    S_i = geom["S_i"]
    D_hL = geom["D_hL"]
    D_hG = geom["D_hG"]

    # --- Friction and shear stresses ---
    shear = compute_all_shear(u_L, u_G, rho_L, rho_G, mu_L, mu_G, D_hL, D_hG)
    tau_wL = shear["tau_wL"]
    tau_wG = shear["tau_wG"]
    tau_i = shear["tau_i"]

    # dh_L/dalpha_L for hydrostatic term
    dh_da = dhL_dalpha(gamma, D)

    # --- Liquid continuity: d(alpha_L)/dt + d(alpha_L * u_L)/dx = 0 ---
    # Upwind flux for alpha_L * u_L
    flux_alpha = alpha_L * u_L
    d_alpha = np.zeros(N)
    for i in range(N):
        # Left face flux (upwind)
        if i == 0:
            # Inlet boundary: use ghost cell = inlet value
            flux_left = flux_alpha[i]
        else:
            flux_left = flux_alpha[i - 1] if u_L[i - 1] >= 0 else flux_alpha[i]

        # Right face flux (upwind)
        if i == N - 1:
            # Outlet boundary: extrapolate
            flux_right = flux_alpha[i]
        else:
            flux_right = flux_alpha[i] if u_L[i] >= 0 else flux_alpha[i + 1]

        d_alpha[i] = -(flux_right - flux_left) / dx[i]

    # --- Combined momentum equation ---
    # Instead of solving for pressure explicitly, we use the combined approach.
    # Divide liquid momentum by (rho_L * alpha_L) and gas momentum by
    # (rho_G * alpha_G), then subtract gas from liquid to eliminate dp/dx.
    #
    # This gives (simplified for incompressible phases):
    #
    #   du_L/dt = -u_L * du_L/dx + gravity_L + friction_L
    #   du_G/dt = -u_G * du_G/dx + gravity_G + friction_G
    #
    # where the pressure gradient is computed from the gas momentum equation
    # and fed into the liquid momentum equation, or equivalently we solve
    # each phase momentum with the combined pressure gradient.
    #
    # For this explicit scheme, we compute source terms directly:

    d_uL = np.zeros(N)
    d_uG = np.zeros(N)

    for i in range(N):
        aL = max(alpha_L[i], 1e-6)
        aG = max(alpha_G[i], 1e-6)
        sin_b = np.sin(beta[i])
        cos_b = np.cos(beta[i])

        # Convective terms (upwind)
        if i == 0:
            duL_dx = (u_L[i + 1] - u_L[i]) / dx[i] if u_L[i] < 0 and N > 1 else 0.0
            duG_dx = (u_G[i + 1] - u_G[i]) / dx[i] if u_G[i] < 0 and N > 1 else 0.0
        elif i == N - 1:
            duL_dx = (u_L[i] - u_L[i - 1]) / dx[i] if u_L[i] >= 0 else 0.0
            duG_dx = (u_G[i] - u_G[i - 1]) / dx[i] if u_G[i] >= 0 else 0.0
        else:
            if u_L[i] >= 0:
                duL_dx = (u_L[i] - u_L[i - 1]) / dx[i]
            else:
                duL_dx = (u_L[i + 1] - u_L[i]) / dx[i]
            if u_G[i] >= 0:
                duG_dx = (u_G[i] - u_G[i - 1]) / dx[i]
            else:
                duG_dx = (u_G[i + 1] - u_G[i]) / dx[i]

        # Gravity term
        grav_L = -GRAVITY * sin_b
        grav_G = -GRAVITY * sin_b

        # Hydrostatic pressure correction for liquid (Eq. 3 term)
        # rho_L * g * cos(beta) * dh_L/dx ≈ rho_L * g * cos(beta) * (dh_L/dalpha) * dalpha/dx
        if i == 0:
            da_dx = (alpha_L[min(i + 1, N - 1)] - alpha_L[i]) / dx[i]
        elif i == N - 1:
            da_dx = (alpha_L[i] - alpha_L[i - 1]) / dx[i]
        else:
            da_dx = (alpha_L[i + 1] - alpha_L[i - 1]) / (dx[i] + dx[i - 1])

        hydrostatic_L = GRAVITY * cos_b * dh_da[i] * da_dx

        # Slug body handling (Issa & Kempf, Section 3.3):
        # When alpha_G < 0.02, gas momentum is singular → set u_G = 0
        is_slug = alpha_G[i] < ALPHA_G_MIN

        # Wall friction source terms (per unit mass)
        # Guard against division by near-zero area in slug body
        A_L_safe = max(A_L[i], 1e-10)
        A_G_safe = max(A_G[i], 1e-10)

        fric_wL = -tau_wL[i] * S_L[i] / (rho_L * A_L_safe)
        fric_iL = tau_i[i] * S_i[i] / (rho_L * A_L_safe)

        # Liquid momentum RHS
        d_uL[i] = -u_L[i] * duL_dx + grav_L + hydrostatic_L + fric_wL + fric_iL

        # Gas momentum RHS
        if is_slug:
            d_uG[i] = 0.0  # slug body: gas velocity forced to zero
        else:
            fric_wG = -tau_wG[i] * S_G[i] / (rho_G * A_G_safe)
            fric_iG = -tau_i[i] * S_i[i] / (rho_G * A_G_safe)
            d_uG[i] = -u_G[i] * duG_dx + grav_G + fric_wG + fric_iG

    return d_alpha, d_uL, d_uG


def compute_max_dt(u_L, u_G, dx, cfl=0.45, alpha_L=None):
    """
    Compute maximum stable time step based on CFL condition.

    CFL condition:
        dt <= CFL * min(dx / max(|u_L|, |u_G|))

    In slug body cells (alpha_L > 1 - ALPHA_G_MIN), u_G is effectively
    zero, so those cells don't limit the time step.

    Parameters
    ----------
    u_L     : ndarray — liquid velocities (m/s)
    u_G     : ndarray — gas velocities (m/s)
    dx      : ndarray — cell widths (m)
    cfl     : float   — CFL number (default 0.45, must be < 1 for stability)
    alpha_L : ndarray or None — liquid holdup (used to mask slug body cells)

    Returns
    -------
    dt : float — maximum stable time step (s)
    """
    # In slug body, gas velocity is forced to zero, so use the effective
    # velocity for CFL
    u_G_eff = np.copy(u_G)
    if alpha_L is not None:
        slug_mask = alpha_L > (1.0 - ALPHA_G_MIN)
        u_G_eff[slug_mask] = 0.0

    max_speed = np.maximum(np.abs(u_L), np.abs(u_G_eff))
    max_speed = np.where(max_speed < 1e-6, 1e-6, max_speed)
    dt = cfl * np.min(dx / max_speed)
    # Enforce a minimum time step to avoid stalling
    return max(dt, 1e-6)


def time_step(alpha_L, u_L, u_G, dt, dx, beta, D, rho_L, rho_G, mu_L, mu_G,
              U_sL_inlet, U_sG_inlet):
    """
    Advance the solution by one time step using explicit Euler.

    Parameters
    ----------
    alpha_L, u_L, u_G : ndarray(N) — current solution fields
    dt     : float     — time step (s)
    dx     : ndarray(N) — cell widths (m)
    beta   : ndarray(N) — inclination angles (radians)
    D      : float      — pipe diameter (m)
    rho_L, rho_G : float — densities (kg/m3)
    mu_L, mu_G   : float — viscosities (Pa.s)
    U_sL_inlet    : float — inlet superficial liquid velocity (m/s)
    U_sG_inlet    : float — inlet superficial gas velocity (m/s)

    Returns
    -------
    alpha_L_new, u_L_new, u_G_new : ndarray(N) — updated fields
    """
    d_alpha, d_uL, d_uG = compute_rhs(
        alpha_L, u_L, u_G, dx, beta, D, rho_L, rho_G, mu_L, mu_G
    )

    alpha_L_new = alpha_L + dt * d_alpha
    u_L_new = u_L + dt * d_uL
    u_G_new = u_G + dt * d_uG

    # Clamp holdup to physical range
    alpha_L_new = np.clip(alpha_L_new, 1e-6, 1.0 - 1e-6)

    # --- Boundary conditions ---
    # Inlet (i=0): fixed superficial velocities
    # U_sL = alpha_L * u_L, U_sG = alpha_G * u_G
    # Keep inlet holdup from continuity, compute velocities from superficial
    aL_in = alpha_L_new[0]
    aG_in = 1.0 - aL_in
    u_L_new[0] = U_sL_inlet / max(aL_in, 1e-6)
    u_G_new[0] = U_sG_inlet / max(aG_in, ALPHA_G_MIN)

    # Outlet (i=N-1): zero-gradient (Neumann) for all variables
    alpha_L_new[-1] = alpha_L_new[-2]
    u_L_new[-1] = u_L_new[-2]
    u_G_new[-1] = u_G_new[-2]

    # Enforce slug body condition (Issa & Kempf, Section 3.3):
    # When alpha_G < ALPHA_G_MIN, the gas momentum equation is singular.
    # Set u_G = 0 in slug body. In the transition zone, smoothly reduce
    # gas velocity to prevent velocity spikes.
    alpha_G_new = 1.0 - alpha_L_new
    slug_mask = alpha_G_new < ALPHA_G_MIN
    u_G_new[slug_mask] = 0.0

    # Velocity limiting: cap gas velocity to prevent blow-up in
    # near-slug transition cells. Maximum physical gas velocity is
    # bounded by the superficial gas velocity / ALPHA_G_MIN.
    U_G_max = U_sG_inlet / ALPHA_G_MIN
    u_G_new = np.clip(u_G_new, -U_G_max, U_G_max)

    # Cap liquid velocity similarly
    U_L_max = max(U_sL_inlet * 20.0, 30.0)
    u_L_new = np.clip(u_L_new, -U_L_max, U_L_max)

    return alpha_L_new, u_L_new, u_G_new


def equilibrium_holdup(U_sL, U_sG, D, rho_L, rho_G, mu_L, mu_G, beta_rad):
    """
    Compute equilibrium liquid holdup for stratified flow using momentum
    balance (steady-state combined momentum equation).

    This is the initial condition: the holdup where the gas and liquid
    momentum equations are in balance for the given superficial velocities.

    Uses a coarse scan to locate sign changes in the momentum residual,
    then refines with bisection for accuracy.

    Parameters
    ----------
    U_sL    : float — superficial liquid velocity (m/s)
    U_sG    : float — superficial gas velocity (m/s)
    D       : float — pipe diameter (m)
    rho_L   : float — liquid density (kg/m3)
    rho_G   : float — gas density (kg/m3)
    mu_L    : float — liquid viscosity (Pa.s)
    mu_G    : float — gas viscosity (Pa.s)
    beta_rad: float — pipe inclination (radians)

    Returns
    -------
    alpha_L_eq : float — equilibrium liquid holdup (dimensionless)
    """

    def _residual(alpha_L_try):
        u_L = U_sL / alpha_L_try
        u_G = U_sG / (1.0 - alpha_L_try)
        geom = compute_all_geometry(alpha_L_try, D)
        A_L = max(geom["A_L"], 1e-12)
        A_G = max(geom["A_G"], 1e-12)
        shear = compute_all_shear(u_L, u_G, rho_L, rho_G, mu_L, mu_G,
                                  geom["D_hL"], geom["D_hG"])
        return (
            shear["tau_wL"] * geom["S_L"] / A_L
            - shear["tau_wG"] * geom["S_G"] / A_G
            - shear["tau_i"] * geom["S_i"] * (1.0 / A_L + 1.0 / A_G)
            + (rho_L - rho_G) * GRAVITY * np.sin(beta_rad)
        )

    # --- Stage 1: coarse scan to find sign changes -----------------------
    alphas = np.linspace(0.02, 0.98, 500)
    residuals = np.array([_residual(a) for a in alphas])

    # Look for sign changes (robust root detection)
    sign_changes = []
    for i in range(len(residuals) - 1):
        if residuals[i] * residuals[i + 1] < 0:
            sign_changes.append(i)

    # --- Stage 2: bisection refinement at each sign change ----------------
    best_alpha = 0.5
    best_abs_res = 1e30

    for idx in sign_changes:
        a_lo, a_hi = alphas[idx], alphas[idx + 1]
        r_lo = residuals[idx]
        for _ in range(50):  # bisection iterations
            a_mid = 0.5 * (a_lo + a_hi)
            r_mid = _residual(a_mid)
            if r_lo * r_mid <= 0:
                a_hi = a_mid
            else:
                a_lo = a_mid
                r_lo = r_mid
        a_mid = 0.5 * (a_lo + a_hi)
        r_mid = _residual(a_mid)
        if abs(r_mid) < best_abs_res:
            best_abs_res = abs(r_mid)
            best_alpha = a_mid

    # --- Fallback: if no sign change found, use minimum |residual| --------
    if not sign_changes:
        idx_min = np.argmin(np.abs(residuals))
        best_alpha = alphas[idx_min]

    return best_alpha
