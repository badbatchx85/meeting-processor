"""Auto-start of the Ollama server when processing with the local provider."""
import meeting_processor.ollama_service as svc


def test_is_running_true_on_200(monkeypatch):
    class _R:
        status_code = 200

    monkeypatch.setattr("httpx.get", lambda *a, **k: _R())
    assert svc.is_running("http://localhost:11434") is True


def test_is_running_false_on_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("connrefused")

    monkeypatch.setattr("httpx.get", _boom)
    assert svc.is_running("http://localhost:11434") is False


def test_ensure_running_noop_when_already_up(config, monkeypatch):
    monkeypatch.setattr(svc, "is_running", lambda base: True)
    spawned = {"n": 0}
    monkeypatch.setattr(svc.subprocess, "Popen", lambda *a, **k: spawned.__setitem__("n", spawned["n"] + 1))
    assert svc.ensure_running(config) is True
    assert spawned["n"] == 0


def test_ensure_running_false_when_binary_missing(config, monkeypatch):
    monkeypatch.setattr(svc, "is_running", lambda base: False)
    monkeypatch.setattr(svc.shutil, "which", lambda name: None)
    spawned = {"n": 0}
    monkeypatch.setattr(svc.subprocess, "Popen", lambda *a, **k: spawned.__setitem__("n", spawned["n"] + 1))
    assert svc.ensure_running(config) is False
    assert spawned["n"] == 0


def test_ensure_running_starts_ollama(config, monkeypatch):
    calls = {"running": [False, True], "popen": 0}

    def _is_running(base):
        return calls["running"].pop(0) if calls["running"] else True

    monkeypatch.setattr(svc, "is_running", _is_running)
    monkeypatch.setattr(svc.shutil, "which", lambda name: "/usr/local/bin/ollama")
    monkeypatch.setattr(svc.subprocess, "Popen", lambda *a, **k: calls.__setitem__("popen", calls["popen"] + 1))
    assert svc.ensure_running(config, timeout=5) is True
    assert calls["popen"] == 1


def test_pipeline_summary_ensures_ollama_for_local(config, monkeypatch):
    """summarize_existing with local provider triggers ensure_running."""
    from datetime import datetime
    from meeting_processor.models import MeetingSummary, Transcript, TranscriptSegment
    from meeting_processor.note_generator import NoteGenerator
    from meeting_processor.pipeline import MeetingPipeline

    config.llm_provider = "local"
    called = {"ensure": 0}
    monkeypatch.setattr(
        "meeting_processor.ollama_service.ensure_running",
        lambda cfg, **k: called.__setitem__("ensure", called["ensure"] + 1) or True,
    )

    class _FakeSummarizer:
        def __init__(self, *a, **k): ...
        def summarize(self, transcript, source_filename):
            return MeetingSummary(
                executive_summary="x", time_windows=[], action_items=[],
                participants=[], key_topics=[],
            )

    monkeypatch.setattr("meeting_processor.pipeline.MeetingSummarizer", lambda cfg: _FakeSummarizer())

    # Write a transcription-only meeting to summarize.
    transcript = Transcript(
        segments=[TranscriptSegment(start=0.0, end=2.0, text="oi")],
        full_text="oi", language="pt", duration=2.0,
    )
    gen = NoteGenerator(config)
    paths = gen.prepare("reuniao.mp4", datetime(2026, 6, 5, 10, 0))
    gen.write_transcription(transcript, paths)

    MeetingPipeline(config).summarize_existing(paths.meeting_dir.name)
    assert called["ensure"] == 1
