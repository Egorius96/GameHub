"""Детекция комбинаций «три в ряд» на поле Team Territory."""

from __future__ import annotations

# (dr, dc) — горизонталь, вертикаль, диагонали
_DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _cell_index(row: int, col: int, g: int) -> int:
    return row * g + col


def _in_bounds(row: int, col: int, g: int) -> bool:
    return 0 <= row < g and 0 <= col < g


def triples_through_cell(cells: list[int], g: int, cell: int) -> list[tuple[int, int, int]]:
    """Все завершённые тройки одной команды, проходящие через cell."""
    if not (0 <= cell < len(cells)):
        return []
    team = cells[cell]
    if team < 0:
        return []
    row, col = divmod(cell, g)
    found: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for dr, dc in _DIRECTIONS:
        run: list[int] = [cell]
        r, c = row - dr, col - dc
        while _in_bounds(r, c, g) and cells[_cell_index(r, c, g)] == team:
            run.insert(0, _cell_index(r, c, g))
            r -= dr
            c -= dc
        r, c = row + dr, col + dc
        while _in_bounds(r, c, g) and cells[_cell_index(r, c, g)] == team:
            run.append(_cell_index(r, c, g))
            r += dr
            c += dc
        if len(run) < 3:
            continue
        for i in range(len(run) - 2):
            triple = tuple(sorted(run[i : i + 3]))
            if triple not in seen:
                seen.add(triple)
                found.append(triple)
    return found


def register_new_combos(
    cells: list[int],
    g: int,
    painted_cells: list[int],
    completed_triples: set[tuple[int, int, int]],
    combo_counts: dict[int, int],
    combo_cells: set[int],
) -> int:
    """Регистрирует новые тройки после закраски. Возвращает число новых комбо."""
    new_count = 0
    for cell in painted_cells:
        for triple in triples_through_cell(cells, g, cell):
            if triple in completed_triples:
                continue
            if any(c in combo_cells for c in triple):
                continue
            completed_triples.add(triple)
            team = cells[triple[0]]
            combo_counts[team] = combo_counts.get(team, 0) + 1
            combo_cells.update(triple)
            new_count += 1
    return new_count
