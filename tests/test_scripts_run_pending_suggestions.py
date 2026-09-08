import json

from scripts.run_pending_suggestions import _truncate, process_job


def _write_job(pending_dir, **overrides):
    pending_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "id": "job-1",
        "requester_id": 1,
        "requester_display": "Requester",
        "guild_id": 2,
        "channel_id": 3,
        "idea": "je veux une commande musique",
        "transcript": [],
        "final_prompt": "Ajoute une commande musique.",
        "created_at": "2026-07-29T00:00:00+00:00",
    }
    job.update(overrides)
    path = pending_dir / "job-1.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    return path


def _dirs(tmp_path):
    return {
        "processing_dir": tmp_path / "processing",
        "done_dir": tmp_path / "done",
        "failed_dir": tmp_path / "failed",
    }


def test_truncate_leaves_short_text_untouched():
    assert _truncate("short", limit=100) == "short"


def test_truncate_keeps_the_tail_of_long_text():
    text = "x" * 50 + "END"
    assert _truncate(text, limit=10) == "xxxxxxxEND"


def test_process_job_succeeds_through_claude_tests_and_deploy(tmp_path):
    pending_dir = tmp_path / "pending"
    job_path = _write_job(pending_dir)
    dirs = _dirs(tmp_path)

    result = process_job(
        job_path,
        **dirs,
        claude_runner=lambda prompt: (True, "claude ok"),
        test_runner=lambda: (True, "tests ok"),
        deploy_runner=lambda: (True, "deploy ok"),
    )

    assert result["success"] is True
    assert result["stage"] == "done"
    assert not job_path.exists()
    assert not (dirs["processing_dir"] / "job-1.json").exists()
    done_file = dirs["done_dir"] / "job-1.json"
    assert done_file.exists()
    saved = json.loads(done_file.read_text(encoding="utf-8"))
    assert saved["id"] == "job-1"
    assert saved["requester_id"] == 1


def test_process_job_stops_and_marks_failed_when_claude_fails(tmp_path):
    pending_dir = tmp_path / "pending"
    job_path = _write_job(pending_dir)
    dirs = _dirs(tmp_path)
    test_runner_called = False

    def test_runner():
        nonlocal test_runner_called
        test_runner_called = True
        return True, "should not run"

    result = process_job(
        job_path,
        **dirs,
        claude_runner=lambda prompt: (False, "claude failed"),
        test_runner=test_runner,
        deploy_runner=lambda: (True, "deploy ok"),
    )

    assert result["success"] is False
    assert result["stage"] == "claude"
    assert test_runner_called is False
    assert (dirs["failed_dir"] / "job-1.json").exists()
    assert not (dirs["done_dir"] / "job-1.json").exists()


def test_process_job_stops_and_marks_failed_when_tests_fail_without_deploying(tmp_path):
    pending_dir = tmp_path / "pending"
    job_path = _write_job(pending_dir)
    dirs = _dirs(tmp_path)
    deploy_runner_called = False

    def deploy_runner():
        nonlocal deploy_runner_called
        deploy_runner_called = True
        return True, "should not run"

    result = process_job(
        job_path,
        **dirs,
        claude_runner=lambda prompt: (True, "claude ok"),
        test_runner=lambda: (False, "2 failed"),
        deploy_runner=deploy_runner,
    )

    assert result["success"] is False
    assert result["stage"] == "tests"
    assert deploy_runner_called is False
    assert (dirs["failed_dir"] / "job-1.json").exists()


def test_process_job_marks_failed_when_deploy_fails_after_green_tests(tmp_path):
    pending_dir = tmp_path / "pending"
    job_path = _write_job(pending_dir)
    dirs = _dirs(tmp_path)

    result = process_job(
        job_path,
        **dirs,
        claude_runner=lambda prompt: (True, "claude ok"),
        test_runner=lambda: (True, "tests ok"),
        deploy_runner=lambda: (False, "deploy failed"),
    )

    assert result["success"] is False
    assert result["stage"] == "deploy"
    assert (dirs["failed_dir"] / "job-1.json").exists()


def test_run_claude_receives_the_final_prompt_and_forwards_the_argument(tmp_path):
    pending_dir = tmp_path / "pending"
    job_path = _write_job(pending_dir, final_prompt="Prompt bien précis")
    dirs = _dirs(tmp_path)
    seen_prompts = []

    def claude_runner(prompt):
        seen_prompts.append(prompt)
        return True, "ok"

    process_job(
        job_path,
        **dirs,
        claude_runner=claude_runner,
        test_runner=lambda: (True, "ok"),
        deploy_runner=lambda: (True, "ok"),
    )

    assert seen_prompts == ["Prompt bien précis"]
