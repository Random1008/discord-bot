from dataclasses import dataclass, field

from services.rpg.unique_rooms import UNIQUE_ROOMS

DISCOVERY_MESSAGE = "📖 Nouvelle salle découverte !"


@dataclass
class Codex:
    visits: dict[str, int] = field(default_factory=dict)

    def record_visit(self, key: str) -> bool:
        """Records a visit and returns True if this is the first visit (a discovery)."""
        is_first_visit = key not in self.visits
        self.visits[key] = self.visits.get(key, 0) + 1
        return is_first_visit

    def is_discovered(self, key: str) -> bool:
        return key in self.visits

    def visit_count(self, key: str) -> int:
        return self.visits.get(key, 0)

    def discovered_count(self) -> int:
        return len(self.visits)


def render_codex(discovered: dict[str, int]) -> str:
    lines = ["📖 **Codex de la Tour**", ""]
    for room in UNIQUE_ROOMS:
        if room.key in discovered:
            lines.append(f"✅ {room.name}")
        else:
            lines.append("❓ Salle inconnue")
    total_visits = sum(discovered.get(room.key, 0) for room in UNIQUE_ROOMS)
    lines.append("")
    lines.append(f"Salles découvertes : {len(discovered)}/{len(UNIQUE_ROOMS)}")
    lines.append(f"Visites totales : {total_visits}")
    return "\n".join(lines)
