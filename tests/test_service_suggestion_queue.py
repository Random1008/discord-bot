import json

from services.suggestion_queue import write_suggestion_job


def test_write_suggestion_job_creates_the_pending_directory_and_a_json_file(tmp_path):
    pending_dir = tmp_path / "pending"

    job_id = write_suggestion_job(
        requester_id=1,
        requester_display="Requester",
        guild_id=2,
        channel_id=3,
        idea="je veux une commande musique",
        transcript=[("Quel préfixe ?", "!")],
        final_prompt="Ajoute une commande musique.",
        pending_dir=pending_dir,
    )

    files = list(pending_dir.glob("*.json"))
    assert len(files) == 1
    assert files[0].stem == job_id


def test_write_suggestion_job_content_is_complete_and_well_formed(tmp_path):
    pending_dir = tmp_path / "pending"

    job_id = write_suggestion_job(
        requester_id=1,
        requester_display="Requester",
        guild_id=2,
        channel_id=3,
        idea="je veux une commande musique",
        transcript=[("Quel préfixe ?", "!"), ("Quel nom ?", "musique")],
        final_prompt="Ajoute une commande musique.",
        pending_dir=pending_dir,
    )

    data = json.loads((pending_dir / f"{job_id}.json").read_text(encoding="utf-8"))

    assert data["id"] == job_id
    assert data["requester_id"] == 1
    assert data["requester_display"] == "Requester"
    assert data["guild_id"] == 2
    assert data["channel_id"] == 3
    assert data["idea"] == "je veux une commande musique"
    assert data["final_prompt"] == "Ajoute une commande musique."
    assert data["transcript"] == [
        {"question": "Quel préfixe ?", "answer": "!"},
        {"question": "Quel nom ?", "answer": "musique"},
    ]
    assert "created_at" in data


def test_write_suggestion_job_generates_a_unique_id_per_call(tmp_path):
    pending_dir = tmp_path / "pending"

    id_one = write_suggestion_job(
        requester_id=1, requester_display="R", guild_id=1, channel_id=1,
        idea="idea", transcript=[], final_prompt="prompt", pending_dir=pending_dir,
    )
    id_two = write_suggestion_job(
        requester_id=1, requester_display="R", guild_id=1, channel_id=1,
        idea="idea", transcript=[], final_prompt="prompt", pending_dir=pending_dir,
    )

    assert id_one != id_two
    assert len(list(pending_dir.glob("*.json"))) == 2
