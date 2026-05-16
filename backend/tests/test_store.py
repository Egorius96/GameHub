from app.games.pro_racing.engine import GameEngine


def test_drugs_ability_adds_time() -> None:
    engine = GameEngine(mode="normal", car_level=1)
    initial = engine.state.seconds
    engine.ability("drugs")
    assert engine.state.seconds == initial + 10
