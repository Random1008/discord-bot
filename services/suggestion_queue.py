import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

QUEUE_ROOT = Path(__file__).resolve().parent.parent / "automation_queue"
PENDING_DIR = QUEUE_ROOT / "pending"
PROCESSING_DIR = QUEUE_ROOT / "processing"
DONE_DIR = QUEUE_ROOT / "done"
FAILED_DIR = QUEUE_ROOT / "failed"


def write_suggestion_job(
    *,
    requester_id: int,
    requester_display: str,
    guild_id: int,
    channel_id: int,
    idea: str,
    transcript: list[tuple[str, str]],
    final_prompt: str,
    pending_dir: Path = PENDING_DIR,
) -> str:
    pending_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "requester_id": requester_id,
        "requester_display": requester_display,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "idea": idea,
        "transcript": [{"question": question, "answer": answer} for question, answer in transcript],
        "final_prompt": final_prompt,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (pending_dir / f"{job_id}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job_id
