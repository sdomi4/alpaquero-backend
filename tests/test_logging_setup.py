import logging
from pathlib import Path
import sys
import tempfile
import unittest

from observatory.log_broker import log_broker
from observatory.logging_setup import (
    LoggingSettings,
    configure_logging,
    shutdown_logging,
)


class LoggingSetupTests(unittest.TestCase):
    def tearDown(self):
        shutdown_logging()

    @staticmethod
    def _flush_handlers():
        for handler in logging.getLogger().handlers:
            handler.flush()

    def test_stdout_stderr_and_logger_share_file_and_frontend_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = LoggingSettings(
                directory=Path(tmpdir),
                max_bytes=100_000,
                backup_count=2,
                frontend_history=100,
                frontend_queue_size=10,
            )
            configure_logging(settings)

            print("stdout marker")
            sys.stderr.write("stderr marker\n")
            logging.getLogger("test.application").warning("logger marker")
            logging.getLogger("uvicorn.access").info("access marker")
            logging.getLogger("watchfiles.main").info("1 change detected")
            self._flush_handlers()

            contents = settings.file_path.read_text(encoding="utf-8")
            self.assertEqual(contents.count("stdout marker"), 1)
            self.assertEqual(contents.count("stderr marker"), 1)
            self.assertEqual(contents.count("logger marker"), 1)
            self.assertEqual(contents.count("access marker"), 1)
            self.assertNotIn("1 change detected", contents)

            history = log_broker.snapshot()
            texts = [entry["text"] for entry in history]
            self.assertIn("stdout marker", texts)
            self.assertIn("stderr marker", texts)
            self.assertIn("logger marker", texts)
            self.assertIn("access marker", texts)
            self.assertNotIn("1 change detected", texts)

    def test_exception_traceback_reaches_file_and_frontend_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = LoggingSettings(
                directory=Path(tmpdir),
                max_bytes=100_000,
                backup_count=2,
            )
            configure_logging(settings)

            try:
                raise RuntimeError("traceback marker")
            except RuntimeError:
                logging.getLogger("test.exception").exception("operation failed")
            self._flush_handlers()

            contents = settings.file_path.read_text(encoding="utf-8")
            self.assertIn("operation failed", contents)
            self.assertIn("RuntimeError: traceback marker", contents)

            texts = [entry["text"] for entry in log_broker.snapshot()]
            self.assertIn("operation failed", texts)
            self.assertIn("RuntimeError: traceback marker", texts)

    def test_file_rotates_at_configured_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = LoggingSettings(
                directory=Path(tmpdir),
                max_bytes=300,
                backup_count=2,
                frontend_history=10,
                frontend_queue_size=10,
            )
            configure_logging(settings)

            logger = logging.getLogger("test.rotation")
            for index in range(30):
                logger.info("rotation marker %s %s", index, "x" * 40)
            self._flush_handlers()

            self.assertTrue(settings.file_path.exists())
            self.assertTrue(Path(f"{settings.file_path}.1").exists())
            self.assertLessEqual(
                len(list(Path(tmpdir).glob("arriero.log.*"))),
                settings.backup_count,
            )


if __name__ == "__main__":
    unittest.main()
