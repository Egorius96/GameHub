"""Детекция комбинаций «три в ряд» и полных рядов/столбцов на поле Team Territory."""

from __future__ import annotations

# (dr, dc) — горизонталь, вертикаль, диагонали
_DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))

LineKey = tuple[str, int]


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
    combo_center_cells: set[int] | None = None,
) -> int:
    """Регистрирует новые тройки после закраски. Возвращает число новых комбо."""
    centers = combo_center_cells if combo_center_cells is not None else set()
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
            center = _center_of_triple(triple, g)
            if center is not None:
                centers.add(center)
            new_count += 1
    return new_count


def _center_of_triple(triple: tuple[int, int, int], g: int) -> int | None:
    """Средняя клетка тройки по линии (для метки 1+1)."""
    if len(triple) != 3:
        return None
    rows = sorted(divmod(c, g)[0] for c in triple)
    cols = sorted(divmod(c, g)[1] for c in triple)
    return rows[1] * g + cols[1]


def _row_cells(row: int, g: int) -> list[int]:
    return [row * g + col for col in range(g)]


def _col_cells(col: int, g: int) -> list[int]:
    return [row * g + col for row in range(g)]


def _line_fully_owned(cells: list[int], indices: list[int]) -> int | None:
    if not indices:
        return None
    team = cells[indices[0]]
    if team < 0:
        return None
    for idx in indices:
        if cells[idx] != team:
            return None
    return team


def _lines_through_cell(row: int, col: int) -> list[LineKey]:
    return [("row", row), ("col", col)]


def register_new_line_combos(
    cells: list[int],
    g: int,
    painted_cells: list[int],
    completed_lines: set[LineKey],
    line_combo_counts: dict[int, int],
    line_combo_cells: set[int],
    combo_cells: set[int],
) -> int:
    """Регистрирует полные ряды/столбцы после закраски. Возвращает число новых line-комбо."""
    new_count = 0
    checked_lines: set[LineKey] = set()
    for cell in painted_cells:
        if not (0 <= cell < len(cells)):
            continue
        row, col = divmod(cell, g)
        for line_key in _lines_through_cell(row, col):
            if line_key in checked_lines:
                continue
            checked_lines.add(line_key)
            if line_key in completed_lines:
                continue
            kind, idx = line_key
            indices = _row_cells(idx, g) if kind == "row" else _col_cells(idx, g)
            team = _line_fully_owned(cells, indices)
            if team is None:
                continue
            completed_lines.add(line_key)
            line_combo_counts[team] = line_combo_counts.get(team, 0) + 1
            line_combo_cells.update(indices)
            combo_cells.update(indices)
            new_count += 1
    return new_count
