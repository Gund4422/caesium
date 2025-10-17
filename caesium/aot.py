from .piler import transpile_to_asm
import subprocess
import sys
import shutil
from pathlib import Path
import urllib.request
import zipfile

NASM_URLS = {
    "win32": "https://www.nasm.us/pub/nasm/releasebuilds/3.01rc9/win32/nasm-3.01rc9-win32.zip",
    "win64": "https://www.nasm.us/pub/nasm/releasebuilds/3.01rc9/win64/nasm-3.01rc9-win64.zip"
}

NASM_CACHE = Path(".caesium_nasm")
NASM_CACHE.mkdir(exist_ok=True)

def download_nasm():
    import platform
    arch = platform.architecture()[0]
    key = "win64" if arch == "64bit" else "win32"
    url = NASM_URLS[key]
    zip_path = NASM_CACHE / "nasm.zip"
    if not zip_path.exists():
        print("[aot] Downloading NASM...")
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(NASM_CACHE)

    # Recursively search for nasm.exe
    for path in NASM_CACHE.rglob("nasm.exe"):
        return path

    raise FileNotFoundError("Could not find nasm.exe after extraction!")

def aot(func):
    """
    Decorator to compile a Python math function to NASM and execute.
    """
    def wrapper(*args, **kwargs):
        asm_file = transpile_to_asm(func)
        nasm_exe = download_nasm()
        bin_file = asm_file.with_suffix(".exe")
        subprocess.run([str(nasm_exe), "-f", "win64", str(asm_file), "-o", str(bin_file)], check=True)
        return bin_file
    return wrapper
