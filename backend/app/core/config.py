import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "Pro Racing Web API"
    # legacy (больше не обязателен): раньше тут был отдельный сервис Users API
    users_api_base: str = os.getenv("USERS_API_BASE", "http://localhost:7998/users/")
    # Публичный URL статического дефолтного аватара (раздаётся через /app/pictures/).
    default_avatar_url: str = os.getenv("DEFAULT_AVATAR_URL", "/app/pictures/default_avatar.jpg")
    users_auth_url: str = os.getenv("USERS_AUTH_URL", "http://localhost:7998/users/auth")
    project_name: str = "GamesHub"
    pro_racing_game_key: str = "misha_pro_racing_game"
    rps_game_key: str = "rps_game"
    tamagochi_game_key: str = "tamagochi_world_game"
    team_territory_game_key: str = "team_territory"
    minecraft_2d_online_game_key: str = "minecraft_2d_online"
    """development | production — при production запрещён TEAM_TERRITORY_DEBUG_SOLO_LOBBY."""
    gamehub_env: str = Field(default_factory=lambda: (os.getenv("GAMEHUB_ENV") or "development").strip().lower())
    team_territory_debug_solo_lobby: bool = Field(
        default_factory=lambda: os.getenv("TEAM_TERRITORY_DEBUG_SOLO_LOBBY", "0").strip() == "1"
    )
    # Team Territory (п. 12 GAME_RULES)
    tt_paint_max: int = Field(default_factory=lambda: int(os.getenv("TT_PAINT_MAX", "10")))
    tt_tick_ms: int = Field(default_factory=lambda: int(os.getenv("TT_TICK_MS", "6000")))
    tt_regen_sec: int = Field(default_factory=lambda: int(os.getenv("TT_REGEN_SEC", "45")))
    tt_bundle: int = Field(default_factory=lambda: int(os.getenv("TT_BUNDLE", "3")))
    tt_diamond_cost: int = Field(default_factory=lambda: int(os.getenv("TT_DIAMOND_COST", "2")))
    tt_max_buys_per_match: int = Field(default_factory=lambda: int(os.getenv("TT_MAX_BUYS_PER_MATCH", "2")))
    tt_global_cap_base: int = Field(default_factory=lambda: int(os.getenv("TT_GLOBAL_CAP_BASE", "12")))
    tt_f_n_divisor: int = Field(default_factory=lambda: int(os.getenv("TT_F_N_DIVISOR", "3")))
    tt_f_n_offset: int = Field(default_factory=lambda: int(os.getenv("TT_F_N_OFFSET", "4")))
    tt_max_grid_g: int = Field(default_factory=lambda: int(os.getenv("TEAM_TERRITORY_MAX_GRID_G", "18")))
    tt_match_max_sec: int = Field(default_factory=lambda: int(os.getenv("TT_MATCH_MAX_SEC", "900")))
    tt_match_stall_idle_sec: int = Field(default_factory=lambda: int(os.getenv("TT_MATCH_STALL_IDLE_SEC", "300")))
    tt_match_stall_warn_before_sec: int = Field(default_factory=lambda: int(os.getenv("TT_MATCH_STALL_WARN_BEFORE_SEC", "60")))
    tt_win_diamonds: int = Field(default_factory=lambda: int(os.getenv("TT_WIN_DIAMONDS", "50")))
    tt_loss_diamonds: int = Field(default_factory=lambda: int(os.getenv("TT_LOSS_DIAMONDS", "10")))
    tt_tie_diamonds: int = Field(default_factory=lambda: int(os.getenv("TT_TIE_DIAMONDS", "10")))
    tt_ready_timeout_sec: int = Field(default_factory=lambda: int(os.getenv("TT_READY_TIMEOUT_SEC", "60")))
    tt_min_participants: int = Field(default_factory=lambda: int(os.getenv("TT_MIN_PARTICIPANTS", "2")))
    tt_challenge_problems: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_PROBLEMS", "5")))
    tt_challenge_riddle_sec: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_RIDDLE_SEC", "5")))
    tt_challenge_math_sec: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_MATH_SEC", "7")))
    tt_challenge_sequence_sec: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_SEQUENCE_SEC", "8")))
    tt_combo_bonus_points: int = Field(default_factory=lambda: int(os.getenv("TT_COMBO_BONUS_POINTS", "1")))
    tt_repaint_cost: int = Field(default_factory=lambda: int(os.getenv("TT_REPAINT_COST", "2")))
    tt_opponent_left_grace_sec: int = Field(default_factory=lambda: int(os.getenv("TT_OPPONENT_LEFT_GRACE_SEC", "60")))
    tt_one_sided_idle_sec: int = Field(default_factory=lambda: int(os.getenv("TT_ONE_SIDED_IDLE_SEC", "300")))
    tt_challenge_cooldown_sec: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_COOLDOWN_SEC", "120")))
    tt_challenge_max_paint_start: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_MAX_PAINT_START", "5")))
    tt_challenge_round_gap_sec: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_ROUND_GAP_SEC", "3")))
    tt_challenge_max_per_match: int = Field(default_factory=lambda: int(os.getenv("TT_CHALLENGE_MAX_PER_MATCH", "6")))
    tt_challenge_weight_math: float = Field(default_factory=lambda: float(os.getenv("TT_CHALLENGE_WEIGHT_MATH", "0.34")))
    tt_challenge_weight_spelling: float = Field(
        default_factory=lambda: float(os.getenv("TT_CHALLENGE_WEIGHT_SPELLING", "0.33"))
    )
    tt_challenge_weight_sequence: float = Field(
        default_factory=lambda: float(os.getenv("TT_CHALLENGE_WEIGHT_SEQUENCE", "0.33"))
    )
    tt_challenge_spelling_wordlist: str = Field(
        default_factory=lambda: os.getenv("TT_CHALLENGE_SPELLING_WORDLIST", "").strip()
    )
    tt_hud_ink_poll_sec: float = Field(default_factory=lambda: float(os.getenv("TT_HUD_INK_POLL_SEC", "2.5")))
    tt_min_ticks_for_reward: int = Field(default_factory=lambda: int(os.getenv("TT_MIN_TICKS_FOR_REWARD", "3")))
    tt_lobby_idle_close_sec: int = Field(default_factory=lambda: int(os.getenv("TT_LOBBY_IDLE_CLOSE_SEC", "600")))
    catalog_username: str = "gamehub_catalog"
    catalog_password: str = "gamehub_catalog_password"
    jwt_secret: str = "pro-racing-hardcoded-secret-key"
    jwt_alg: str = "HS256"
    ws_tick_rate: int = 30
    # Пароли «я автор» для редактирования блока создателя в каталоге (пусто = отключено).
    pro_racing_author: str = (os.getenv("PRO_RACING_AUTHOR") or os.getenv("pro_racing_author") or "").strip()
    rps_author: str = (os.getenv("RPS_AUTHOR") or os.getenv("rps_author") or "").strip()
    tamagochi_author: str = (os.getenv("TAMAGOTCHI_AUTHOR") or os.getenv("tamagochi_author") or "").strip()
    team_territory_author: str = (os.getenv("TEAM_TERRITORY_AUTHOR") or os.getenv("team_territory_author") or "").strip()
    minecraft_2d_author: str = (os.getenv("MC2D_AUTHOR") or os.getenv("minecraft_2d_author") or "").strip()


settings = Settings()


def assert_team_territory_prod_safety() -> None:
    """П. 3.1: debug solo в production запрещён."""
    if settings.gamehub_env == "production" and settings.team_territory_debug_solo_lobby:
        raise RuntimeError(
            "TEAM_TERRITORY_DEBUG_SOLO_LOBBY=1 is forbidden when GAMEHUB_ENV=production. "
            "Unset TEAM_TERRITORY_DEBUG_SOLO_LOBBY or change GAMEHUB_ENV."
        )
