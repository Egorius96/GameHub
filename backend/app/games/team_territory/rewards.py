"""Награды алмазами за матч Team Territory (п. 8–9 GAME_RULES)."""

from __future__ import annotations

from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema
from app.db.models import GameHubUser
from app.db.session import _session_factory
from app.games.team_territory.constants import tt_params
from app.games.team_territory.room_engine import TerritoryRoom
from app.integrations.users_api import sync_diamonds_to_sessions


def grant_match_rewards(room: TerritoryRoom, memory_guard: set[str]) -> None:
    if not room.match_id:
        return
    done_key = f"grant:{room.match_id}"
    if done_key in memory_guard:
        return
    p = tt_params()
    reason = room.finish_reason or ""
    if reason == "stale_idle":
        memory_guard.add(done_key)
        return

    memory_guard.add(done_key)
    db = _session_factory()
    try:
        winners = set(room.winning_team_ids or [])
        for uname, pl in list(room.players.items()):
            if pl.role != "player":
                continue
            ukey = f"{room.match_id}:{uname}"
            if ukey in memory_guard:
                continue
            if pl.team_id not in winners:
                continue
            if pl.ticks_in_match < p.min_ticks_for_reward:
                continue
            u = db.query(GameHubUser).filter(GameHubUser.username == uname).first()
            if u is None:
                continue
            other = ensure_gameshub_schema(u.other_data or {})
            games = other.setdefault("games", {})
            prog = games.setdefault(settings.team_territory_game_key, {})
            if not isinstance(prog, dict):
                prog = {}
                games[settings.team_territory_game_key] = prog
            mr = prog.setdefault("match_rewards", {})
            if not isinstance(mr, dict):
                mr = {}
                prog["match_rewards"] = mr
            if mr.get(room.match_id):
                memory_guard.add(ukey)
                continue
            cur = int(other.get("diamonds", 0))
            other["diamonds"] = cur + p.win_diamonds
            mr[room.match_id] = p.win_diamonds
            if len(mr) > 80:
                for k in list(mr.keys())[:40]:
                    mr.pop(k, None)
            u.other_data = other
            db.commit()
            memory_guard.add(ukey)
            sync_diamonds_to_sessions(uname, int(other["diamonds"]))
    except Exception:
        db.rollback()
        memory_guard.discard(done_key)
    finally:
        db.close()
