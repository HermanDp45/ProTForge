# Protein Design Information System

Дипломный fullstack-проект: информационная система для управления проектами по генерации и анализу 3D-структур белков. Backend на FastAPI, frontend на React, 3D-визуализация через Mol*, генерация структур через внешнюю диффузионную модель **DiMA + SALAD**.

---

## ⚠️ Почему в репозитории нет самой диффузионной модели

В этот репозиторий выложена **только информационная система** (web-приложение). Сама диффузионная модель `DiMA_structure` и SALAD-декодер (`SaladEncoderTraining`) **не публикуются на GitHub** — это закрытый исследовательский код и тяжелые чекпоинты (сотни МБ), которые нельзя выкладывать в открытый доступ.

Информационная система спроектирована так, что диффузия — это **внешний компонент**: backend дергает `DiMA_structure/generate_structure.py` как subprocess через [`backend/integrations/dima_client.py`](backend/integrations/dima_client.py), используя пути и параметры из переменных окружения. Чтобы реально запустить генерацию, нужно отдельно получить:

- репозиторий `DiMA_structure` с `generate_structure.py`;
- репозиторий `SaladEncoderTraining/SaladTraining` (используется как PYTHONPATH);
- три чекпоинта: диффузии, SALAD-декодера и статистик нормализации.

Без них поднимется UI, API, регистрация, проекты и загрузка готовых `.pdb`, но кнопка «сгенерировать» вернет ошибку про незаданные `DIMA_*` переменные. Это ожидаемое поведение.

---

## Что реализовано

- Регистрация и авторизация пользователей (JWT).
- Личный кабинет.
- Проекты: создание, просмотр, редактирование, удаление.
- Внутри проекта:
  - генерация новой структуры по параметрам (длина и т.д.);
  - сценарий «модификации» через параметры генерации;
  - загрузка готового `.pdb`;
  - список структур с метриками (длина, pLDDT, время генерации).
- 3D-визуализация структуры (Mol*-viewer, локальная сборка в `frontend/public/molstar`).
- Хранение пользователей/проектов/структур в SQLite (`app.db`).
- Опционально — асинхронная очередь генерации через Celery + Redis (если их нет, API уходит в синхронный fallback).

---

## Архитектура

```
┌─────────────┐      HTTPS/JSON       ┌──────────────────────────┐
│  Browser    │ ─────────────────────▶│   FastAPI backend        │
│ (React SPA) │ ◀──── JWT, JSON ──────│   /users /projects ...   │
│  + Mol*     │                       │                          │
└─────────────┘                       │  ┌────────────────────┐  │
                                      │  │ SQLAlchemy / SQLite│  │
                                      │  │       app.db       │  │
                                      │  └────────────────────┘  │
                                      │  ┌────────────────────┐  │
                                      │  │  uploads/*.pdb     │  │
                                      │  └────────────────────┘  │
                                      │  ┌────────────────────┐  │
                                      │  │ Celery + Redis     │  │ (опционально)
                                      │  └────────────────────┘  │
                                      └──────────┬───────────────┘
                                                 │ subprocess
                                                 ▼
                                ┌────────────────────────────────┐
                                │  DiMA_structure (внешний репо) │
                                │  generate_structure.py         │
                                │   └─ SALAD structure decoder   │
                                │   └─ checkpoints (.pth / .jax) │
                                └────────────────────────────────┘
```

---

## Стек

- **Frontend:** React + React Router + Axios; Mol* как локальный viewer.
- **Backend:** FastAPI + SQLAlchemy + Pydantic; auth — `python-jose` + `passlib[bcrypt]`.
- **DB:** SQLite (`app.db`), для прод-варианта в `.env` лежит шаблон под PostgreSQL.
- **Очередь (опц.):** Celery + Redis.
- **Интеграция с моделью:** subprocess + переменные окружения `DIMA_*` / `SALAD_ROOT`.

---

## Установка

### 1. Conda/mamba окружение

Рекомендуется ставить через `mamba` — стандартный conda solver на тяжелых CUDA/JAX/PyTorch стэках обычно зависает.

```bash
# создать окружение (имя для удобства — vkr)
mamba create -n vkr python=3.10 -y
conda activate vkr
```

### 2. Backend (Python)

```bash
pip install \
    "fastapi>=0.111,<1.0" \
    "uvicorn[standard]>=0.30,<1.0" \
    "sqlalchemy>=2.0,<3.0" \
    "python-jose[cryptography]>=3.3,<4.0" \
    "passlib[bcrypt]>=1.7,<2.0" \
    "python-multipart>=0.0.9" \
    "pydantic>=2.7,<3.0" \
    "celery>=5.4,<6.0" \
    "redis>=5.0,<6.0" \
    biopython
```

### 3. Frontend (Node.js)

Node ставится тем же conda:

```bash
conda install -c conda-forge nodejs=20 -y
cd frontend
npm install
cd ..
```

### 4. (Только для реальной генерации) DiMA + SALAD

Если у вас есть доступ к `DiMA_structure` и `SaladEncoderTraining`, поставьте дополнительно:

```bash
pip install "torch>=2.0" chex immutabledict ml-collections numpy scipy tqdm \
            pydssp dm-tree flax gemmi matplotlib tensorboard jmp tabulate

# JAX с CUDA 12
pip install "jax[cuda12]==0.5.0" \
    -f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html

pip install "dm-haiku @ git+https://github.com/deepmind/dm-haiku@v0.0.14"
pip install "flexloop @ git+https://github.com/mjendrusch/flexloop.git"

# фикс версий
pip install --no-cache-dir "numpy==1.26.1" "pandas==2.1.2"
pip install "mlflow==2.14.1" "setuptools==69.5.1" wheel
```

---

## Переменные окружения

### Backend (`backend/.env`)

```
DATABASE_URL=sqlite:///./app.db                # или postgresql://user:***@host:5432/db
SECRET_KEY=<сгенерируйте свой>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REDIS_URL=redis://localhost:6379/0
```

### DiMA-интеграция

Чтобы кнопка «сгенерировать» в UI реально вызывала диффузию, нужно прописать переменные. Шаблон лежит в [dima_conda_vars.txt](dima_conda_vars.txt) (пути в файле — пример с конкретной машины, замените на свои):

```
DIMA_REPO_DIR=/path/to/DiMA_structure
DIMA_PYTHON=/path/to/conda/envs/vkr/bin/python
DIMA_GENERATE_SCRIPT=/path/to/DiMA_structure/generate_structure.py

DIMA_STRUCTURE_DECODER_PATH=/path/to/checkpoint-200000.jax
DIMA_STATISTICS_PATH=/path/to/encodings-...-200000.pth
DIMA_STRUCTURE_CONFIG_NAME=eq_dgram_latent_320_nbr_128

DIMA_CHECKPOINTS_PREFIX=dima-salad-ft200k
DIMA_CHECKPOINT_NAME=400000
DIMA_SCHEDULER=cosine
DIMA_N_STEPS=1000
DIMA_BATCH_SIZE=1
DIMA_TIMEOUT_SEC=3600
DIMA_CUDA_VISIBLE_DEVICES=0

SALAD_ROOT=/path/to/SaladEncoderTraining/SaladTraining
PYTHONPATH=/path/to/DiMA_structure:/path/to/SaladEncoderTraining/SaladTraining
HYDRA_FULL_ERROR=1

REDIS_URL=redis://localhost:6379/0
```

Удобный способ — прицепить переменные к conda-окружению, чтобы они подгружались по `conda activate vkr`:

```bash
conda activate vkr

mapfile -t VARS < <(grep -vE '^\s*(#|$)' dima_conda_vars.txt)
conda env config vars set -n vkr "${VARS[@]}"

conda deactivate
conda activate vkr   # переменные теперь активны
```

Без этих переменных backend поднимется, но `POST /projects/{id}/generate-protein-async/` отдаст ошибку `DiMAGenerationError: Environment variable ... is not set`.

---

## Запуск

### Backend

```bash
conda activate vkr
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API: `http://localhost:8000`, OpenAPI-доки: `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm start
```

UI: `http://localhost:3000`.

### Celery worker (опционально, для async генерации)

```bash
redis-server --port 6379
```

```bash
conda activate vkr
celery -A backend.celery_worker.celery worker \
  --loglevel=info \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  -Ofair
```

---

## Полезные эндпоинты

| Метод  | Путь                                                | Назначение                          |
|--------|-----------------------------------------------------|-------------------------------------|
| POST   | `/users/`                                           | регистрация                         |
| POST   | `/token`                                            | вход, выдача JWT                    |
| GET    | `/users/me`                                         | профиль                             |
| GET    | `/projects/`                                        | список проектов пользователя        |
| POST   | `/projects/`                                        | создать проект                      |
| GET    | `/projects/{project_id}`                            | проект                              |
| PUT    | `/projects/{project_id}`                            | обновить                            |
| DELETE | `/projects/{project_id}`                            | удалить                             |
| GET    | `/projects/{project_id}/protein-structures/`        | список структур проекта             |
| POST   | `/projects/{project_id}/generate-protein-async/`    | сгенерировать (через DiMA)          |
| POST   | `/projects/{project_id}/upload-protein/`            | загрузить готовый `.pdb`            |
| GET    | `/protein-structures/{structure_id}`                | структура                           |
| DELETE | `/protein-structures/{structure_id}`                | удалить структуру                   |

---

## Структура репозитория

```
inf_sys_for_prot_gen/
├── backend/
│   ├── main.py                      # FastAPI app + роуты
│   ├── models.py / schemas.py       # SQLAlchemy + Pydantic
│   ├── crud.py / database.py        # доступ к данным
│   ├── auth.py / security.py        # JWT, bcrypt
│   ├── celery_worker.py             # async-таски
│   ├── integrations/dima_client.py  # subprocess-вызов DiMA
│   ├── services/protein_generation.py
│   └── utils.py                     # парсинг PDB, метрики
├── frontend/                        # React SPA + Mol* viewer
├── tools/                           # сборка диплома (docx)
├── uploads/                         # PDB-файлы (не в git)
├── app.db                           # SQLite (локально)
├── dima_conda_vars.txt              # шаблон env-переменных для DiMA
└── README.md
```

---

## Лицензия

См. [LICENSE](LICENSE).
