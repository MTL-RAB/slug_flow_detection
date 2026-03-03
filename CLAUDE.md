# CLAUDE.md — Project Instructions for Claude Code

## Project Overview

**Slug Flow Simulator** — a 1D two-fluid slug capturing model for multiphase pipeline flow, based on Issa & Kempf (2003). Desktop GUI built with tkinter + matplotlib.

## Architecture

```
slug_capturing_gui.py        → Main GUI (tkinter), entry point
  └── slug_capturing_solver.py  → Simulation orchestrator, threading, probe data
        └── slug_capturing_equations.py  → Pure physics: geometry, friction, FV discretisation
version.py                   → Centralised version (__version__, __build_date__)
license_manager.py           → RSA-signed license creation + validation
license_generator_gui.py     → Admin-only GUI for generating .lic files
build_windows.py             → PyInstaller build script (creates .exe files)
```

## Key Conventions

- **Entry point**: `python slug_capturing_gui.py`
- **Version**: semantic versioning in `version.py` (`__version__ = "X.Y.Z"`)
- **Build date**: auto-stamped by `build_windows.py` at compile time
- **Project files**: JSON format with `.scproj` extension
- **License files**: signed JSON with `.lic` extension, validated with RSA public key
- **License check**: only enforced when running as compiled `.exe` (frozen mode); skipped in development

## Dependencies

- `numpy` — numerical computation
- `matplotlib` — plotting (embedded in tkinter via `FigureCanvasTkAgg`)
- `cryptography` — RSA license signing/verification
- `pyinstaller` — build only, not a runtime dependency
- `tkinter` — standard library (no pip install needed)

## Building

```bash
pip install -r requirements.txt
python build_windows.py           # builds both .exe files
python build_windows.py --main    # main app only
python build_windows.py --generator  # license generator only
```

Output goes to `dist/`. RSA keys go to `keys/` (gitignored).

## Testing

No formal test suite yet. To verify the license system:

```bash
python -c "
from license_manager import generate_keypair, load_private_key, load_public_key, create_license, validate_license
import tempfile, os
d = tempfile.mkdtemp()
pk, pub = generate_keypair(os.path.join(d,'priv.pem'), os.path.join(d,'pub.pem'))
lic = create_license(pk, licensee='Test', organization='Test', email='t@t.com')
print(validate_license(pub, lic, '1.0.0'))
"
```

## Files to Never Commit

- `keys/` — RSA private/public keypair
- `*.lic` — license files
- `dist/`, `build/`, `*.spec` — PyInstaller artifacts
- `*.exe` — compiled binaries

## Physics Model Notes

- 1D transient two-fluid model, 4 conservation equations (liquid/gas continuity + momentum)
- First-order upwind finite volume, explicit Euler time integration
- Adaptive CFL-based time stepping (default CFL = 0.45)
- Slug body treatment: when alpha_G < 0.02, gas momentum singular → u_G forced to 0
- Initial conditions: equilibrium holdup + small sinusoidal perturbation
