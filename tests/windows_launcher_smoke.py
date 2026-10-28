"""Exercise the distributed BAT files and a real Tk window on Windows."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if os.name != "nt":
        raise SystemExit("This smoke test requires Windows.")
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "Папка с пробелами (тест)" / "--main"
        shutil.copytree(source, project, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "logs"))
        environment = dict(os.environ, PROTOCOL_NO_PAUSE="1", PYTHONUTF8="1")
        for launcher in ("start.bat", "Запустить_Windows.bat"):
            result = subprocess.run(["cmd.exe", "/d", "/c", launcher, "--smoke-test"],
                                    cwd=project, env=environment, timeout=600)
            assert result.returncode == 0, f"{launcher}: exit {result.returncode}"
            log = (project / "logs/startup.log").read_text(encoding="utf-8")
            assert "Application closed normally." in log, log
            print(f"Verified: {launcher}: Tk window opened and closed; Unicode/space/parentheses path OK")

        # The new Python install manager can return a NEGATIVE Windows HRESULT
        # when 3.12 is absent. IF NOT ERRORLEVEL 1 wrongly treats that as success.
        # Emulate that exact result, then exercise both supported fallback routes.
        shim = Path(temp) / "python-launcher-shim"
        shim.mkdir()
        for fallback_to_python in (False, True):
            script = [
                "@echo off",
                'echo %1>>"%~dp0calls.txt"',
                'if "%1"=="-3.12" exit /b -1610612730',
            ]
            if fallback_to_python:
                script.append("exit /b -1610612730")
            else:
                script += [
                    'if not "%1"=="-3" exit /b 1',
                    f'"{sys.executable}" %2 %3 %4 %5 %6 %7 %8 %9',
                    "exit /b %ERRORLEVEL%",
                ]
            (shim / "py.cmd").write_bytes(("\r\n".join(script) + "\r\n").encode("ascii"))
            calls = shim / "calls.txt"
            calls.unlink(missing_ok=True)
            fallback_env = dict(environment, PATH=str(shim) + os.pathsep + environment.get("PATH", ""))
            result = subprocess.run(["cmd.exe", "/d", "/c", "start.bat", "--smoke-test"],
                                    cwd=project, env=fallback_env, timeout=120)
            assert result.returncode == 0, f"Missing Python 3.12 fallback: exit {result.returncode}"
            requests = calls.read_text(encoding="utf-8").splitlines()
            assert requests[:2] == ["-3.12", "-3"], requests
            log = (project / "logs/startup.log").read_text(encoding="utf-8")
            assert "Application closed normally." in log, log
            route = "python on PATH" if fallback_to_python else "default py -3"
            print(f"Verified: missing Python 3.12 / HRESULT -1610612730 -> {route} -> real Tk window")


if __name__ == "__main__":
    main()
