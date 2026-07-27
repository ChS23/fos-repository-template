#!/usr/bin/env python3
"""Расчёт коэффициента трудового участия (КТУ) по формам взаимооценки.

Реализует методику раздела 9 проектной работы: взаимооценка участников,
оценка зоны ответственности и объективные следы работы сводятся в КТУ,
на который умножается командный балл.

Формат входного файла (JSON):

{
  "team": "Команда 1",
  "team_score": 82,
  "members": ["Иванов", "Петрова", "Сидоров", "Кузнецова"],
  "peer_reviews": {
    "Иванов":    {"Петрова": [5,4,5,5], "Сидоров": [4,4,3,4], "Кузнецова": [5,5,5,5]},
    "Петрова":   {"Иванов": [5,5,4,5],  "Сидоров": [3,3,3,4], "Кузнецова": [5,4,5,5]},
    "Сидоров":   {"Иванов": [4,5,4,4],  "Петрова": [5,5,5,5], "Кузнецова": [4,4,4,5]},
    "Кузнецова": {"Иванов": [5,4,5,4],  "Петрова": [5,5,4,5], "Сидоров": [3,4,3,3]}
  },
  "responsibility": {"Иванов": 1.0, "Петрова": 1.1, "Сидоров": 0.9, "Кузнецова": 1.0},
  "objective":      {"Иванов": 1.0, "Петрова": 1.1, "Сидоров": 0.9, "Кузнецова": 1.0},
  "defended":       {"Иванов": true, "Петрова": true, "Сидоров": true, "Кузнецова": true}
}

Оценки взаимооценки — четыре критерия по пятибалльной шкале:
вклад в артефакты, соблюдение сроков, качество рецензирования, взаимодействие.

Запуск:
    python tools/ktu_calc.py peer-review/team-01.json
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

MIN_K, MAX_K = 0.8, 1.2
GAP_THRESHOLD = 0.2


def clamp(value: float) -> float:
    return max(MIN_K, min(MAX_K, value))


def peer_component(reviews: dict, member: str) -> tuple[float, float]:
    """Средний балл участника и коэффициент K1 (крайние оценки отбрасываются)."""
    scores = [statistics.mean(marks)
              for reviewer, given in reviews.items()
              for target, marks in given.items()
              if target == member and reviewer != member]
    if not scores:
        return 3.0, 1.0
    if len(scores) >= 3:
        scores = sorted(scores)[1:-1]
    mean = statistics.mean(scores)
    return mean, clamp(0.8 + 0.1 * (mean - 3))


def main() -> int:
    if len(sys.argv) < 2:
        print("Использование: python tools/ktu_calc.py <файл.json>")
        return 2

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    members = data["members"]
    team_score = data.get("team_score")
    reviews = data.get("peer_reviews", {})
    responsibility = data.get("responsibility", {})
    objective = data.get("objective", {})
    defended = data.get("defended", {})

    print(f"Команда: {data.get('team', '—')}   командный балл: {team_score}")
    print(f"{'Участник':<16}{'B':>5}{'K1':>7}{'K2':>7}{'K3':>7}{'КТУ':>7}{'Балл':>8}  Примечание")
    print("-" * 84)

    warnings: list[str] = []
    for member in members:
        mean, k1 = peer_component(reviews, member)
        k2 = clamp(float(responsibility.get(member, 1.0)))
        k3 = clamp(float(objective.get(member, 1.0)))
        ktu = 0.4 * k1 + 0.4 * k2 + 0.2 * k3

        note = ""
        if not defended.get(member, True):
            ktu = min(ktu, 1.0)
            note = "не защитил зону ответственности: КТУ ограничен 1,0"
        if abs(k1 - k2) > GAP_THRESHOLD:
            warnings.append(f"{member}: расхождение K1 и K2 = {abs(k1 - k2):.2f} — разбирается на защите")

        score = round(team_score * ktu, 1) if team_score is not None else None
        print(f"{member:<16}{mean:>5.2f}{k1:>7.2f}{k2:>7.2f}{k3:>7.2f}{ktu:>7.2f}"
              f"{score if score is not None else '—':>8}  {note}")

    if warnings:
        print("\nТребуют разбора:")
        for warning in warnings:
            print(f"  - {warning}")

    if all(abs(0.4 * peer_component(reviews, m)[1]
               + 0.4 * clamp(float(responsibility.get(m, 1.0)))
               + 0.2 * clamp(float(objective.get(m, 1.0))) - 1.0) < 0.01
           for m in members):
        print("\nВклад участников признан равным: КТУ = 1,0 для всей команды.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
