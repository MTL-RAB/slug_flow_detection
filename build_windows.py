#!/usr/bin/env python3
"""
Build script for Windows executables
======================================

Creates two single-file .exe installers using PyInstaller:

    dist/SlugFlowSimulator.exe   — Main application (distribute to all users)
    dist/LicenseGenerator.exe    — Admin-only tool (keep with private key)

Prerequisites:
    pip install -r requirements.txt

Usage:
    python build_windows.py              # build both
    python build_windows.py --main       # main app only
    python build_windows.py --generator  # license generator only
    python build_windows.py --genkeys    # generate RSA keypair only

The script auto-generates an RSA keypair in keys/ if one doesn't exist.
The public key is embedded inside SlugFlowSimulator.exe.
The private key is NOT embedded — keep it separate and secure.
"""

import os
import sys
import shutil
import subprocess
import datetime
import argparse

KEYS_DIR = os.path.join(os.path.dirname(__file__), "keys")
PRIVATE_KEY = os.path.join(KEYS_DIR, "private_key.pem")
PUBLIC_KEY = os.path.join(KEYS_DIR, "public_key.pem")
VERSION_FILE = os.path.join(os.path.dirname(__file__), "version.py")


def ensure_keys():
    """Generate RSA keypair if it doesn't exist."""
    if os.path.isfile(PRIVATE_KEY) and os.path.isfile(PUBLIC_KEY):
        print(f"[keys] Using existing keypair in {KEYS_DIR}/")
        return

    print(f"[keys] Generating new RSA keypair in {KEYS_DIR}/")
    # Import here so the rest of the script can show help without cryptography
    from license_manager import generate_keypair
    generate_keypair(PRIVATE_KEY, PUBLIC_KEY)
    print(f"[keys] Private key: {PRIVATE_KEY}")
    print(f"[keys] Public key:  {PUBLIC_KEY}")
    print(f"[keys] IMPORTANT: Keep private_key.pem secure!")


def stamp_build_date():
    """Update __build_date__ in version.py to today."""
    today = datetime.date.today().isoformat()
    lines = []
    with open(VERSION_FILE, "r") as f:
        for line in f:
            if line.startswith("__build_date__"):
                lines.append(f'__build_date__ = "{today}"\n')
            else:
                lines.append(line)
    with open(VERSION_FILE, "w") as f:
        f.writelines(lines)
    print(f"[version] Build date stamped: {today}")


def read_version():
    """Read current version from version.py."""
    ns = {}
    with open(VERSION_FILE) as f:
        exec(f.read(), ns)
    return ns.get("__version__", "0.0.0")


def build_main_app():
    """Build SlugFlowSimulator.exe with public key embedded."""
    if not os.path.isfile(PUBLIC_KEY):
        print("[ERROR] public_key.pem not found. Run with --genkeys first.")
        sys.exit(1)

    version = read_version()
    name = f"SlugFlowSimulator"

    print(f"\n[build] Building {name}.exe (v{version})...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        f"--name={name}",
        f"--add-data={PUBLIC_KEY}{os.pathsep}.",
        # Include all source modules
        "--hidden-import=slug_capturing_equations",
        "--hidden-import=slug_capturing_solver",
        "--hidden-import=license_manager",
        "--hidden-import=version",
        "--clean",
        "--noconfirm",
        "slug_capturing_gui.py",
    ]

    print(f"[build] Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=os.path.dirname(__file__) or ".")
    if result.returncode != 0:
        print(f"[ERROR] PyInstaller failed with exit code {result.returncode}")
        sys.exit(1)

    exe_path = os.path.join("dist", f"{name}.exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[build] Created: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"[build] Created: dist/{name} (see dist/ folder)")


def build_license_generator():
    """Build LicenseGenerator.exe (no private key embedded)."""
    version = read_version()
    name = "LicenseGenerator"

    print(f"\n[build] Building {name}.exe (v{version})...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        f"--name={name}",
        "--hidden-import=license_manager",
        "--hidden-import=version",
        "--clean",
        "--noconfirm",
        "license_generator_gui.py",
    ]

    print(f"[build] Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=os.path.dirname(__file__) or ".")
    if result.returncode != 0:
        print(f"[ERROR] PyInstaller failed with exit code {result.returncode}")
        sys.exit(1)

    exe_path = os.path.join("dist", f"{name}.exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[build] Created: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"[build] Created: dist/{name} (see dist/ folder)")


def main():
    parser = argparse.ArgumentParser(description="Build Slug Flow Simulator Windows executables")
    parser.add_argument("--main", action="store_true", help="Build main app only")
    parser.add_argument("--generator", action="store_true", help="Build license generator only")
    parser.add_argument("--genkeys", action="store_true", help="Generate RSA keypair only")
    args = parser.parse_args()

    print("=" * 60)
    print("  Slug Flow Simulator — Windows Build")
    print("=" * 60)

    if args.genkeys:
        ensure_keys()
        return

    build_main = args.main or (not args.main and not args.generator)
    build_gen = args.generator or (not args.main and not args.generator)

    # Step 1: Ensure RSA keys exist
    ensure_keys()

    # Step 2: Stamp build date
    stamp_build_date()

    # Step 3: Build executables
    if build_main:
        build_main_app()
    if build_gen:
        build_license_generator()

    # Summary
    print("\n" + "=" * 60)
    print("  BUILD COMPLETE")
    print("=" * 60)
    print()
    print("Distribution files:")
    if build_main:
        print("  dist/SlugFlowSimulator.exe  — Give to all users")
    if build_gen:
        print("  dist/LicenseGenerator.exe   — Admin only")
    print(f"  keys/private_key.pem        — KEEP SECURE (admin only)")
    print()
    print("Workflow:")
    print("  1. Run LicenseGenerator.exe to create .lic files")
    print("  2. Rename output to 'license.lic'")
    print("  3. User places license.lic next to SlugFlowSimulator.exe")
    print("  4. User runs SlugFlowSimulator.exe")


if __name__ == "__main__":
    main()
