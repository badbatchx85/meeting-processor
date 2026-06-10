"""Endpoint de mídia (range streaming) para o player de transcrição."""
from pathlib import Path


def _seed(config, meeting_id, stem, data=b"0123456789"):
    (config.reunioes_path / meeting_id).mkdir(parents=True, exist_ok=True)
    uploads = Path(config.project_root) / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / f"{stem}.mp4").write_bytes(data)


def test_media_serves_source_bytes(client, config):
    mid = "2026-01-01 10h00 - reuniao"
    _seed(config, mid, "reuniao", b"VIDEOBYTES")
    r = client.get(f"/api/meetings/{mid}/media")
    assert r.status_code == 200
    assert r.content == b"VIDEOBYTES"


def test_media_supports_range(client, config):
    mid = "2026-01-02 10h00 - r2"
    _seed(config, mid, "r2", b"0123456789")
    r = client.get(f"/api/meetings/{mid}/media", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206
    assert r.content == b"0123"
    assert r.headers.get("content-range") == "bytes 0-3/10"


def test_media_404_when_no_source(client, config):
    mid = "2026-01-03 10h00 - nope"
    (config.reunioes_path / mid).mkdir(parents=True, exist_ok=True)
    r = client.get(f"/api/meetings/{mid}/media")
    assert r.status_code == 404
