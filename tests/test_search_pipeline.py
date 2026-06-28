"""Hook de indexação para busca no pipeline (best-effort, opt-in)."""
from datetime import datetime

from meeting_processor import search_index as si
from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.pipeline import MeetingPipeline


def _write_meeting(config):
    """Cria uma reunião só-transcrição e devolve (pipeline, paths, transcript)."""
    transcript = Transcript(
        segments=[
            TranscriptSegment(start=0.0, end=2.0, text="alpha"),
            TranscriptSegment(start=2.0, end=4.0, text="beta"),
        ],
        full_text="alpha beta", language="pt", duration=4.0,
    )
    pipe = MeetingPipeline(config)
    paths = pipe.note_generator.prepare("reuniao.mp4", datetime(2026, 6, 5, 10, 0))
    pipe.note_generator.write_transcription(transcript, paths)
    return pipe, paths, transcript


def test_index_for_search_indexes_when_enabled(config, monkeypatch):
    config.enable_search_index = True
    monkeypatch.setattr("meeting_processor.pipeline.ollama_service.embed",
                        lambda text, cfg: [float(len(text)), 1.0])
    pipe, paths, transcript = _write_meeting(config)
    pipe._index_for_search(paths, transcript)
    rows = si.load_index(config.vault_path)
    assert len(rows) == 1
    assert rows[0]["meeting_id"] == paths.meeting_dir.name
    assert rows[0]["text"] == "alpha beta"


def test_index_for_search_noop_when_disabled(config, monkeypatch):
    config.enable_search_index = False
    called = {"n": 0}
    monkeypatch.setattr("meeting_processor.pipeline.ollama_service.embed",
                        lambda text, cfg: called.__setitem__("n", called["n"] + 1) or [1.0])
    pipe, paths, transcript = _write_meeting(config)
    pipe._index_for_search(paths, transcript)
    assert called["n"] == 0
    assert si.load_index(config.vault_path) == []


def test_index_for_search_best_effort_on_ollama_off(config, monkeypatch):
    config.enable_search_index = True
    from meeting_processor.ollama_service import EmbeddingError

    def _boom(text, cfg):
        raise EmbeddingError("off")

    monkeypatch.setattr("meeting_processor.pipeline.ollama_service.embed", _boom)
    pipe, paths, transcript = _write_meeting(config)
    pipe._index_for_search(paths, transcript)  # não pode levantar
    assert si.load_index(config.vault_path) == []
