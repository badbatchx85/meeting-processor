"""MEETING_DATA_DIR redirects all writable paths to a single base dir."""
from pathlib import Path

from meeting_processor.config import load_config


def test_data_dir_env_redirects_writable_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "appsupport"
    monkeypatch.setenv("MEETING_DATA_DIR", str(data_dir))

    cfg = load_config()

    # project_root and everything derived from it move under the data dir.
    assert Path(cfg.project_root) == data_dir
    assert cfg.vault_path == data_dir / cfg.vault_dir
    assert cfg.temp_path == data_dir / cfg.temp_dir
    # load_config creates the temp dir under the data dir, not the repo.
    assert cfg.temp_path.exists()


def test_no_env_falls_back_to_package_root(tmp_path, monkeypatch):
    monkeypatch.delenv("MEETING_DATA_DIR", raising=False)
    cfg = load_config()
    # Default: two levels up from meeting_processor/config.py == repo root.
    expected = Path(__file__).resolve().parent.parent
    assert Path(cfg.project_root) == expected


def test_relative_data_dir_is_resolved_to_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_DATA_DIR", "./appsupport")
    cfg = load_config()
    assert Path(cfg.project_root).is_absolute()
    assert Path(cfg.project_root) == (tmp_path / "appsupport").resolve()
