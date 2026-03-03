# Verification Cases

Benchmark save files for reproducing the simulation conditions from:

> Issa, R.I. & Kempf, M.H.W. (2003). "Simulation of slug flow in horizontal
> and nearly horizontal pipes with the two-fluid model."
> *International Journal of Multiphase Flow*, 29(1), 69-95.

Experimental validation data from:

> Manolis, I.G. (1995). "High pressure gas-liquid slug flow."
> Ph.D. Thesis, Imperial College London.

## Test Facility

All cases use the Imperial College WASP facility geometry:

| Parameter         | Value                |
|-------------------|----------------------|
| Pipe diameter     | 0.078 m (78 mm)      |
| Working fluids    | Air-water (atmospheric) |
| Water density     | 998.0 kg/m³          |
| Water viscosity   | 0.001 Pa·s (1 cP)   |
| Air density       | 1.2 kg/m³            |
| Air viscosity     | 1.8 x 10⁻⁵ Pa·s     |

## Grid Resolution

The paper used 1250 cells giving Δx/D ≈ 0.37. These save files use the same
resolution for faithful reproduction. Note: higher cell counts will increase
simulation time proportionally.

## Cases

### Case 1 — Horizontal Pipe (Primary Validation)

**File:** `case1_horizontal_primary.scproj`

The principal test case from Issa & Kempf, matching the boundary conditions
used for the primary slug flow validation.

- U_sL = 1.0 m/s, U_sG = 2.0 m/s
- 36 m horizontal pipe, 1250 cells
- CFL = 0.5, t_end = 60 s

**Expected behaviour:** Slug flow develops from initial stratified equilibrium.
Small perturbations grow into full slugs within ~10-15 s. Slug frequency
stabilises by ~30 s.

### Case 2 — Horizontal Pipe (Higher Gas Velocity)

**File:** `case2_horizontal_high_gas.scproj`

Higher gas velocity case with lower liquid loading.

- U_sL = 0.55 m/s, U_sG = 3.0 m/s
- 36 m horizontal pipe, 1250 cells
- CFL = 0.5, t_end = 60 s

**Expected behaviour:** Less frequent but longer slugs. The higher gas velocity
produces a lower equilibrium holdup and longer development length before
slug initiation.

### Case 3 — Horizontal Pipe (High Gas, Low Liquid)

**File:** `case3_horizontal_transition.scproj`

Near the stratified-slug transition boundary on the Taitel & Dukler flow
pattern map.

- U_sL = 0.4 m/s, U_sG = 6.0 m/s
- 36 m horizontal pipe, 1250 cells
- CFL = 0.5, t_end = 80 s

**Expected behaviour:** Flow is close to the transition boundary. Slugs may
form intermittently or remain as large-amplitude waves. Longer simulation
time is needed to observe the slugging behaviour developing.

### Case 4 — V-Section (Terrain-Induced Slugging)

**File:** `case4_v_section.scproj`

V-shaped pipe with downhill and uphill sections, demonstrating the interaction
between terrain-induced and hydrodynamic slugging as reported in the paper.

- U_sL = 1.0 m/s, U_sG = 2.0 m/s
- Segment 1: 14 m at -1.5° (downhill)
- Segment 2: 23 m at +1.5° (uphill)
- 1250 cells, CFL = 0.5, t_end = 80 s

**Expected behaviour:** Liquid accumulates at the V-bottom (pipe low point)
before being pushed uphill as terrain-induced slugs. These slugs tend to
be significantly longer and more energetic than in the purely horizontal case.

## How to Use

1. Open Slug Flow Simulator
2. File > Open... > select any `.scproj` file from this folder
3. Click **Run Simulation**
4. Use the playback slider after completion to review slug development

## References

- Issa, R.I. & Kempf, M.H.W. (2003). Int. J. Multiphase Flow, 29(1), 69-95.
- Manolis, I.G. (1995). Ph.D. Thesis, Imperial College London.
- Bonizzi, M. & Issa, R.I. (2003). Int. J. Multiphase Flow, 29(11), 1719-1747.
- Taitel, Y. & Dukler, A.E. (1976). AIChE J., 22(1), 47-55.
