# Cardio Digital Twin Template

Готовый шаблон репозитория для тиражирования решения по кардиореабилитации:
- оптимальная кластеризация пациентов,
- модель машинного обучения для каждого класса,
- цифровые двойники с виртуальными экспериментами,
- автоматическая генерация планов реабилитации.

## Структура

- `src/cardio_twin_results_pipeline.py` — основной пайплайн.
- `configs/config.yaml` — пути к данным и папке результатов.
- `data/sample/cardio_sample.csv` — пример входного датасета.
- `docs/updated_architecture_description.md` — обновлённое описание архитектуры.
- `.github/workflows/run-pipeline.yml` — запуск в GitHub Actions.

## Быстрый запуск

```bash
git clone https://github.com/<your-org>/<your-repo>.git
cd <your-repo>
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
python src/cardio_twin_results_pipeline.py --config configs/config.yaml
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python src/cardio_twin_results_pipeline.py --config configs/config.yaml
```

## Входные данные

CSV должен содержать те же поля, что и пример `data/sample/cardio_sample.csv`,
включая целевую переменную `Успех_реабилитации_01`.

## Выходные файлы

В папке `outputs/` формируются:
- `summary.json`
- `twin_simulations.json`
- `rehab_plans.txt`

## Как тиражировать на новую клинику

1. Поместить новый датасет в `data/raw/` (или любую папку).
2. Изменить `data_path` в `configs/config.yaml`.
3. Запустить пайплайн.
4. Проверить `summary.json` и сгенерированные планы.

试运行
