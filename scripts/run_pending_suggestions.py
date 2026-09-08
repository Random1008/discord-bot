import json
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from services.suggestion_queue import DONE_DIR, FAILED_DIR, PENDING_DIR, PROCESSING_DIR

COLOMBINA_DIR = Path(__file__).resolve().parent.parent
BOT_PARENT_DIR = COLOMBINA_DIR.parent

POLL_INTERVAL_SECONDS = 15
CLAUDE_TIMEOUT_SECONDS = 1800
TEST_TIMEOUT_SECONDS = 600
DEPLOY_TIMEOUT_SECONDS = 600
OUTPUT_TRUNCATE_CHARS = 4000

CLAUDE_PROMPT_TEMPLATE = """Tu es invoqué automatiquement pour implémenter une demande de fonctionnalité pour le \
bot Discord "colombina". La demande a déjà été validée par les administrateurs du serveur puis clarifiée via un \
entretien avec le membre qui l'a proposée. Travaille dans ce dépôt.

RÈGLES STRICTES :
- Ne modifie JAMAIS de fichiers en dehors de `colombina/` et `shared/` (ne touche jamais à `yoru/`, `makima/`, \
`giani/`, `zero-two/`).
- Respecte les conventions déjà en place dans `colombina/` (consulte `colombina/COLOMBINA_REFERENCE.txt` si \
besoin) : convention de préfixes ($ économie, . admin, ! le reste), pattern cogs/services/tests existant, \
migrations Alembic chaînées dans `shared/alembic/versions/`.
- Ajoute des tests pour tout code nouveau, dans le style déjà utilisé dans `colombina/tests/`.
- Mets à jour `colombina/COLOMBINA_REFERENCE.txt` pour documenter la nouvelle fonctionnalité.
- Ne lance ni rebuild ni redeploy toi-même : un processus séparé s'en charge une fois que les tests passent.
- Termine par un résumé bref de ce qui a été fait.

DEMANDE À IMPLÉMENTER (rédigée par une IA à partir d'un entretien avec le demandeur) :
{final_prompt}
"""


def _truncate(text: str, limit: int = OUTPUT_TRUNCATE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_claude(final_prompt: str, cwd: Path = BOT_PARENT_DIR) -> tuple[bool, str]:
    wrapped = CLAUDE_PROMPT_TEMPLATE.format(final_prompt=final_prompt)
    try:
        completed = subprocess.run(
            ["claude", "-p", wrapped, "--dangerously-skip-permissions"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"Timeout Claude Code après {CLAUDE_TIMEOUT_SECONDS}s.\n{exc.stdout or ''}\n{exc.stderr or ''}"
    return completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"


def run_tests(colombina_dir: Path = COLOMBINA_DIR) -> tuple[bool, str]:
    shared_dir = colombina_dir.parent / "shared"
    cmd = (
        f'docker run --rm -v "{colombina_dir}":/app -v "{shared_dir}":/app/shared -w /app python:3.12-slim '
        f'bash -lc "pip install -q -r requirements-dev.txt && python -m pytest -q"'
    )
    try:
        completed = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=TEST_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        return False, f"Timeout tests après {TEST_TIMEOUT_SECONDS}s.\n{exc.stdout or ''}\n{exc.stderr or ''}"
    return completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"


def run_deploy(colombina_dir: Path = COLOMBINA_DIR) -> tuple[bool, str]:
    cmd = "docker compose build bot && docker compose up -d bot"
    try:
        completed = subprocess.run(
            cmd, shell=True, cwd=str(colombina_dir), capture_output=True, text=True, timeout=DEPLOY_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"Timeout déploiement après {DEPLOY_TIMEOUT_SECONDS}s.\n{exc.stdout or ''}\n{exc.stderr or ''}"
    return completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"


def process_job(
    job_path: Path,
    *,
    processing_dir: Path = PROCESSING_DIR,
    done_dir: Path = DONE_DIR,
    failed_dir: Path = FAILED_DIR,
    claude_runner=run_claude,
    test_runner=run_tests,
    deploy_runner=run_deploy,
) -> dict:
    processing_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    processing_path = processing_dir / job_path.name
    job_path.rename(processing_path)
    job = json.loads(processing_path.read_text(encoding="utf-8"))

    result = {
        "id": job["id"],
        "requester_id": job["requester_id"],
        "requester_display": job["requester_display"],
        "guild_id": job["guild_id"],
        "channel_id": job["channel_id"],
        "idea": job["idea"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    claude_ok, claude_output = claude_runner(job["final_prompt"])
    result["claude_output"] = _truncate(claude_output)
    if not claude_ok:
        result.update(success=False, stage="claude")
        return _finish(processing_path, result, done_dir, failed_dir)

    tests_ok, test_output = test_runner()
    result["test_output"] = _truncate(test_output)
    if not tests_ok:
        result.update(success=False, stage="tests")
        return _finish(processing_path, result, done_dir, failed_dir)

    deploy_ok, deploy_output = deploy_runner()
    result["deploy_output"] = _truncate(deploy_output)
    result.update(success=deploy_ok, stage="deploy" if not deploy_ok else "done")
    return _finish(processing_path, result, done_dir, failed_dir)


def _finish(processing_path: Path, result: dict, done_dir: Path, failed_dir: Path) -> dict:
    target_dir = done_dir if result["success"] else failed_dir
    (target_dir / processing_path.name).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    processing_path.unlink()
    return result


def main() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[runner] démarré, surveille {PENDING_DIR}", flush=True)
    while True:
        for job_path in sorted(PENDING_DIR.glob("*.json")):
            print(f"[runner] traitement de {job_path.name}", flush=True)
            try:
                result = process_job(job_path)
                print(
                    f"[runner] terminé : {result['id']} success={result['success']} stage={result['stage']}",
                    flush=True,
                )
            except Exception:
                traceback.print_exc()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
