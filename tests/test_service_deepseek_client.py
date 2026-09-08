import json

import pytest

from services import deepseek_client
from services.deepseek_client import DeepSeekError, conduct_clarification_turn


class _FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, body: str = ""):
        self.status = status
        self._payload = payload
        self._body = body

    async def json(self):
        return self._payload

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_payload = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_payload = json
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _install_fake_session(monkeypatch, response: _FakeResponse):
    fake_session = _FakeSession(response)
    monkeypatch.setattr(deepseek_client.aiohttp, "ClientSession", lambda: fake_session)
    return fake_session


def _content_response(content: dict) -> _FakeResponse:
    payload = {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}
    return _FakeResponse(status=200, payload=payload)


@pytest.mark.asyncio
async def test_returns_a_question_when_deepseek_is_not_done(monkeypatch):
    _install_fake_session(monkeypatch, _content_response({"done": False, "question": "Quel préfixe veux-tu ?"}))

    turn = await conduct_clarification_turn("je veux une commande musique", [], api_key="key")

    assert turn.done is False
    assert turn.question == "Quel préfixe veux-tu ?"
    assert turn.final_prompt is None


@pytest.mark.asyncio
async def test_returns_the_final_prompt_when_deepseek_is_done(monkeypatch):
    _install_fake_session(monkeypatch, _content_response({"done": True, "final_prompt": "Ajoute une commande ..."}))

    turn = await conduct_clarification_turn("je veux une commande musique", [("Quel préfixe ?", "!")], api_key="key")

    assert turn.done is True
    assert turn.final_prompt == "Ajoute une commande ..."


@pytest.mark.asyncio
async def test_force_done_asks_deepseek_to_wrap_up_even_if_it_would_keep_asking(monkeypatch):
    fake_session = _install_fake_session(
        monkeypatch, _content_response({"done": True, "final_prompt": "Prompt final synthétisé"})
    )

    turn = await conduct_clarification_turn(
        "je veux une commande musique", [("Q1", "R1")] * 5, api_key="key", force_done=True
    )

    assert turn.done is True
    last_message = fake_session.last_payload["messages"][-1]
    assert last_message["role"] == "user"
    assert "arrête de poser des questions" in last_message["content"]


@pytest.mark.asyncio
async def test_history_is_replayed_as_alternating_assistant_and_user_messages(monkeypatch):
    fake_session = _install_fake_session(
        monkeypatch, _content_response({"done": False, "question": "Suite ?"})
    )

    await conduct_clarification_turn(
        "idée", [("Quel préfixe ?", "!"), ("Quel nom de commande ?", "musique")], api_key="key"
    )

    messages = fake_session.last_payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Idée initiale proposée par un membre : idée"}
    assert json.loads(messages[2]["content"]) == {"done": False, "question": "Quel préfixe ?"}
    assert messages[3] == {"role": "user", "content": "!"}
    assert json.loads(messages[4]["content"]) == {"done": False, "question": "Quel nom de commande ?"}
    assert messages[5] == {"role": "user", "content": "musique"}


@pytest.mark.asyncio
async def test_raises_deepseek_error_on_non_200_status(monkeypatch):
    _install_fake_session(monkeypatch, _FakeResponse(status=500, body="internal error"))

    with pytest.raises(DeepSeekError):
        await conduct_clarification_turn("idée", [], api_key="key")


@pytest.mark.asyncio
async def test_raises_deepseek_error_on_non_json_content(monkeypatch):
    payload = {"choices": [{"message": {"content": "not json"}}]}
    _install_fake_session(monkeypatch, _FakeResponse(status=200, payload=payload))

    with pytest.raises(DeepSeekError):
        await conduct_clarification_turn("idée", [], api_key="key")


@pytest.mark.asyncio
async def test_raises_deepseek_error_when_done_true_but_no_final_prompt(monkeypatch):
    _install_fake_session(monkeypatch, _content_response({"done": True}))

    with pytest.raises(DeepSeekError):
        await conduct_clarification_turn("idée", [], api_key="key")


@pytest.mark.asyncio
async def test_raises_deepseek_error_when_not_done_and_no_question(monkeypatch):
    _install_fake_session(monkeypatch, _content_response({"done": False}))

    with pytest.raises(DeepSeekError):
        await conduct_clarification_turn("idée", [], api_key="key")
