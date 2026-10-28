"""Exercise the distributed BAT files and a real Tk window on Windows."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    if os.name != "nt":
        raise SystemExit("This smoke test requires Windows.")
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "Папка с пробелами (тест)" / "--main"
        shutil.copytree(source, project, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "logs"))
        environment = dict(os.environ, PROTOCOL_NO_PAUSE="1")
        for launcher in ("start.bat", "Запустить_Windows.bat"):
            result = subprocess.run(["cmd.exe", "/d", "/c", launcher, "--smoke-test"],
                                    cwd=project, env=environment, timeout=600)
            assert result.returncode == 0, f"{launcher}: exit {result.returncode}"
            log = (project / "logs/startup.log").read_text(encoding="utf-8")
            assert "Application closed normally." in log, log
            print(f"Verified: {launcher}: Tk window opened and closed; Unicode/space/parentheses path OK")


if __name__ == "__main__":
    main()
