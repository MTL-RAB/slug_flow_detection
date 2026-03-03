"""
License Manager — RSA-signed floating licenses
================================================

Provides:
    - RSA keypair generation
    - License creation (signing with private key)
    - License validation (verification with public key)
    - License file I/O (.lic JSON format)

The private key is used ONLY by the License Generator (admin tool).
The public key is embedded in the main application at build time.
"""

import json
import sys
import os
import base64
import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from version import version_tuple

# ============================================================================
# KEY MANAGEMENT
# ============================================================================

def generate_keypair(private_path, public_path):
    """Generate a 2048-bit RSA keypair and save to PEM files."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    os.makedirs(os.path.dirname(private_path), exist_ok=True)
    os.makedirs(os.path.dirname(public_path), exist_ok=True)

    with open(private_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    public_key = private_key.public_key()
    with open(public_path, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    return private_key, public_key


def load_private_key(path):
    """Load RSA private key from PEM file."""
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def load_public_key(path):
    """Load RSA public key from PEM file."""
    with open(path, "rb") as f:
        return serialization.load_pem_public_key(f.read())


def get_public_key_path():
    """Locate the public key PEM file (frozen bundle or development)."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle — public_key.pem is in the temp extract dir
        return os.path.join(sys._MEIPASS, "public_key.pem")
    else:
        # Development — look in keys/ next to this script
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "keys", "public_key.pem")


def get_default_private_key_path():
    """Default location for the private key (used by license generator)."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "private_key.pem")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "keys", "private_key.pem")


# ============================================================================
# LICENSE CREATION (requires private key)
# ============================================================================

_SIGN_PADDING = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()),
    salt_length=padding.PSS.MAX_LENGTH,
)


def create_license(private_key, *, licensee, organization, email,
                   license_type="full", days=90, max_version="1.99.0"):
    """
    Create a signed license dictionary.

    Parameters
    ----------
    private_key : RSAPrivateKey
    licensee, organization, email : str
    license_type : str  ("full" or "trial")
    days : int  (validity period from today)
    max_version : str  (maximum app version this license supports)

    Returns
    -------
    dict — license data including base64 signature
    """
    today = datetime.date.today()
    payload = {
        "licensee": licensee,
        "organization": organization,
        "email": email,
        "license_type": license_type,
        "issued_date": today.isoformat(),
        "expiry_date": (today + datetime.timedelta(days=days)).isoformat(),
        "max_version": max_version,
    }

    # Sign the canonical (sorted-keys) JSON representation
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = private_key.sign(payload_bytes, _SIGN_PADDING, hashes.SHA256())
    payload["signature"] = base64.b64encode(signature).decode("ascii")

    return payload


# ============================================================================
# LICENSE VALIDATION (requires public key only)
# ============================================================================

def validate_license(public_key, license_data, current_version=None):
    """
    Validate a license dictionary.

    Parameters
    ----------
    public_key : RSAPublicKey
    license_data : dict
    current_version : str or None  (e.g. "1.0.0")

    Returns
    -------
    (is_valid, message) : (bool, str)
    """
    # 1. Check signature exists
    sig_b64 = license_data.get("signature")
    if not sig_b64:
        return False, "License file is missing a signature."

    # 2. Reconstruct payload and verify signature
    payload = {k: v for k, v in license_data.items() if k != "signature"}
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    try:
        signature = base64.b64decode(sig_b64)
        public_key.verify(signature, payload_bytes, _SIGN_PADDING, hashes.SHA256())
    except Exception:
        return False, "License signature is invalid. The file may have been tampered with."

    # 3. Check expiry date
    try:
        expiry = datetime.date.fromisoformat(license_data["expiry_date"])
    except (KeyError, ValueError):
        return False, "License file has no valid expiry date."

    if datetime.date.today() > expiry:
        days_ago = (datetime.date.today() - expiry).days
        return False, (
            f"License expired on {expiry.isoformat()} ({days_ago} days ago).\n"
            f"Please contact your administrator for a renewal."
        )

    # 4. Check version ceiling
    if current_version and "max_version" in license_data:
        try:
            if version_tuple(current_version) > version_tuple(license_data["max_version"]):
                return False, (
                    f"License is valid up to version {license_data['max_version']}, "
                    f"but this application is version {current_version}.\n"
                    f"Please contact your administrator for an upgraded license."
                )
        except (ValueError, TypeError):
            pass  # ignore malformed version strings

    # All checks passed
    days_left = (expiry - datetime.date.today()).days
    return True, (
        f"Licensed to {license_data.get('licensee', '?')} "
        f"({license_data.get('organization', '?')}). "
        f"Valid until {expiry.isoformat()} ({days_left} days remaining)."
    )


# ============================================================================
# LICENSE FILE I/O
# ============================================================================

LICENSE_EXTENSION = ".lic"


def save_license(license_data, path):
    """Save license dictionary to a .lic JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(license_data, f, indent=2, ensure_ascii=False)


def load_license(path):
    """Load license dictionary from a .lic JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_license_file():
    """
    Search standard locations for a license.lic file.

    Search order:
        1. Next to the executable (frozen) or script (development)
        2. Current working directory
    Returns path or None.
    """
    candidates = []

    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))
    else:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))

    candidates.append(os.getcwd())

    for directory in candidates:
        path = os.path.join(directory, "license.lic")
        if os.path.isfile(path):
            return path

    return None
