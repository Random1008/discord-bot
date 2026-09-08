from services.proces_config import (
    DEFAULT_REGLEMENT,
    DEFAULT_TEXT,
    DEFAULT_TITLE,
    build_proces_embed,
    get_proces_reglement,
    load_proces_config,
    save_proces_config,
)


def test_load_defaults_for_missing_file(tmp_path):
    config = load_proces_config(tmp_path / "nope.json")
    assert config["title"] == DEFAULT_TITLE
    assert config["text"] == DEFAULT_TEXT
    assert config["reglement"] == DEFAULT_REGLEMENT


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "proces_config.json"
    save_proces_config(path, "Titre test", "Texte test")
    config = load_proces_config(path)
    assert config["title"] == "Titre test"
    assert config["text"] == "Texte test"


def test_save_and_load_reglement_roundtrip(tmp_path):
    path = tmp_path / "proces_config.json"
    save_proces_config(path, "Titre test", "Texte test", reglement="Article 1 : pas d'insultes.")
    config = load_proces_config(path)
    assert config["reglement"] == "Article 1 : pas d'insultes."


def test_save_without_reglement_keeps_existing(tmp_path):
    path = tmp_path / "proces_config.json"
    save_proces_config(path, "T", "X", reglement="Règlement existant")
    # un enregistrement titre/texte seul ne doit pas écraser le règlement
    save_proces_config(path, "T2", "X2")
    assert load_proces_config(path)["reglement"] == "Règlement existant"


def test_save_empty_reglement_falls_back_to_default(tmp_path):
    path = tmp_path / "proces_config.json"
    save_proces_config(path, "T", "X", reglement="")
    assert load_proces_config(path)["reglement"] == DEFAULT_REGLEMENT


def test_get_proces_reglement_default(tmp_path):
    assert get_proces_reglement(tmp_path / "absent.json") == DEFAULT_REGLEMENT


def test_build_embed():
    embed = build_proces_embed({"title": "T", "text": "X"})
    assert embed.title == "T"
    assert embed.description == "X"
