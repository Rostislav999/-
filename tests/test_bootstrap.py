import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from bootstrap import start


class StartupTests(unittest.TestCase):
    def test_setup_unicode_folder_repeat_launch_and_retained_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "Папка с пробелами (тест)"
            project.mkdir()
            shutil.copy2(Path(__file__).parents[1] / "bootstrap.py", project)
            # Empty requirements keep this integration test offline.
            (project / "requirements.txt").write_text("")
            (project / "app.py").write_text('print("TEST APP STARTED")\n')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(start(project), 0)
            log = (project / "logs/startup.log").read_text()
            self.assertIn("Creating the Python environment", log)
            self.assertIn("TEST APP STARTED", log)
            (project / "app.py").write_text('raise RuntimeError("TEST STARTUP FAILURE")\n')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(start(project), 1)
            log = (project / "logs/startup.log").read_text()
            self.assertIn("TEST STARTUP FAILURE", log)
            self.assertNotIn("Creating the Python environment", log)

    def test_incomplete_archive_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            project = Path(temp)
            self.assertEqual(start(project), 1)
            log = (project / "logs/startup.log").read_text()
            self.assertIn("Extract the complete ZIP", log)


if __name__ == "__main__":
    unittest.main()
