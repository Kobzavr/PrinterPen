"""
build_exe.py — Builds standalone Windows executable using PyInstaller.

Usage:
    python build_exe.py
"""
import os
import subprocess
import sys
import shutil

def build():
    print("=" * 60)
    print("PrinterPen — Building Standalone Windows Executable")
    print("=" * 60)

    try:
        import PyInstaller
    except ImportError:
        print("[*] PyInstaller not found. Installing into current environment...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "PrinterPen",
        "--icon", "logo.ico",
        "--add-data", "fonts;fonts",
        "--add-data", "resources;resources",
        "--add-data", "logo.ico;.",
        "main.py"
    ]

    print("\n[*] Executing PyInstaller...")
    subprocess.check_call(cmd)

    dist_dir = os.path.join("dist", "PrinterPen")
    zip_dest = os.path.join("dist", "PrinterPen-windows-x64")

    if os.path.exists(dist_dir):
        print("\n[*] Packaging dist/PrinterPen into dist/PrinterPen-windows-x64.zip...")
        shutil.make_archive(zip_dest, "zip", dist_dir)
        print(f"\n[+] Success! Standalone package created:")
        print(f"    Folder: {os.path.abspath(dist_dir)}")
        print(f"    ZIP:    {os.path.abspath(zip_dest)}.zip")
    else:
        print("\n[-] Build failed or dist/PrinterPen not found.")

if __name__ == "__main__":
    build()
