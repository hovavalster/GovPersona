# -*- coding: utf-8 -*-
import sys
import io
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

"""
Build GovPersona-Portable — a self-contained folder that runs on any
Windows 64-bit machine without Python installed.

Run this ONCE on your development machine:
  python build_portable.py

Output:
  GovPersona-Portable\\          <- zip and copy this to the other computer
    GovPersona.exe              <- double-click to launch
    python\\                     <- embedded Python 3.12 + all packages
    models\\                     <- HuggingFace embedding model (~460 MB)
    data\\                       <- ChromaDB (your ingested documents)
    knowledge_base\\             <- source PDFs
    agents\\, core\\, ui\\, config\\  <- app source
    app.py + other .py files
    .env                        <- your API key

Requirements on THIS machine:
  pip install pyinstaller
  (all other packages already installed)
"""

import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
import glob

# ── Config ─────────────────────────────────────────────────────────────────────

PYTHON_VERSION   = "3.12.0"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PORTABLE_DIR = os.path.join(SCRIPT_DIR, "GovPersona-Portable")
PYTHON_DIR   = os.path.join(PORTABLE_DIR, "python")
MODELS_DIR   = os.path.join(PORTABLE_DIR, "models")

# HuggingFace cache on this machine
HF_CACHE     = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
MODEL_NAME   = "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"

# Directories to copy from the GovPersona project
COPY_DIRS = ["agents", "core", "ui", "config", "knowledge_base", "data", ".streamlit"]

# Individual files to copy
COPY_FILES = [
    "app.py", "ingest.py", "download_boi.py", "download_mof.py",
    "requirements.txt", ".env",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)


def download(url, dest):
    print(f"  Downloading {os.path.basename(dest)}...")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved to {dest}")


def run(cmd, cwd=None, env=None):
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"  ERROR: command failed (exit {result.returncode})")
        sys.exit(1)


# ── Step 1: Install PyInstaller ────────────────────────────────────────────────

def install_pyinstaller():
    step("Step 1 / 7 — Install PyInstaller")
    run([sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller"])
    print("  PyInstaller ready.")


# ── Step 2: Compile launcher.py → GovPersona.exe ──────────────────────────────

def compile_launcher():
    step("Step 2 / 7 — Compile launcher.py → GovPersona.exe")
    launcher = os.path.join(SCRIPT_DIR, "launcher.py")
    if not os.path.exists(launcher):
        print("  ERROR: launcher.py not found.")
        sys.exit(1)

    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "GovPersona",
        "--distpath", PORTABLE_DIR,
        "--workpath", os.path.join(SCRIPT_DIR, "build_pyinstaller"),
        "--specpath", os.path.join(SCRIPT_DIR, "build_pyinstaller"),
        launcher,
    ])
    exe = os.path.join(PORTABLE_DIR, "GovPersona.exe")
    if not os.path.exists(exe):
        print("  ERROR: GovPersona.exe was not created.")
        sys.exit(1)
    print(f"  Created: {exe}  ({os.path.getsize(exe)//1024} KB)")


# ── Step 3: Download + set up embedded Python ─────────────────────────────────

def setup_embedded_python():
    step("Step 3 / 7 — Download & set up embedded Python 3.12")

    os.makedirs(PYTHON_DIR, exist_ok=True)

    embed_zip = os.path.join(SCRIPT_DIR, f"python-{PYTHON_VERSION}-embed-amd64.zip")
    if not os.path.exists(embed_zip):
        download(PYTHON_EMBED_URL, embed_zip)
    else:
        print(f"  Using cached {embed_zip}")

    print("  Extracting...")
    with zipfile.ZipFile(embed_zip, "r") as z:
        z.extractall(PYTHON_DIR)

    # Enable site-packages: uncomment 'import site' in python312._pth
    pth_files = glob.glob(os.path.join(PYTHON_DIR, "python*._pth"))
    if not pth_files:
        print("  WARNING: ._pth file not found — site-packages may not load.")
    else:
        pth = pth_files[0]
        with open(pth, "r") as f:
            content = f.read()
        content = content.replace("#import site", "import site")
        with open(pth, "w") as f:
            f.write(content)
        print(f"  Enabled site-packages in {os.path.basename(pth)}")

    # Install pip into embedded Python
    get_pip = os.path.join(SCRIPT_DIR, "get-pip.py")
    if not os.path.exists(get_pip):
        download(GET_PIP_URL, get_pip)
    python_exe = os.path.join(PYTHON_DIR, "python.exe")
    run([python_exe, get_pip, "--quiet"])
    print("  pip installed.")


# ── Step 4: Install packages into embedded Python ─────────────────────────────

def install_packages():
    step("Step 4 / 7 — Install packages into embedded Python")
    python_exe = os.path.join(PYTHON_DIR, "python.exe")
    req = os.path.join(SCRIPT_DIR, "requirements.txt")
    print("  This may take 5–10 minutes (downloading packages)...")
    run([
        python_exe, "-m", "pip", "install",
        "--quiet",
        "-r", req,
    ])
    print("  All packages installed.")


# ── Step 5: Copy HuggingFace model ────────────────────────────────────────────

def copy_model():
    step("Step 5 / 7 — Copy HuggingFace embedding model (~460 MB)")

    src = os.path.join(HF_CACHE, MODEL_NAME)
    if not os.path.exists(src):
        print(f"  ERROR: Model cache not found at:\n    {src}")
        print("  Run the app once on this machine first to download the model.")
        sys.exit(1)

    # We only copy the snapshots subfolder (skip redundant blobs)
    snapshots_src = os.path.join(src, "snapshots")
    if not os.path.exists(snapshots_src):
        print("  ERROR: No snapshots folder found in model cache.")
        sys.exit(1)

    # Destination: models/hub/models--.../ (HuggingFace expects this structure)
    dest_model = os.path.join(MODELS_DIR, "hub", MODEL_NAME)
    dest_snapshots = os.path.join(dest_model, "snapshots")

    if os.path.exists(dest_snapshots):
        print("  Model already copied — skipping.")
    else:
        print(f"  Copying {snapshots_src} ...")
        shutil.copytree(snapshots_src, dest_snapshots)
        print("  Model copied.")

    # Also copy refs/ folder so HuggingFace can resolve 'main'
    refs_src = os.path.join(src, "refs")
    refs_dst = os.path.join(dest_model, "refs")
    if os.path.exists(refs_src) and not os.path.exists(refs_dst):
        shutil.copytree(refs_src, refs_dst)


# ── Step 6: Copy GovPersona source + data ─────────────────────────────────────

def copy_app_files():
    step("Step 6 / 7 — Copy GovPersona source files & data")

    for fname in COPY_FILES:
        src = os.path.join(SCRIPT_DIR, fname)
        dst = os.path.join(PORTABLE_DIR, fname)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  Copied {fname}")
        else:
            print(f"  SKIP  {fname} (not found)")

    for dname in COPY_DIRS:
        src = os.path.join(SCRIPT_DIR, dname)
        dst = os.path.join(PORTABLE_DIR, dname)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            print(f"  Copied {dname}/")
        else:
            print(f"  SKIP  {dname}/ (not found)")


# ── Step 7: Summary ───────────────────────────────────────────────────────────

def print_summary():
    step("Step 7 / 7 — Done!")

    size_mb = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, files in os.walk(PORTABLE_DIR)
        for f in files
    ) // (1024 * 1024)

    print(f"  Portable folder: {PORTABLE_DIR}")
    print(f"  Total size     : ~{size_mb} MB")
    print()
    print("  NEXT STEPS:")
    print("  1. Zip the GovPersona-Portable/ folder")
    print("  2. Copy it to the other computer (USB / Google Drive)")
    print("  3. Unzip anywhere (e.g. C:\\GovPersona-Portable\\)")
    print("  4. Double-click GovPersona.exe to launch")
    print()
    print("  The app opens at http://localhost:8501 in your browser.")
    print("  NOTE: internet access is still needed for the Anthropic API.")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nGovPersona Portable Builder")
    print(f"Output: {PORTABLE_DIR}\n")

    os.makedirs(PORTABLE_DIR, exist_ok=True)

    install_pyinstaller()
    compile_launcher()
    setup_embedded_python()
    install_packages()
    copy_model()
    copy_app_files()
    print_summary()
