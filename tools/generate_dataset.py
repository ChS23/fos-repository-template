#!/usr/bin/env python3
"""Генератор учебного датасета и модели для КИМ-4.5.

Формирует синтетические данные продаж розничной сети, обучает модель
прогнозирования спроса и готовит отчёт команды разработки. Вид намеренного
дефекта задаётся параметром командной строки, что позволяет подготовить
несколько вариантов задания для разных обучающихся и обновлять их ежегодно.

Виды дефектов:
    none      корректная модель без заложенного дефекта (контрольный вариант);
    drift     дрейф концепции на свежем срезе: изменяется сила влияния
              промоакций, модель систематически ошибается на новых данных;
    subgroup  перекос по подгруппе: одна товарная категория прогнозируется
              заметно хуже прочих, средняя метрика этого не показывает;
    leakage   утечка целевой переменной: в признаки добавляется величина,
              недоступная на момент прогноза;
    shift     смещение обучающей выборки: обучение проводится на периоде
              без промоакций.

Запуск:
    python tools/generate_dataset.py --defect drift --seed 20260717 --out out/

Требования: numpy, pandas, scikit-learn (Python 3.10+).
Установка:  uv venv --python 3.12 && uv pip install numpy pandas scikit-learn
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

FORMATS = ("hyper", "super", "conv", "disc")
FORMAT_BASE = {"hyper": 120, "super": 80, "conv": 40, "disc": 60}
CATEGORIES = [f"cat_{c}" for c in "ABCDEFGH"]
CATEGORY_BASE = dict(zip(CATEGORIES, [1.0, 0.9, 1.3, 0.8, 1.1, 0.7, 1.0, 0.95]))
PRICE = dict(zip(CATEGORIES, [1.5, 2.0, 3.0, 1.2, 2.5, 1.8, 2.2, 1.6]))

TRAIN_END, TEST_END, N_DAYS = 400, 500, 540
VOLATILE_CATEGORY = "cat_C"


def build_frame(rng: np.random.Generator, defect: str) -> pd.DataFrame:
    """Формирует таблицу продаж по дням, магазинам и категориям."""
    noise_level = {c: 0.12 for c in CATEGORIES}
    if defect == "subgroup":
        noise_level[VOLATILE_CATEGORY] = 0.45

    stores = [(f"S{i:02d}", fmt)
              for i, fmt in enumerate([f for f in FORMATS for _ in range(5)], 1)]

    rows = []
    for day in range(N_DAYS):
        dow, month = day % 7, (day // 30) % 12
        season = 1.0 + 0.20 * np.sin(2 * np.pi * day / 365.0)
        weekend = 1.0 + (0.25 if dow >= 5 else 0.0)
        trend = 1.0 + 0.0003 * day
        is_fresh = day >= TEST_END

        promo_rate = 0.10
        if defect == "drift" and is_fresh:
            promo_rate = 0.45
        elif defect == "shift" and day < TRAIN_END:
            promo_rate = 0.0

        promo_coef = 1.7 if (defect == "drift" and is_fresh) else 0.6

        for store_id, fmt in stores:
            for cat in CATEGORIES:
                promo = int(rng.random() < promo_rate)
                base = FORMAT_BASE[fmt] * CATEGORY_BASE[cat] * season * weekend * trend
                sales = max(0.0, base * (1.0 + promo_coef * promo)
                            * rng.normal(1.0, noise_level[cat]))
                row = [day, store_id, fmt, cat, dow, month, promo, round(sales, 2)]
                if defect == "leakage":
                    row.append(round(sales * PRICE[cat] * rng.normal(1.0, 0.02), 2))
                rows.append(row)

    columns = ["day", "store_id", "store_format", "category",
               "dow", "month", "promo_flag", "sales"]
    if defect == "leakage":
        columns.append("revenue_today")
    return pd.DataFrame(rows, columns=columns)


def add_lags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["store_id", "category", "day"])
    grouped = df.groupby(["store_id", "category"], observed=True)["sales"]
    df["lag_7"] = grouped.shift(7)
    df["lag_14"] = grouped.shift(14)
    df["roll_28_mean"] = grouped.shift(1).rolling(28, min_periods=7).mean().reset_index(drop=True)
    return df.dropna().reset_index(drop=True)


def wape(actual: pd.Series, predicted) -> float:
    return float(np.sum(np.abs(actual - predicted)) / np.sum(actual)) * 100


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--defect", default="drift",
                        choices=["none", "drift", "subgroup", "leakage", "shift"],
                        help="вид заложенного дефекта")
    parser.add_argument("--seed", type=int, default=20260717, help="зерно генератора")
    parser.add_argument("--out", default="out", help="каталог выгрузки")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    out = Path(args.out)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "model").mkdir(parents=True, exist_ok=True)

    df = add_lags(build_frame(rng, args.defect))

    encoded = pd.get_dummies(df, columns=["store_format", "category"])
    features = [c for c in encoded.columns
                if c.startswith(("store_format_", "category_"))]
    features += ["dow", "month", "promo_flag", "lag_7", "lag_14", "roll_28_mean"]
    if args.defect == "leakage":
        features.append("revenue_today")

    train = encoded[encoded.day < TRAIN_END]
    test = encoded[(encoded.day >= TRAIN_END) & (encoded.day < TEST_END)]
    fresh = encoded[encoded.day >= TEST_END]

    model = GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=0)
    model.fit(train[features], train["sales"])

    metrics = {
        "defect": args.defect,
        "seed": args.seed,
        "wape_test_model": round(wape(test["sales"], model.predict(test[features])), 1),
        "wape_test_baseline": round(wape(test["sales"], test["roll_28_mean"]), 1),
        "wape_fresh_model": round(wape(fresh["sales"], model.predict(fresh[features])), 1),
        "wape_fresh_baseline": round(wape(fresh["sales"], fresh["roll_28_mean"]), 1),
    }
    volatile = test[test.get(f"category_{VOLATILE_CATEGORY}", pd.Series(dtype=bool)) == 1]
    if len(volatile):
        metrics["wape_test_volatile_category"] = round(
            wape(volatile["sales"], model.predict(volatile[features])), 1)

    columns = ["day", "store_id", "store_format", "category", "dow", "month",
               "promo_flag", "lag_7", "lag_14", "roll_28_mean"]
    if args.defect == "leakage":
        columns.append("revenue_today")
    columns.append("sales")

    df[df.day < TRAIN_END][columns].to_csv(out / "data" / "sales_train.csv", index=False)
    df[(df.day >= TRAIN_END) & (df.day < TEST_END)][columns].to_csv(out / "data" / "sales_test.csv", index=False)
    df[df.day >= TEST_END][columns].to_csv(out / "data" / "sales_fresh.csv", index=False)

    with open(out / "model" / "model.pkl", "wb") as handle:
        pickle.dump({"model": model, "features": features}, handle)
    with open(out / "model" / "features.json", "w", encoding="utf-8") as handle:
        json.dump({"target": "sales", "features_used": features},
                  handle, ensure_ascii=False, indent=2)
    with open(out / "metrics.json", "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"Строк в наборе: {len(df)}. Выгрузка: {out.resolve()}")
    print("Отчёт команды разработки и описание дефекта готовятся преподавателем "
          "и в состав выгрузки не входят.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
