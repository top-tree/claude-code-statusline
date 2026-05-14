import json

from scripts import config


def test_load_config_reads_valid_json(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"symbol": "¥", "pricing": {"m": {"input": 1}}}))
    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_path))

    assert config.load_config() == {"symbol": "¥", "pricing": {"m": {"input": 1}}}


def test_load_config_returns_none_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", str(tmp_path / "missing.json"))

    assert config.load_config() is None


def test_load_config_returns_none_for_invalid_json(tmp_path, monkeypatch):
    cfg_path = tmp_path / "bad.json"
    cfg_path.write_text("{")
    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_path))

    assert config.load_config() is None


def test_load_config_returns_none_for_array_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "arr.json"
    cfg_path.write_text(json.dumps(["bad", "config"]))
    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_path))

    assert config.load_config() is None


def test_load_config_returns_none_for_string_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "str.json"
    cfg_path.write_text(json.dumps("just a string"))
    monkeypatch.setattr(config, "CONFIG_FILE", str(cfg_path))

    assert config.load_config() is None

