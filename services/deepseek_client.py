import json
from dataclasses import dataclass

import aiohttp

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_VISION_MODEL = "deepseek-v4-flash-vision-exp"
MAX_CLARIFICATION_QUESTIONS = 5

CLARIFICATION_SYSTEM_PROMPT = """Tu es l'assistant qui recueille les demandes de fonctionnalités pour un bot \
Discord nommé Colombina, écrit en Python avec discord.py.

Un membre a proposé une idée de fonctionnalité, déjà validée par les administrateurs du serveur. Ton rôle : \
lui poser au maximum 5 questions de clarification courtes et concrètes (une seule question à la fois) pour \
comprendre précisément comment la fonctionnalité doit se comporter (commande(s) exacte(s), préfixe souhaité, \
ce qui déclenche l'action, cas limites, permissions requises). Ne pose jamais une question déjà répondue.

Dès que tu as assez d'informations (ou qu'on te dit d'arrêter), termine l'entretien et rédige un prompt final \
complet et autonome, en français, destiné à un agent de codage (Claude Code) qui va lire ce prompt SANS avoir vu \
la conversation Discord. Ce prompt doit décrire précisément la fonctionnalité à implémenter, les commandes et \
préfixes attendus, les cas limites mentionnés, et rappeler d'ajouter des tests et de documenter le changement.

Réponds TOUJOURS avec un unique objet JSON, rien d'autre autour, au format exact :
{"done": false, "question": "<ta prochaine question>"}
ou, une fois prêt :
{"done": true, "final_prompt": "<prompt complet pour Claude Code>"}
"""


class DeepSeekError(RuntimeError):
    pass


@dataclass
class ClarificationTurn:
    done: bool
    question: str | None = None
    final_prompt: str | None = None


def _build_messages(idea: str, history: list[tuple[str, str]]) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Idée initiale proposée par un membre : {idea}"},
    ]
    for question, answer in history:
        messages.append(
            {"role": "assistant", "content": json.dumps({"done": False, "question": question}, ensure_ascii=False)}
        )
        messages.append({"role": "user", "content": answer})
    return messages


async def _call_deepseek(
    messages: list[dict[str, str]], api_key: str, *, model: str = DEEPSEEK_MODEL
) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            DEEPSEEK_API_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise DeepSeekError(f"DeepSeek a répondu {response.status} : {body[:300]}")
            data = await response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise DeepSeekError("Réponse DeepSeek inattendue (pas de contenu).") from exc


def _build_judge_content(text: str, images: list[tuple[str, str]] | None) -> str | list[dict]:
    """Construit le contenu du message « user » du juge, en y joignant les images/GIFs.

    Sans image, on garde une simple chaîne (comportement texte historique).
    Avec images, on produit une liste de parties OpenAI (texte + image_url).
    """
    if not images:
        return text
    parts: list[dict] = [{"type": "text", "text": text}]
    for name, url in images:
        parts.append({"type": "text", "text": f"[Image partagée par {name} :]"})
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


async def conduct_clarification_turn(
    idea: str,
    history: list[tuple[str, str]],
    api_key: str,
    force_done: bool = False,
) -> ClarificationTurn:
    messages = _build_messages(idea, history)
    if force_done:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Limite de questions atteinte : arrête de poser des questions et rédige maintenant le "
                    "prompt final complet pour Claude Code avec les informations déjà recueillies."
                ),
            }
        )

    raw = await _call_deepseek(messages, api_key)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeepSeekError("Réponse DeepSeek non-JSON.") from exc

    done = bool(parsed.get("done")) or force_done
    if done:
        final_prompt = parsed.get("final_prompt")
        if not final_prompt:
            raise DeepSeekError("DeepSeek a signalé la fin de l'entretien sans fournir de prompt final.")
        return ClarificationTurn(done=True, final_prompt=final_prompt)

    question = parsed.get("question")
    if not question:
        raise DeepSeekError("DeepSeek n'a fourni ni question ni prompt final.")
    return ClarificationTurn(done=False, question=question)


# --- Juge IA des procès ($proces) ---
# Le règlement du serveur (configurable, services/proces_config.py) est injecté à
# chaque appel dans le bloc « RÈGLES À APPLIQUER » du prompt système, avec les
# notions de jeu RP en complément. Sans règlement configuré, les notions RP seules
# sont fournies (comportement historique).

RP_NOTIONS = (
    "Notions de jeu (RP) complémentaires : vol, braquage, piratage, triche, arnaque, "
    "escroquerie, abus de confiance, mensonge frauduleux et détournement de biens sont "
    "condamnables ; fair-play, honnêteté, entraide et respect sont valorisés."
)


def _rules_block(reglement: str | None) -> str:
    parts = []
    if reglement and reglement.strip():
        parts.append("RÈGLES À APPLIQUER — règlement du serveur (référence principale) :\n" + reglement.strip())
    parts.append(RP_NOTIONS)
    return "\n\n".join(parts)


def _judge_messages(base_prompt: str, user_content: str | list, reglement: str | None) -> list[dict]:
    return [
        {"role": "system", "content": base_prompt + "\n\n" + _rules_block(reglement)},
        {"role": "user", "content": user_content},
    ]


JUDGE_SYSTEM_PROMPT = """Tu es un juge neutre et impartial qui tranche un procès entre deux joueurs d'un serveur Discord de jeu.

Les règles à appliquer te sont fournies dans le bloc « RÈGLES À APPLIQUER » de ton prompt système : le règlement du serveur est la référence principale, complété par des notions de jeu. Qualifie les faits à la lumière de ces règles et cite l'article pertinent (ex. « article 4 ») dans ta raison quand l'accusation correspond à une règle. Un comportement nuisible non listé se juge au regard de l'esprit du règlement.

Un accusateur et un accusé débattent ci-dessous et présentent chacun leurs preuves et arguments. Analyse leurs échanges ainsi que les images fournies en pièce jointe de façon neutre et objective, en te fondant UNIQUEMENT sur ce qui est écrit dans leurs messages et sur le contenu des images, puis tranche.

Cas d'école pour te guider :
- Image/vidéo NSFW, gore ou choquante partagée (pièce jointe) → violation du règlement → coupable.
- Insultes, harcèlement, menaces ou traque répétés (messages ou vocal) → coupable.
- Doxxing ou divulgation d'informations personnelles sans consentement → coupable.
- Vol ou arnaque in-game (RP) avéré → condamnable ; sans preuve (aucune capture, aucun témoignage cohérent) → inconclusif.
- Accusation non étayée (aucune preuve, aucun élément) → inconclusif.
- Gravité et antécédents : à prendre en compte dans ton appréciation des faits, mais tu ne prononces PAS de sanction de modération (avertissement/bannissement) : tu tranches coupable/innocent/inconclusif.

Réponds TOUJOURS avec un unique objet JSON, rien d'autre autour, au format exact :
{"verdict": "coupable" | "innocent" | "inconclusif", "raison": "<explication courte en français, article du règlement concerné si applicable>"}
- "coupable" : l'accusation est fondée et étayée par les preuves (l'accusateur gagne).
- "innocent" : l'accusation est infondée ou l'accusé se disculpe (l'accusé gagne).
- "inconclusif" : preuves insuffisantes pour trancher.
"""


async def judge_trial(
    accusation: str,
    transcript: str,
    api_key: str,
    *,
    images: list[tuple[str, str]] | None = None,
    reglement: str | None = None,
) -> dict:
    """Envoie l'accusation + la transcription (et les images/GIFs) au juge IA.

    `reglement` : texte du règlement du serveur à appliquer (injecté dans le bloc
    « RÈGLES À APPLIQUER » du prompt système).
    """
    text = (
        f"Accusation : {accusation}\n\n"
        f"Échanges (débat entre les deux joueurs) :\n{transcript or '(aucun message)'}"
    )
    messages = _judge_messages(JUDGE_SYSTEM_PROMPT, _build_judge_content(text, images), reglement)
    if images:
        raw = await _call_deepseek(messages, api_key, model=DEEPSEEK_VISION_MODEL)
    else:
        raw = await _call_deepseek(messages, api_key)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeepSeekError("Réponse du juge IA non-JSON.") from exc
    return parsed


JUDGE_ACTIVE_SYSTEM_PROMPT = """Tu es le juge d'un tribunal dans un serveur Discord de jeu (bot Colombina).

Un procès oppose un accusateur et un accusé. Des complices peuvent aussi s'exprimer. Les débats se déroulent dans un fil de discussion. Tu es le troisième protagoniste : tu INTERAGIS avec les parties en français, naturellement, comme un juge qui anime l'audience.

Les règles à appliquer te sont fournies dans le bloc « RÈGLES À APPLIQUER » de ton prompt système : le règlement du serveur est la référence principale, complété par des notions de jeu. Appuie-toi dessus pour orienter tes questions (par exemple vérifier si un article précis a pu être violé, demander les preuves correspondantes).

Ton rôle : poser des questions, demander des preuves, relancer chaque partie, recadrer si besoin. Sois neutre et impartial, fonde-toi sur ce qui est écrit dans la transcription et sur les images fournies en pièce jointe. Ne rends pas de verdict tant que tu n'as pas assez d'éléments.

Si les débats dégénèrent (insultes, provocations, harcèlement, intimidation pendant l'audience), recadre fermement les participants : ces comportements violent le règlement du serveur, même pendant un procès.

Ta parole est absolue : quand tu estimes avoir suffisamment d'éléments pour trancher, tu clores toi-même les débats — tu n'attends l'accord de personne et tu ne demandes pas la permission. Annonce la clôture en une phrase ferme (ex. « J'ai entendu les deux parties. Les débats sont clos. ») sans révéler ton verdict (tu le prononceras juste après), puis mets proposer_cloture à true : le procès se ferme et ta sentence est rendue immédiatement.

Réponds TOUJOURS avec un unique objet JSON, rien d'autre autour, au format exact :
{"reponse": "<ton message de juge, en français>", "proposer_cloture": false}
- "reponse" : ce que tu dis aux participants (question, remarque, relance, annonce de clôture…).
- "proposer_cloture" : true uniquement quand tu décides de clore le procès et de rendre le verdict (décision souveraine, aucun vote des participants).
"""


async def judge_turn(
    accusation: str,
    transcript: str,
    api_key: str,
    *,
    opening: bool = False,
    images: list[tuple[str, str]] | None = None,
    reglement: str | None = None,
) -> dict:
    """Fait parler le juge IA (question/remarque) pendant le procès.

    Retourne {"reponse": str, "proposer_cloture": bool}. `opening=True` pour le
    message d'ouverture du procès (présentation + première question).
    `reglement` : texte du règlement du serveur à appliquer (injecté dans le bloc
    « RÈGLES À APPLIQUER » du prompt système).
    """
    instruction = (
        "C'est le tout début du procès : présente-toi brièvement, rappelle l'accusation "
        "et pose une première question à l'accusé."
        if opening
        else "Poursuis les débats : pose une question ou fais une remarque pertinente "
        "(sans répéter ce que tu viens de dire)."
    )
    text = (
        f"Accusation : {accusation}\n\n"
        f"Transcription des échanges :\n{transcript or '(aucun message pour le moment)'}\n\n"
        f"Consigne : {instruction}"
    )
    messages = _judge_messages(JUDGE_ACTIVE_SYSTEM_PROMPT, _build_judge_content(text, images), reglement)
    if images:
        raw = await _call_deepseek(messages, api_key, model=DEEPSEEK_VISION_MODEL)
    else:
        raw = await _call_deepseek(messages, api_key)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeepSeekError("Réponse du juge IA non-JSON.") from exc
    return {
        "reponse": str(parsed.get("reponse") or "").strip(),
        "proposer_cloture": bool(parsed.get("proposer_cloture")),
    }
