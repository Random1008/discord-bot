from unittest.mock import Mock

import discord

from services.welcome_config import (
    DEFAULT_TEXT,
    DEFAULT_TITLE,
    build_welcome_embed,
    load_welcome_config,
    render_welcome_text,
    save_welcome_config,
)


def FakeMember(mention="<@123>"):
    member = Mock(spec=discord.Member)
    member.mention = mention
    return member


def test_load_welcome_config_returns_defaults_when_file_missing(tmp_path):
    config = load_welcome_config(tmp_path / "does-not-exist.json")

    assert config == {"title": DEFAULT_TITLE, "text": DEFAULT_TEXT, "image_url": None}


def test_save_then_load_welcome_config_round_trips(tmp_path):
    path = tmp_path / "welcome_config.json"

    save_welcome_config(path, "Salut !", "Hey {membre}, welcome.", "https://example.com/banner.png")
    config = load_welcome_config(path)

    assert config == {"title": "Salut !", "text": "Hey {membre}, welcome.", "image_url": "https://example.com/banner.png"}


def test_save_welcome_config_persists_a_null_image_url(tmp_path):
    path = tmp_path / "welcome_config.json"

    save_welcome_config(path, "Salut !", "Hey {membre}.", None)
    config = load_welcome_config(path)

    assert config["image_url"] is None


def test_render_welcome_text_replaces_placeholder_with_the_members_mention():
    member = FakeMember(mention="<@999>")

    result = render_welcome_text("Bienvenue {membre} !", member)

    assert result == "Bienvenue <@999> !"


def test_render_welcome_text_leaves_the_placeholder_literal_when_no_member_given():
    result = render_welcome_text("Bienvenue {membre} !", None)

    assert result == "Bienvenue {membre} !"


def test_build_welcome_embed_sets_title_description_and_image():
    config = {"title": "Salut", "text": "Coucou {membre}", "image_url": "https://example.com/x.png"}
    member = FakeMember(mention="<@42>")

    embed = build_welcome_embed(config, member)

    assert embed.title == "Salut"
    assert embed.description == "Coucou <@42>"
    assert embed.image.url == "https://example.com/x.png"


def test_build_welcome_embed_has_no_image_when_not_configured():
    config = {"title": "Salut", "text": "Coucou", "image_url": None}

    embed = build_welcome_embed(config)

    assert embed.image.url is None
