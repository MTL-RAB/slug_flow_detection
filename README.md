# Slug Flow Simulator

**1D two-fluid slug capturing model** for multiphase pipeline flow, based on Issa & Kempf (2003).

Interactive desktop GUI for engineers to design multi-segment pipelines, run transient simulations, and analyse slug flow behaviour.

## Features

- Multi-segment pipeline geometry with arbitrary inclinations (-90 to +90 deg)
- Transient two-fluid model with adaptive CFL-based time stepping
- Live simulation monitoring with progress tracking
- Time-history playback with slider scrubbing after simulation completes
- Multiple visualisation tabs: holdup, velocity, pressure profiles and probe time-series
- Slug event detection and frequency estimation
- Configurable probe locations along the pipe
- Project files (JSON `.scproj` format) with undo/redo support

## Quick Start (Development)

```bash
pip install numpy matplotlib cryptography
python slug_capturing_gui.py
```

In development mode the license check is skipped.

## Building Windows Executables

### Prerequisites

Install Python 3.9+ and the required packages:

```bash
pip install -r requirements.txt
```

### Build

```bash
python build_windows.py
```

This will:
1. Generate an RSA keypair in `keys/` (first build only)
2. Stamp the current date into `version.py`
3. Build **`dist/SlugFlowSimulator.exe`** — the main application
4. Build **`dist/LicenseGenerator.exe`** — the admin licensing tool

You can also build selectively:

```bash
python build_windows.py --main        # main app only
python build_windows.py --generator   # license generator only
python build_windows.py --genkeys     # generate RSA keypair only
```

### Build Output

| File | Description | Who gets it |
|------|-------------|-------------|
| `dist/SlugFlowSimulator.exe` | Main application | All users |
| `dist/LicenseGenerator.exe` | License generation tool | Admin only |
| `keys/private_key.pem` | RSA private key | Admin only (keep secure!) |
| `keys/public_key.pem` | RSA public key | Embedded in main app at build time |

## Licensing

The application uses RSA-signed floating licenses with a 90-day validity period.

### How It Works

- The **private key** stays with the administrator — it never ships in the main application
- The **public key** is embedded inside `SlugFlowSimulator.exe` at build time
- Even if someone decompiles the `.exe`, they cannot forge a license without the private key
- Each license is a signed JSON `.lic` file containing: licensee, organisation, expiry date, and version ceiling

### Generating a License

1. Run `LicenseGenerator.exe` (or `python license_generator_gui.py` in development)
2. Load the private key (`private_key.pem`) if not auto-detected
3. Fill in the licensee details:
   - **Licensee name** — the person or team
   - **Organisation** — company name
   - **Email** — contact email
   - **License type** — Full or Trial
   - **Validity** — number of days (default: 90)
   - **Max version** — highest app version this license supports (e.g. `1.99.0`)
4. Click **Generate License File...** and save the `.lic` file

### Installing a License

1. Rename the generated file to `license.lic`
2. Place it in the same folder as `SlugFlowSimulator.exe`
3. Launch the application — it will validate the license on startup

If no license is found, the application will prompt the user to browse for one.

### License Validation

On startup the application checks:
- **Signature** — the file has not been tampered with
- **Expiry date** — the license has not expired
- **Version ceiling** — the app version does not exceed `max_version`

If any check fails, a clear error message is shown and the application will not start.

## Versioning

Version information is centralised in `version.py`:

```python
__app_name__ = "Slug Flow Simulator"
__version__ = "1.0.0"
__build_date__ = "2026-03-03"
```

- **Semantic versioning** (`MAJOR.MINOR.PATCH`)
- `__build_date__` is automatically updated by `build_windows.py` at build time
- Version is shown in the title bar, Help > About dialog, and used for license validation
- To release a new version, update `__version__` in `version.py` before building

## Project Structure

```
slug_flow_detection/
├── slug_capturing_gui.py          # Main application GUI (tkinter)
├── slug_capturing_solver.py       # Simulation orchestrator and data structures
├── slug_capturing_equations.py    # Physics: geometry, friction, governing equations
├── version.py                     # Centralised version info
├── license_manager.py             # License creation, validation, RSA key management
├── license_generator_gui.py       # Admin tool: license generation GUI
├── build_windows.py               # PyInstaller build script
├── requirements.txt               # Python dependencies
├── .gitignore                     # Excludes keys, builds, license files
├── dataset/                       # Experimental reference data
├── best_models/                   # Pre-trained ML classifiers
├── ensemble_models/               # Ensemble ML models
└── images/                        # Output plots
```

## Distribution Checklist

When distributing a new release:

1. Update `__version__` in `version.py` (e.g. `1.0.0` → `1.1.0`)
2. Run `python build_windows.py` on a Windows machine
3. Distribute `dist/SlugFlowSimulator.exe` to users
4. Generate new `.lic` files if the version exceeds existing license ceilings
5. Keep `keys/private_key.pem` and `LicenseGenerator.exe` secure

## Physics Reference

Issa, R.I. & Kempf, M.H.W. (2003). "Simulation of slug flow in horizontal and nearly horizontal pipes with the two-fluid model." *International Journal of Multiphase Flow*, 29(1), 69-95.
