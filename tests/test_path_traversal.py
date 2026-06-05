"""Path-traversal guard for meeting_id-derived paths under wiki/reunioes/."""


def test_reunioes_dir_blocks_traversal(config):
    from meeting_processor.web.app import _reunioes_dir

    vp = config.vault_path
    assert _reunioes_dir(vp, "..") is None
    assert _reunioes_dir(vp, "../secret") is None
    assert _reunioes_dir(vp, "../../etc/passwd") is None
    assert _reunioes_dir(vp, "a/b") is None            # not a direct child
    # A legitimate single-folder id resolves to a direct child of reunioes/.
    ok = _reunioes_dir(vp, "2026-06-04 10h00 - reuniao")
    assert ok is not None
    assert ok.parent == (vp / "wiki" / "reunioes").resolve()


def test_summarize_rejects_traversal_id(client, config, monkeypatch):
    called = {"hit": False}

    def _fake(self, meeting_id):
        called["hit"] = True

    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline.summarize_existing", _fake
    )
    r = client.post("/api/meetings/..%2F..%2Fsecret/summarize")
    assert r.status_code == 404
    assert called["hit"] is False


def test_load_meeting_rejects_traversal(client):
    r = client.get("/api/meetings/..%2F..%2Fsecret/export.md")
    assert r.status_code == 404
