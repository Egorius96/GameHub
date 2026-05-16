"""Хитбоксы Pro Racing: машина 120×50 по центру 150×68, камень 70×60 по центру 100×80."""

from app.games.pro_racing.engine import rects_intersect_car_rock
from app.games.pro_racing.models import Entity, PlayerState


def test_car_rock_no_hit_when_visually_side_by_side() -> None:
    car = PlayerState(50, 300)
    rock = Entity(200, 300, 100, 80)
    assert not rects_intersect_car_rock(car, rock)


def test_car_rock_hit_when_overlapping_centers() -> None:
    car = PlayerState(50, 300)
    rock = Entity(80, 310, 100, 80)
    assert rects_intersect_car_rock(car, rock)
