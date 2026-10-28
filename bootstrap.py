"""Visible, logged setup and startup; usable before third-party packages exist."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import traceback


def requirements_installed(project: Path) -> bool:
    for line in (project / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        package, separator, version = line.strip().partition("==")
        if not separator:
            return False
        try:
            if importlib.metadata.version(package) != version:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def start(project: Path, smoke_test: bool = False) -> int:
    """Return the actual application exit code and retain diagnostics on failure."""
    log_dir = project / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "startup.log"
    with log_path.open("w", encoding="utf-8") as log:
        def say(text):
            print(text, flush=True)
            log.write(text + "\n")
            log.flush()

        def run(command):
            # Preserve proxy and TLS configuration; never dump environment values.
            environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            with subprocess.Popen(command, cwd=project, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                  errors="replace", env=environment) as process:
                for line in process.stdout:
                    say(line.rstrip("\r\n"))
                return process.wait()

        try:
            say("Protocol to Excel - startup")
            say(f"Python: {sys.version.split()[0]} ({sys.executable})")
            say(f"Folder: {project}")
            if sys.version_info < (3, 10):
                raise RuntimeError("Python 3.10 or newer is required. Install Python 3.12 (64-bit).")
            for name in ("app.py", "requirements.txt"):
                if not (project / name).is_file():
                    raise RuntimeError(f"Missing {name}. Extract the complete ZIP archive first.")
            python = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not python.is_file():
                say("[1/3] Creating the Python environment. Please wait...")
                code = run([sys.executable, "-m", "venv", str(project / ".venv")])
                if code:
                    raise RuntimeError("Could not create .venv. See the preceding error; check your Python installation and folder permissions.")
            check = run([str(python), str(project / "bootstrap.py"), "--check-dependencies"])
            if check:
                say("[2/3] Installing required packages. Internet is needed for this step...")
                code = run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                            "-r", str(project / "requirements.txt")])
                if code:
                    raise RuntimeError("Package installation failed. Keep the firewall enabled; see the pip error above.")
            else:
                say("[2/3] Required packages are already installed.")
            say("[3/3] Opening the application...")
            command = [str(python), "-u", str(project / "app.py")]
            if smoke_test:
                command.append("--smoke-test")
            code = run(command)
            if code:
                say(f"Application failed with exit code {code}.")
                say("If the error mentions tkinter/_tkinter, repair Python and enable Tcl/Tk.")
            else:
                say("Application closed normally.")
            say(f"Startup log: {log_path}")
            return code
        except Exception:
            say(traceback.format_exc())
            say(f"Startup failed. Log: {log_path}")
            return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-dependencies", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    if args.check_dependencies:
        return 0 if requirements_installed(project) else 1
    return start(project, args.smoke_test)


if __name__ == "__main__":
    raise SystemExit(main())
