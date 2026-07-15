#!/usr/bin/env python3
"""Минимальная проверка структуры и относительных Markdown-ссылок."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'README.md',
    'LICENSE.md',
    'docs/rpd.md',
    'resources/README.md',
    'team/README.md',
]
LINK_RE = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            errors.append(f'Отсутствует обязательный файл: {rel}')

    md_files = list(ROOT.rglob('*.md'))
    placeholders = 0
    for md in md_files:
        text = md.read_text(encoding='utf-8')
        placeholders += text.count('[ЗАПОЛНИТЬ')
        for raw_target in LINK_RE.findall(text):
            target = raw_target.split('#', 1)[0].strip()
            if not target or target.startswith(('http://', 'https://', 'mailto:')):
                continue
            target_path = (md.parent / unquote(target)).resolve()
            try:
                target_path.relative_to(ROOT.resolve())
            except ValueError:
                warnings.append(f'Ссылка выходит за пределы репозитория: {md.relative_to(ROOT)} -> {target}')
                continue
            if not target_path.exists():
                errors.append(f'Неработающая ссылка: {md.relative_to(ROOT)} -> {target}')

    if placeholders:
        warnings.append(f'Найдено незаполненных маркеров: {placeholders}')

    print(f'Проверено Markdown-файлов: {len(md_files)}')
    for item in warnings:
        print(f'ПРЕДУПРЕЖДЕНИЕ: {item}')
    for item in errors:
        print(f'ОШИБКА: {item}')

    if errors:
        print(f'Проверка завершена с ошибками: {len(errors)}')
        return 1
    print('Структурных ошибок и неработающих локальных ссылок не найдено.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
