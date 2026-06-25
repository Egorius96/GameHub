from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.store import router as store_router
from app.api.leaderboard import router as leaderboard_router
from app.api.presence import router as presence_router
from app.api.tamagochi import router as tamagochi_router
from app.api.users_compat import router as users_compat_router
from app.api.admin import router as admin_router
from app.api.likes import router as likes_router
from app.api.rps import router as rps_router
from app.api.messenger import router as messenger_router
from app.api.game_creators import router as game_creators_router
from app.api.team_territory import router as team_territory_router
from app.api.minecraft_2d_online import router as minecraft_2d_online_router
from app.api.notifications import router as notifications_router
from app.core.config import assert_team_territory_prod_safety
from app.ws.game import router as ws_router
from app.ws.rps_ws import router as ws_rps_router
from app.ws import tamagochi as ws_tamagochi_mod
from app.ws.tamagochi import router as ws_tamagochi_router
from app.ws.team_territory import router as ws_team_territory_router
from app.ws.minecraft_2d_online import router as ws_minecraft_2d_router
from app.ws.messenger_ws import router as ws_messenger_router
from app.games.team_territory.manager import start_team_territory_background_loop, stop_team_territory_background_loop
from app.games.minecraft_2d_online.manager import (
    start_minecraft_2d_background_loop,
    stop_minecraft_2d_background_loop,
)
from app.services.catalog import ensure_catalog_exists
from app.services.bootstrap import ensure_catalog_user
from app.telemetry import request_stats

app = FastAPI(title="GameHub API")


@app.middleware("http")
async def _req_stats_mw(request, call_next):
    try:
        if request_stats.should_track(request.method, request.url.path):
            await request_stats.track(request.method, request.url.path)
    except Exception:
        pass
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(store_router)
app.include_router(leaderboard_router)
app.include_router(presence_router)
app.include_router(tamagochi_router)
app.include_router(users_compat_router)
app.include_router(admin_router)
app.include_router(likes_router)
app.include_router(rps_router)
app.include_router(messenger_router)
app.include_router(game_creators_router)
app.include_router(team_territory_router)
app.include_router(minecraft_2d_online_router)
app.include_router(notifications_router)
app.include_router(ws_router)
app.include_router(ws_rps_router)
app.include_router(ws_tamagochi_router)
app.include_router(ws_team_territory_router)
app.include_router(ws_minecraft_2d_router)
app.include_router(ws_messenger_router)

_tamagochi_pictures = Path(__file__).resolve().parent / "games" / "tamagochi_world" / "pictures"
if _tamagochi_pictures.is_dir():
    app.mount("/tamagochi/pictures", StaticFiles(directory=str(_tamagochi_pictures)), name="tamagochi_pictures")

_avatars_dir = Path(__file__).resolve().parent / "static" / "avatars"
_avatars_dir.mkdir(parents=True, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=str(_avatars_dir)), name="avatars")

_pictures_dir = Path(__file__).resolve().parent / "pictures"
_pictures_dir.mkdir(parents=True, exist_ok=True)
app.mount("/app/pictures", StaticFiles(directory=str(_pictures_dir)), name="app_pictures")

_game_creators_dir = Path(__file__).resolve().parent / "static" / "game_creators"
_game_creators_dir.mkdir(parents=True, exist_ok=True)
app.mount("/game-creators", StaticFiles(directory=str(_game_creators_dir)), name="game_creators")


@app.on_event("startup")
async def _startup() -> None:
    assert_team_territory_prod_safety()
    ensure_catalog_exists()
    ensure_catalog_user()
    ws_tamagochi_mod.start_tamagochi_world_background_loop()
    start_team_territory_background_loop()
    start_minecraft_2d_background_loop()
    request_stats.start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await ws_tamagochi_mod.stop_tamagochi_world_background_loop()
    await stop_team_territory_background_loop()
    await stop_minecraft_2d_background_loop()
    await request_stats.stop()
