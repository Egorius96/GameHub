"""Движение Pro Racing: диагональ при одновременном dx и dy."""

from app.games.pro_racing.engine import CAR_SPEED, GameEngine


def test_diagonal_moves_both_axes() -> None:
    engine = GameEngine("normal", car_level=1)
    p = engine.state.player1
    x0, y0 = p.x, p.y
    engine.input_move(1, dx=1, dy=-1)
    engine._move_player(p, 0, 635)
    k = 0.7071067811865476
    assert p.x == x0 + 5 * k
    assert p.y == y0 - CAR_SPEED[1] * k


def test_input_move_legacy_direction() -> None:
    engine = GameEngine("normal", car_level=1)
    engine.input_move(1, "right")
    assert engine.state.player1.move_x == 1
    assert engine.state.player1.move_y == 0
