# Модель (вход к КИМ-4.1)

Готовая модель прогнозирования спроса, переданная командой разработки вместе с отчётом о качестве.

| Файл | Содержание |
|---|---|
| `model.pkl` | обученная модель и список признаков (pickle) |
| `features.json` | целевая переменная и признаки модели |
| `team-report.md` | отчёт команды разработки с рекомендацией к внедрению |

## Загрузка

```python
import pickle
import pandas as pd

with open("model.pkl", "rb") as f:
    bundle = pickle.load(f)
model, features = bundle["model"], bundle["features"]

# признаки категориальных колонок закодированы one-hot (store_format_*, category_*)
df = pd.read_csv("../data/sales_test.csv")
X = pd.get_dummies(df, columns=["store_format", "category"])
X = X.reindex(columns=features, fill_value=0)
pred = model.predict(X)
```

## Требования к окружению

Модель сериализована `scikit-learn` версии 1.9. Для загрузки требуются `scikit-learn>=1.9` и `pandas`. Установка через `uv`:

```bash
uv venv --python 3.12
uv pip install scikit-learn pandas
```

## Задание

Отчёт команды (`team-report.md`) рекомендует внедрение. Задача — проверить это утверждение, построить контур проверки (КИМ-4.1) и вынести решение о вводе в эксплуатацию.
