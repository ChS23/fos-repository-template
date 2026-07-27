#!/usr/bin/env python3
"""Валидатор фонда оценочных средств.

Проверяет внутреннюю согласованность репозитория ФОС:

1. относительные Markdown-ссылки разрешаются;
2. отсутствуют незаполненные маркеры шаблона;
3. сумма баллов в рубрике каждого КИМ равна 100;
4. сумма весов оценочных средств в системе оценивания равна 100 %;
5. индикаторы, заявленные в паспорте КИМ, присутствуют в README модуля;
6. индикаторы, заявленные в модели измерения, покрыты паспортами КИМ;
7. шкала перевода баллов одинакова во всех оценочных средствах;
8. часы РПД суммируются в заявленный объём дисциплины.

Запуск:
    python tools/validate_fos.py [корень репозитория]

Код возврата: 0 — нарушений нет, 1 — обнаружены нарушения.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "teacher-private", "from-teacher", "__pycache__", ".venv"}
TEMPLATE_MARKERS = ("[ЗАПОЛНИТЬ]", "[НАЗВАНИЕ", "[ФИО]", "TODO", "FIXME")
INDICATOR = re.compile(r"(?:LC|HPC|PL|BD|ML|AI S|ОПК)-?\s?\d+\.\d+")
SCALE = re.compile(r"Шкала перевода:[^\n]+")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def check(self, ok: bool, message: str) -> None:
        self.checks += 1
        if not ok:
            self.errors.append(message)


def md_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.md")
            if not any(part in SKIP_DIRS for part in p.parts)]


def check_links(root: Path, rep: Report) -> None:
    pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for path in md_files(root):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            link = match.group(2).split("#")[0].strip()
            if not link or link.startswith(("http", "mailto", "<")):
                continue
            target = (path.parent / link).resolve()
            rep.check(target.exists(),
                      f"битая ссылка: {path.relative_to(root)} -> {link}")


def check_markers(root: Path, rep: Report) -> None:
    for path in md_files(root):
        if path.name == "quality-checklist.md":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in TEMPLATE_MARKERS:
            rep.check(marker not in text,
                      f"незаполненный маркер {marker}: {path.relative_to(root)}")


def rubric_total(text: str) -> int | None:
    """Сумма баллов в таблице критериев (строки вида | N | ... | баллы |)."""
    values = re.findall(r"^\|\s*\d+\s*\|.*\|\s*(\d+)\s*\|\s*$", text, re.MULTILINE)
    return sum(int(v) for v in values) if values else None


def check_rubrics(root: Path, rep: Report) -> None:
    targets = list(root.glob("M*/kim-*.md")) + [root / "Project/README.md",
                                                root / "Exam/README.md"]
    for path in targets:
        if not path.exists():
            continue
        total = rubric_total(path.read_text(encoding="utf-8"))
        rep.check(total == 100,
                  f"сумма баллов рубрики не равна 100 ({total}): {path.relative_to(root)}")


def check_weights(root: Path, rep: Report) -> None:
    grading = root / "docs/grading.md"
    if not grading.exists():
        rep.check(False, "отсутствует docs/grading.md")
        return
    weights = [int(w) for w in re.findall(r"\|\s*(\d+)\s*%\s*\|", grading.read_text(encoding="utf-8"))]
    rep.check(sum(weights) == 100,
              f"сумма весов оценочных средств не равна 100 % ({sum(weights)})")


def indicators(text: str) -> set[str]:
    return {i.replace(" ", "").replace("--", "-") for i in INDICATOR.findall(text)}


def check_indicator_coverage(root: Path, rep: Report) -> None:
    for module in sorted(root.glob("M[1-9]*")):
        readme = module / "README.md"
        kims = list(module.glob("kim-*.md"))
        if not readme.exists() or not kims:
            continue
        declared = indicators(readme.read_text(encoding="utf-8"))
        for kim in kims:
            head = kim.read_text(encoding="utf-8").split("## 1.")[0]
            for ind in indicators(head):
                rep.check(ind in declared,
                          f"индикатор {ind} из {kim.name} не заявлен в {module.name}/README.md")


def check_measurement_model(root: Path, rep: Report) -> None:
    readme = root / "README.md"
    if not readme.exists():
        return
    section = readme.read_text(encoding="utf-8").split("## 2. Модель измерения")[-1]
    section = section.split("## 3.")[0]
    model_inds = indicators(section)
    kim_inds: set[str] = set()
    for kim in root.glob("M*/kim-*.md"):
        kim_inds |= indicators(kim.read_text(encoding="utf-8").split("## 1.")[0])
    for path in (root / "Project/README.md", root / "Exam/README.md"):
        if path.exists():
            kim_inds |= indicators(path.read_text(encoding="utf-8").split("## 1.")[0])
    for ind in model_inds:
        rep.check(ind in kim_inds,
                  f"индикатор {ind} из модели измерения не покрыт ни одним КИМ")


def check_scales(root: Path, rep: Report) -> None:
    scales = set()
    for path in list(root.glob("M*/kim-*.md")) + [root / "Project/README.md",
                                                  root / "Exam/README.md"]:
        if not path.exists():
            continue
        found = SCALE.search(path.read_text(encoding="utf-8"))
        if found:
            scales.add(found.group(0).strip())
    rep.check(len(scales) <= 1,
              f"шкалы перевода различаются между оценочными средствами: {len(scales)} вариантов")


def check_hours(root: Path, rep: Report) -> None:
    rpd = root / "docs/rpd.md"
    if not rpd.exists():
        return
    text = rpd.read_text(encoding="utf-8")
    declared = re.search(r"(\d+)\s+академических часа", text)
    total = re.search(r"\*\*Итого:\*\*[^\n]*?(\d+)\s+академических часа", text)
    if declared and total:
        rep.check(declared.group(1) == total.group(1),
                  f"объём в разделе 1 ({declared.group(1)}) не совпадает с итогом структуры ({total.group(1)})")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    rep = Report()

    check_links(root, rep)
    check_markers(root, rep)
    check_rubrics(root, rep)
    check_weights(root, rep)
    check_indicator_coverage(root, rep)
    check_measurement_model(root, rep)
    check_scales(root, rep)
    check_hours(root, rep)

    print(f"Выполнено проверок: {rep.checks}")
    if rep.errors:
        print(f"НАРУШЕНИЙ: {len(rep.errors)}")
        for err in rep.errors:
            print(f"  - {err}")
        return 1
    print("Нарушений не обнаружено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
