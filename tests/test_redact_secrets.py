"""Redação de segredos (chaves de API / tokens) em mensagens de erro."""
from datetime import datetime

from meeting_processor import generation_log
from meeting_processor.dashboard import ProcessingJob
from meeting_processor.utils import redact_secrets


def test_redacts_url_key():
    # Fake, clearly-non-real value — never put a live key in a fixture.
    s = (
        "Falha ao chamar o Gemini: 429 for url "
        "'https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
        "?key=DUMMY_test_key_not_a_real_secret_000'"
    )
    out = redact_secrets(s)
    assert "DUMMY_test_key_not_a_real_secret_000" not in out
    assert "key=REDACTED" in out


def test_redacts_bearer_and_sk():
    assert "REDACTED" in redact_secrets("Authorization: Bearer abc.def.ghi123")
    out = redact_secrets("usando sk-ant-api03-AbCdEfGh1234567890xyz para auth")
    assert "sk-ant-api03-AbCdEf" not in out
    assert "sk-REDACTED" in out


def test_preserves_normal_text():
    msg = "Falha ao chamar o Gemini após 3 tentativas"
    assert redact_secrets(msg) == msg
    assert redact_secrets("") == ""


def test_job_fail_redacts():
    job = ProcessingJob("x.mp4")
    job.fail("erro url?key=SUPERSECRETVALUE123")
    assert "SUPERSECRETVALUE123" not in job.error_message
    assert "key=REDACTED" in job.error_message


def test_generation_log_redacts(tmp_path):
    d = tmp_path / "meeting"
    d.mkdir()
    now = datetime(2026, 1, 1, 10, 0, 0)
    generation_log.append(
        d, "summary", "error",
        error="boom url?key=SUPERSECRETVALUE123",
        started=now, completed=now,
    )
    entry = generation_log.read(d)[0]
    assert "SUPERSECRETVALUE123" not in (entry.get("error") or "")
    assert "REDACTED" in entry["error"]
