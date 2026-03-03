#!/usr/bin/env python3
"""
License Generator — Admin Tool
================================

Standalone tkinter GUI for generating signed license files (.lic)
for the Slug Flow Simulator.

This tool requires access to the RSA private key (private_key.pem).
Only the license administrator should have this tool and key.

Usage:
    python license_generator_gui.py

    The tool looks for private_key.pem next to itself (or in keys/).
    If not found, it offers to generate a new keypair.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import datetime

import license_manager
from version import __app_name__, __version__


class LicenseGeneratorApp:
    """Admin GUI for creating signed license files."""

    def __init__(self, root):
        self.root = root
        self.root.title(f"License Generator — {__app_name__} v{__version__}")
        self.root.geometry("520x560")
        self.root.resizable(False, False)

        self._private_key = None
        self._key_path = None

        self._build_gui()
        self._try_load_default_key()

    def _build_gui(self):
        # ---- Key status ----
        key_frame = ttk.LabelFrame(self.root, text="Private Key", padding=8)
        key_frame.pack(fill="x", padx=12, pady=(12, 6))

        self.key_status = tk.StringVar(value="No private key loaded")
        ttk.Label(key_frame, textvariable=self.key_status,
                  font=("Arial", 9)).pack(anchor="w")

        btn_row = ttk.Frame(key_frame)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="Load Key...", command=self._load_key).pack(side="left")
        ttk.Button(btn_row, text="Generate New Keypair...",
                   command=self._generate_keypair).pack(side="left", padx=8)

        # ---- License details ----
        details = ttk.LabelFrame(self.root, text="License Details", padding=8)
        details.pack(fill="x", padx=12, pady=6)

        self.var_licensee = tk.StringVar()
        self.var_org = tk.StringVar()
        self.var_email = tk.StringVar()
        self.var_type = tk.StringVar(value="full")
        self.var_days = tk.StringVar(value="90")
        self.var_max_ver = tk.StringVar(value="1.99.0")

        fields = [
            ("Licensee name:", self.var_licensee),
            ("Organization:", self.var_org),
            ("Email:", self.var_email),
        ]
        for label_text, var in fields:
            row = ttk.Frame(details)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label_text, width=18, anchor="w").pack(side="left")
            ttk.Entry(row, textvariable=var, width=35).pack(side="left", fill="x", expand=True)

        # License type
        type_row = ttk.Frame(details)
        type_row.pack(fill="x", pady=2)
        ttk.Label(type_row, text="License type:", width=18, anchor="w").pack(side="left")
        ttk.Radiobutton(type_row, text="Full", variable=self.var_type, value="full").pack(side="left")
        ttk.Radiobutton(type_row, text="Trial", variable=self.var_type, value="trial").pack(side="left", padx=8)

        # Duration
        dur_row = ttk.Frame(details)
        dur_row.pack(fill="x", pady=2)
        ttk.Label(dur_row, text="Validity (days):", width=18, anchor="w").pack(side="left")
        ttk.Entry(dur_row, textvariable=self.var_days, width=8, justify="center").pack(side="left")

        # Expiry preview
        self.var_expiry_preview = tk.StringVar()
        self.var_days.trace_add("write", self._update_expiry_preview)
        self._update_expiry_preview()
        ttk.Label(dur_row, textvariable=self.var_expiry_preview,
                  font=("Arial", 8), foreground="gray").pack(side="left", padx=8)

        # Max version
        ver_row = ttk.Frame(details)
        ver_row.pack(fill="x", pady=2)
        ttk.Label(ver_row, text="Max version:", width=18, anchor="w").pack(side="left")
        ttk.Entry(ver_row, textvariable=self.var_max_ver, width=10, justify="center").pack(side="left")
        ttk.Label(ver_row, text="(license works up to this version)",
                  font=("Arial", 8), foreground="gray").pack(side="left", padx=4)

        # ---- Generate button ----
        self.btn_generate = ttk.Button(self.root, text="Generate License File...",
                                       command=self._generate_license)
        self.btn_generate.pack(fill="x", padx=12, pady=12)

        # ---- Output preview ----
        preview_frame = ttk.LabelFrame(self.root, text="Last Generated License", padding=8)
        preview_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.preview_text = tk.Text(preview_frame, font=("Courier", 9), wrap="word",
                                    state="disabled", bg="#f5f5f5", height=8)
        self.preview_text.pack(fill="both", expand=True)

    def _update_expiry_preview(self, *_):
        try:
            days = int(self.var_days.get())
            expiry = datetime.date.today() + datetime.timedelta(days=days)
            self.var_expiry_preview.set(f"Expires: {expiry.isoformat()}")
        except (ValueError, OverflowError):
            self.var_expiry_preview.set("")

    def _try_load_default_key(self):
        """Try to load private key from default location."""
        path = license_manager.get_default_private_key_path()
        if os.path.isfile(path):
            try:
                self._private_key = license_manager.load_private_key(path)
                self._key_path = path
                self.key_status.set(f"Loaded: {os.path.basename(path)}")
            except Exception as e:
                self.key_status.set(f"Failed to load default key: {e}")

    def _load_key(self):
        path = filedialog.askopenfilename(
            title="Select Private Key",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._private_key = license_manager.load_private_key(path)
            self._key_path = path
            self.key_status.set(f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Key Error", f"Could not load private key:\n{e}")

    def _generate_keypair(self):
        folder = filedialog.askdirectory(title="Select folder to save keypair")
        if not folder:
            return
        priv_path = os.path.join(folder, "private_key.pem")
        pub_path = os.path.join(folder, "public_key.pem")

        if os.path.exists(priv_path) or os.path.exists(pub_path):
            if not messagebox.askyesno("Overwrite?",
                                       "Key files already exist in this folder. Overwrite?"):
                return

        try:
            priv, pub = license_manager.generate_keypair(priv_path, pub_path)
            self._private_key = priv
            self._key_path = priv_path
            self.key_status.set(f"Generated: {priv_path}")
            messagebox.showinfo("Keypair Generated",
                                f"Private key: {priv_path}\n"
                                f"Public key:  {pub_path}\n\n"
                                f"Keep private_key.pem secure!\n"
                                f"Use public_key.pem when building the main application.")
        except Exception as e:
            messagebox.showerror("Key Generation Failed", str(e))

    def _generate_license(self):
        if self._private_key is None:
            messagebox.showwarning("No Key", "Load or generate a private key first.")
            return

        licensee = self.var_licensee.get().strip()
        org = self.var_org.get().strip()
        email = self.var_email.get().strip()

        if not licensee:
            messagebox.showwarning("Missing Field", "Licensee name is required.")
            return
        if not org:
            messagebox.showwarning("Missing Field", "Organization is required.")
            return

        try:
            days = int(self.var_days.get())
            if days < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Duration", "Days must be a positive integer.")
            return

        max_ver = self.var_max_ver.get().strip() or "1.99.0"
        lic_type = self.var_type.get()

        try:
            lic_data = license_manager.create_license(
                self._private_key,
                licensee=licensee,
                organization=org,
                email=email,
                license_type=lic_type,
                days=days,
                max_version=max_ver,
            )
        except Exception as e:
            messagebox.showerror("License Error", f"Failed to create license:\n{e}")
            return

        # Suggest filename
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in org)
        default_name = f"license_{safe_name}.lic"

        path = filedialog.asksaveasfilename(
            title="Save License File",
            initialfile=default_name,
            filetypes=[("License files", "*.lic"), ("All files", "*.*")],
            defaultextension=".lic",
        )
        if not path:
            return

        try:
            license_manager.save_license(lic_data, path)
        except Exception as e:
            messagebox.showerror("Save Failed", f"Could not save license:\n{e}")
            return

        # Show preview
        preview = (
            f"License saved: {os.path.basename(path)}\n"
            f"{'=' * 45}\n"
            f"Licensee:     {lic_data['licensee']}\n"
            f"Organization: {lic_data['organization']}\n"
            f"Email:        {lic_data['email']}\n"
            f"Type:         {lic_data['license_type']}\n"
            f"Issued:       {lic_data['issued_date']}\n"
            f"Expires:      {lic_data['expiry_date']}\n"
            f"Max version:  {lic_data['max_version']}\n"
        )
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", preview)
        self.preview_text.config(state="disabled")

        messagebox.showinfo("License Created",
                            f"License saved to:\n{path}\n\n"
                            f"Rename to 'license.lic' and place next to the application.")


def main():
    root = tk.Tk()
    app = LicenseGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
