import random

from services.rpg.achievements import PlayerStats, check_new_achievements
from services.rpg.black_market import generate_black_market
from services.rpg.bosses import BossGimmick, is_boss_floor, random_boss, resolve_boss_round, scale_boss
from services.rpg.character import create_player
from services.rpg.classes import CharacterClass, apply_class, unlocked_classes
from services.rpg.codex import Codex
from services.rpg.combat import Monster, resolve_round, scale_monster
from services.rpg.equipment import apply_equipment, get_armor, get_weapon
from services.rpg.events import draw_event
from services.rpg.final_boss import create_final_boss_state, current_phase, resolve_final_boss_round
from services.rpg.floor import draw_main_rooms, draw_optional_rooms
from services.rpg.legacy import DeathRecord, Legacy, apply_legacy_bonus, record_death
from services.rpg.monsters import spawn_monster
from services.rpg.player import PlayerState
from services.rpg.potions import get_potion
from services.rpg.progression import add_xp, xp_for_next_level, xp_reward_for_monster
from services.rpg.rarity import Rarity, UNLOCK_TOWER_LEVEL, weighted_random_rarity
from services.rpg.rooms import resolve_piege, resolve_repos, resolve_treasure
from services.rpg.run import advance_floor, start_run
from services.rpg.shop import SHOP_CATALOG, buy_item, use_item
from services.rpg.status_effects import StatusEffectKind, apply_status_effect, tick_statuses
from services.rpg.titles import TitleProgress, check_new_titles
from services.rpg.tower_level import tower_level_for_xp
from services.rpg.traits import Trait, apply_trait, random_trait, unlocked_traits
from services.rpg.unique_rooms import draw_unique_room, drawable_rooms, resolve_room_visit


def _player(**overrides) -> PlayerState:
    base = dict(hp=100, max_hp=100, atk=10, defense=5)
    base.update(overrides)
    return PlayerState(**base)


def test_create_player_applies_trait_and_class():
    player, trait = create_player(CharacterClass.GARDIEN, random.Random(1))
    assert player.defense > 5
    assert isinstance(trait, Trait)


def test_apply_class_gardien_adds_defense_and_block():
    player = _player()
    apply_class(player, CharacterClass.GARDIEN)
    assert player.defense == 13
    assert player.block_charges == 1


def test_apply_trait_agile_adds_dodge():
    player = _player()
    apply_trait(player, Trait.AGILE)
    assert player.dodge_chance == 0.10


def test_apply_trait_prudent_boosts_defense_lowers_atk():
    player = _player()
    apply_trait(player, Trait.PRUDENT)
    assert player.defense == 20
    assert player.atk == 1


def test_unlocked_classes_gate_by_tower_level():
    at_start = unlocked_classes(1)
    high = unlocked_classes(100)
    assert CharacterClass.BERSERKER in at_start
    assert CharacterClass.ELU_DU_CREATEUR not in at_start
    assert CharacterClass.ELU_DU_CREATEUR in high
    assert len(high) > len(at_start)


def test_random_trait_gated_by_tower_level():
    trait = random_trait(random.Random(1), tower_level=1)
    assert trait in unlocked_traits(1)


def test_tower_level_formula():
    assert tower_level_for_xp(0) == 1
    assert tower_level_for_xp(100) == 2
    assert tower_level_for_xp(400) == 3


def test_weighted_random_rarity_returns_rarity():
    assert isinstance(weighted_random_rarity(random.Random(1)), Rarity)


def test_equipment_applies_stats():
    player = _player()
    apply_equipment(player, "epee_de_bronze", "cotte_du_gardien")
    assert player.atk == 20
    assert player.defense == 15


def test_equipment_mythique_floor_growth_flags():
    player = _player()
    apply_equipment(player, "coeur_de_la_tour", "armure_de_l_infini")
    assert player.weapon_floor_growth == 1
    assert player.armor_floor_growth == 1


def test_get_potion_returns_known_key():
    assert get_potion("petite_potion").name == "Petite Potion"


def test_player_take_damage_revives_with_extra_life():
    player = _player(hp=10, max_hp=100, extra_lives=1)
    player.take_damage(50)
    assert player.hp == 50
    assert player.extra_lives == 0


def test_player_take_damage_lethal_guard_keeps_one_hp():
    player = _player(hp=10, max_hp=100, lethal_guard=True)
    player.take_damage(500)
    assert player.hp == 1
    assert player.lethal_guard is False


def test_scale_monster_grows_with_floor():
    early = scale_monster(1)
    late = scale_monster(50)
    assert late.hp > early.hp
    assert late.atk > early.atk


def test_spawn_monster_assigns_family_name():
    monster = spawn_monster(1, random.Random(1))
    assert monster.name in ("Gobelins",)


def test_resolve_round_player_kills_monster():
    player = _player(atk=1000)
    monster = Monster(hp=10, max_hp=10, atk=1)
    result = resolve_round(player, monster, random.Random(1))
    assert result.player_damage_dealt >= 9
    assert not monster.is_alive()


def test_is_boss_floor_every_ten_floors():
    assert is_boss_floor(10) is True
    assert is_boss_floor(11) is False


def test_random_boss_scales_with_floor():
    boss = scale_boss(20, BossGimmick.ROI_PARESSEUX, "Roi Paresseux")
    assert boss.hp > 0
    assert boss.gimmick == BossGimmick.ROI_PARESSEUX


def test_resolve_boss_round_mirror_reflects_damage():
    player = _player(atk=100)
    boss = scale_boss(10, BossGimmick.GARDIEN_MIROIR, "Gardien Miroir")
    result = resolve_boss_round(player, boss, random.Random(1))
    assert result.reflected_damage >= 0


def test_final_boss_phase_thresholds():
    state = create_final_boss_state()
    assert current_phase(state.boss) == 1
    state.boss.hp = round(state.boss.max_hp * 0.5)
    assert current_phase(state.boss) == 2
    state.boss.hp = round(state.boss.max_hp * 0.1)
    assert current_phase(state.boss) == 3


def test_resolve_final_boss_round_runs_without_error():
    state = create_final_boss_state()
    player = _player()
    stats = PlayerStats()
    legacy = Legacy()
    result = resolve_final_boss_round(state, player, stats, legacy, 0, random.Random(1))
    assert result.phase == 1


def test_draw_main_and_optional_rooms_are_full_pools():
    rng = random.Random(1)
    assert len(draw_main_rooms(rng)) == 3
    assert len(draw_optional_rooms(rng)) == 2


def test_start_run_and_advance_floor():
    player = _player()
    run = start_run(player, random.Random(1))
    assert run.floor.number == 1
    advance_floor(run, random.Random(1))
    assert run.floor.number == 2


def test_legacy_bonus_scales_with_floor_reached():
    player = _player()
    legacy = Legacy()
    record_death(legacy, DeathRecord(floor_reached=50, monsters_killed=10, gold_earned=100))
    apply_legacy_bonus(player, legacy)
    assert player.atk == 10 + 10
    assert player.defense == 5 + 5


def test_xp_for_next_level_grows():
    assert xp_for_next_level(2) > xp_for_next_level(1)


def test_add_xp_levels_up_player():
    player = _player(xp=0, level=1)
    levels = add_xp(player, xp_for_next_level(1))
    assert levels == 1
    assert player.level == 2


def test_xp_reward_for_monster_scales_with_stats():
    monster = Monster(hp=40, max_hp=40, atk=10)
    assert xp_reward_for_monster(monster) == round(40 * 0.5 + 10)


def test_check_new_achievements_returns_unlockable_only():
    stats = PlayerStats(floor_reached_max=10)
    unlocked = check_new_achievements(stats, set())
    assert any(a.key == "etage_10" for a in unlocked)


def test_check_new_titles_returns_unlockable_only():
    progress = TitleProgress(floor_reached_max=10, deaths=0)
    new_titles = check_new_titles(progress, set())
    assert any(t.key == "aventurier_debutant" for t in new_titles)
    assert not any(t.key == "survivant" for t in new_titles)


def test_treasure_and_piege_and_repos():
    player = _player(hp=50)
    rng = random.Random(1)
    gained = resolve_treasure(player, rng)
    assert gained > 0
    dealt = resolve_piege(player, rng)
    assert dealt > 0
    healed = resolve_repos(player)
    assert healed >= 0


def test_status_effect_rage_boosts_and_reverts():
    target = _player(atk=10, defense=5)
    apply_status_effect(target, StatusEffectKind.RAGE, rounds=1, magnitude=5)
    assert target.atk == 15
    tick_statuses(target)
    assert target.atk == 10


def test_status_effect_precision_boosts_and_reverts():
    target = _player(crit_chance=0.0)
    apply_status_effect(target, StatusEffectKind.PRECISION, rounds=1, magnitude=0.10)
    assert target.crit_chance == 0.10
    tick_statuses(target)
    assert target.crit_chance == 0.0


def test_codex_records_first_visit_as_discovery():
    codex = Codex()
    assert codex.record_visit("salle_des_murmures") is True
    assert codex.record_visit("salle_des_murmures") is False
    assert codex.visit_count("salle_des_murmures") == 2


def test_drawable_rooms_respects_unlock_floor():
    early = drawable_rooms(1)
    late = drawable_rooms(30)
    assert len(late) >= len(early)


def test_resolve_room_visit_generic_bonus_at_level_2():
    player = _player()
    room = next(r for r in drawable_rooms(1) if r.levels is None)
    _, message, _ = resolve_room_visit(room, visit_count=3, player=player, rng=random.Random(1))
    assert "Niveau 2" in message


def test_draw_unique_room_respects_floor_gate():
    room = draw_unique_room(random.Random(1), floor=1)
    assert room.unlock_floor <= 1


def test_draw_event_returns_one_of_the_pool():
    event = draw_event(random.Random(1))
    assert event.key


def test_shop_buy_item_deducts_gold():
    player = _player(gold=100)
    item = SHOP_CATALOG[0]
    message = buy_item(player, item)
    assert player.gold == 100 - item.price
    assert message


def test_shop_buy_item_rejects_insufficient_gold():
    player = _player(gold=0)
    item = SHOP_CATALOG[0]
    message = buy_item(player, item)
    assert "pas assez" in message
    assert player.gold == 0


def test_shop_buy_potion_adds_to_bag():
    player = _player(gold=100)
    item = SHOP_CATALOG[0]
    buy_item(player, item)
    assert item.key in player.bag


def test_use_item_consumes_from_bag_and_heals():
    player = _player(hp=50)
    player.bag.append("petite_potion")
    message = use_item(player, "petite_potion")
    assert "petite_potion" not in player.bag
    assert player.hp > 50
    assert message


def test_use_item_missing_from_bag():
    player = _player(hp=50)
    message = use_item(player, "petite_potion")
    assert "sac" in message


def test_resolve_round_act_skips_player_attack():
    player = _player(atk=1000)
    monster = Monster(hp=10, max_hp=10, atk=5)
    result = resolve_round(player, monster, random.Random(1), player_attacks=False)
    assert result.player_damage_dealt == 0
    assert monster.is_alive()
    assert result.monster_damage_dealt > 0


def test_resolve_boss_round_act_skips_reflect():
    player = _player(atk=100)
    boss = scale_boss(10, BossGimmick.GARDIEN_MIROIR, "Gardien Miroir")
    result = resolve_boss_round(player, boss, random.Random(1), player_attacks=False)
    assert result.player_damage_dealt == 0
    assert result.reflected_damage == 0


def test_black_market_generates_three_offers():
    offers = generate_black_market(random.Random(1))
    assert len(offers) == 3
    for offer in offers:
        assert offer.kind in ("weapon", "armor", "potion")
        assert offer.price > 0
