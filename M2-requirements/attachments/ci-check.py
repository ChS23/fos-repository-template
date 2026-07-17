#!/usr/bin/env python3
"""Формальная проверка спецификации требований (КИМ-2.5).

Проверяет формальные признаки, не оценивая содержание:
- уникальность идентификаторов требований;
- наличие обязательных полей у каждого требования;
- отсутствие несвязанных требований в матрице трассируемости;
- наличие декларации использования ИИ.

Запуск: python ci-check.py <каталог работы>
Код возврата 0 — проверка пройдена, 1 — обнаружены нарушения.
"""

import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ("Тип", "Приоритет", "Источник", "Критерий приёмки")
REQ_ID = re.compile(r"^###\s+(REQ-\d+)", re.MULTILINE)


def read_srs(root: Path) -> str:
    srs_dir = root / "srs"
    if not srs_dir.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(srs_dir.glob("*.md")))


def check_requirements(text: str) -> list[str]:
    errors: list[str] = []
    ids = REQ_ID.findall(text)
    seen: set[str] = set()
    for rid in ids:
        if rid in seen:
            errors.append(f"дублируется идентификатор {rid}")
        seen.add(rid)

    blocks = re.split(r"^###\s+REQ-\d+", text, flags=re.MULTILINE)[1:]
    for rid, block in zip(ids, blocks):
        for field in REQUIRED_FIELDS:
            if field not in block:
                errors.append(f"{rid}: отсутствует поле «{field}»")
    if not ids:
        errors.append("не найдено ни одного требования REQ-*")
    return errors


def check_traceability(root: Path, req_ids: set[str]) -> list[str]:
    matrix = root / "traceability.md"
    if not matrix.is_file():
        return ["отсутствует файл traceability.md"]
    text = matrix.read_text(encoding="utf-8")
    traced = set(re.findall(r"REQ-\d+", text))
    orphans = req_ids - traced
    return [f"требование {rid} отсутствует в матрице трассируемости"
            for rid in sorted(orphans)]


def check_ai_disclosure(root: Path) -> list[str]:
    readme = root / "README.md"
    if not readme.is_file():
        return ["отсутствует README.md с декларацией использования ИИ"]
    text = readme.read_text(encoding="utf-8")
    errors: list[str] = []
    if "Декларация использования ИИ" not in text:
        errors.append("в README.md отсутствует раздел декларации использования ИИ")
    if "Не проверено" not in text:
        errors.append("в декларации отсутствует раздел «Не проверено»")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    text = read_srs(root)
    errors = check_requirements(text)
    req_ids = set(REQ_ID.findall(text))
    errors += check_traceability(root, req_ids)
    errors += check_ai_disclosure(root)

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
