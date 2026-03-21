# -*- coding: utf-8 -*-
"""
GovPersona launcher — compiled to GovPersona.exe by build_portable.py.
Starts the embedded Python + Streamlit server and opens the browser.
"""
import os
import sys
import subprocess
import threading
import time
import webbrowser


def _open_browser():
    time.sleep(4)
    webbrowser.open("http://localhost:8501")


def main():
    # Locate the portable root directory (same folder as this .exe)
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))

    python_exe = os.path.join(app_dir, "python", "python.exe")
    app_py    = os.path.join(app_dir, "app.py")
    models_dir = os.path.join(app_dir, "models")

    if not os.path.exists(python_exe):
        print(f"ERROR: Embedded Python not found at:\n  {python_exe}")
        print("The portable bundle may be incomplete.")
        input("\nPress Enter to exit...")
        return

    if not os.path.exists(app_py):
        print(f"ERROR: app.py not found at:\n  {app_py}")
        input("\nPress Enter to exit...")
        return

    # Build environment: point HuggingFace to the bundled model cache
    env = os.environ.copy()
    env["HF_HOME"]                      = models_dir
    env["SENTENCE_TRANSFORMERS_HOME"]   = models_dir
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    env["HF_HUB_OFFLINE"]               = "1"   # use local cache only
    env["PYTHONUTF8"]                   = "1"
    env["PYTHONIOENCODING"]             = "utf-8"

    # Load .env file (API key etc.)
    env_file = os.path.join(app_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    print("=" * 50)
    print("  GovPersona — Starting...")
    print("  URL: http://localhost:8501")
    print("  Close this window to stop the server.")
    print("=" * 50)

    # Open browser after server has had time to start
    threading.Thread(target=_open_browser, daemon=True).start()

    cmd = [
        python_exe, "-m", "streamlit", "run", app_py,
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]

    result = subprocess.run(cmd, cwd=app_dir, env=env)

    if result.returncode != 0:
        print(f"\nServer exited with code {result.returncode}.")
        input("Press Enter to close...")


if __name__ == "__main__":
    main()
