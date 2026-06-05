"""Diagnostic logging for the Whisper transcription step.

Verifies the dedicated whisper-debug.log helper and the failure logger that
records full tracebacks + run context to both the dedicated file and the main
module logger.
"""
import logging
from pathlib import Path

from meeting_processor.transcriber import _debug_logger, _log_run_failure


def test_debug_logger_writes_to_project_root(config):
    log = _debug_logger(config)
    file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    expected = str((Path(config.project_root) / "whisper-debug.log").resolve())
    assert Path(file_handlers[0].baseFilename).resolve() == Path(expected)
    assert log.propagate is False


def test_debug_logger_idempotent(config, tmp_path):
    _debug_logger(config)
    log = _debug_logger(config)
    file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1  # not duplicated on repeat calls

    # A new project_root re-points the single handler to the new file.
    other = tmp_path / "other"
    other.mkdir()
    config.project_root = str(other)
    log2 = _debug_logger(config)
    fhs = [h for h in log2.handlers if isinstance(h, logging.FileHandler)]
    assert len(fhs) == 1
    assert Path(fhs[0].baseFilename).resolve() == (other / "whisper-debug.log").resolve()


def test_log_run_failure_writes_traceback_and_context(config):
    try:
        raise ValueError("boom")
    except ValueError as e:
        _log_run_failure(config, "openai", {"model": "base"}, e)

    text = (Path(config.project_root) / "whisper-debug.log").read_text(encoding="utf-8")
    assert "FALHA" in text
    assert "openai" in text
    assert "base" in text                 # context dict
    assert "Traceback" in text            # full exc_info
    assert "ValueError: boom" in text


def test_log_run_failure_also_hits_main_logger(config, caplog):
    with caplog.at_level(logging.ERROR, logger="meeting_processor.transcriber"):
        try:
            raise RuntimeError("kaput")
        except RuntimeError as e:
            _log_run_failure(config, "cpp", {"returncode": 1}, e)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("cpp" in r.getMessage() for r in errors)
    assert any(r.exc_info for r in errors)  # traceback attached
