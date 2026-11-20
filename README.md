# Такт BI

Сервис производственной аналитики: вопрос на русском языке, таблица показателей, график и краткий вывод с рекомендациями. Полное задание — в [THEME.md](THEME.md).

## Структура

```
backend/    FastAPI, расчёты по SQLite, LLM-вызовы, графики Matplotlib
frontend/   React + TypeScript + Vite, сборка и раздача через nginx
compose.yaml
.env.example
```

В контейнере `frontend` nginx отдаёт статику и проксирует `/api`, `/docs` и `/openapi.json` в `backend`. Наружу опубликован только порт `8080`.

## Запуск

Нужен Docker с Docker Compose v2.

```bash
docker compose up --build
```

Откройте [http://localhost:8080/](http://localhost:8080/). Первый запуск создаёт учебную базу SQLite в томе `workshop-data`. Без ключа работает демонстрационный режим: вопрос разбирается правилами, расчёты идут через те же SQL-функции.

### Подключение модели

```bash
cp .env.example .env
```

Заполните `.env`:

| Переменная | Значение |
| --- | --- |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` или `https://api.openai.com/v1` |
| `LLM_MODEL` | `openai/gpt-4o-mini` или `gpt-4o-mini` |
| `LLM_API_KEY` | ключ провайдера |

После изменения `.env` пересоздайте контейнеры:

```bash
docker compose up -d --force-recreate
```

Поддерживаются также `OPENAI_API_KEY`, `OPENAI_BASE_URL` и `OPENROUTER_API_KEY`. Провайдер должен поддерживать Chat Completions, `tools` и строгий `response_format.type=json_schema`.

### Обновление

Образы собираются из исходников и не монтируют код внутрь контейнера. Чтобы изменить приложение, пересоберите и разверните новую версию:

```bash
docker compose up --build -d
```

Остановка: `docker compose down`. Удаление базы: `docker compose down -v`.

## API

- `GET /api/config` — режим (`llm` или `demo`) и имя модели.
- `GET /api/health` — готовность сервера.
- `POST /api/chat` — `{"question": "...", "context": {}}`; для уточнения передайте предыдущие `filters` в `context`.
- `POST /api/report` — `{"tool": "plan_shortfalls", "arguments": {"count": 5}, "context": {}}`.

Swagger UI доступен по адресу `http://localhost:8080/docs`.

Ответ содержит `tool`, `mode`, `model`, `filters`, `metric_label`, `unit`, `kpis`, `table`, `series`, `chart`, `facts`, `summary`, `recommendations`. Таблица — это `columns` с ключами, подписями и единицами плюс `rows`; ключи строк совпадают с ключами столбцов. График — PNG в base64.

## Локальная разработка

Backend (Python 3.12):

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/python -m uvicorn app:app --reload --port 8000
```

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev
```

Vite проксирует `/api` на `http://127.0.0.1:8000`. Сборка: `npm run build`.

Тесты:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Данные и расчёты

SQLite хранит 2016 записей: 42 смены по 12 часов на четырёх станках с 29 октября 2026 года 08:00 до 19 ноября 08:00. Линия А — S-101 и S-102, линия Б — S-201 и S-202. Одна запись описывает час одного станка.

- Отклонение от плана: `100 × (выпуск − план) / план`.
- Доля брака: `100 × брак / (годные детали + брак)`.
- Загрузка: `100 × (доступные машино-минуты − простои) / доступные машино-минуты`.
- Сравнение с прошлой неделей: те же станки и часы ровно на семь суток раньше.

Функции для function calling: `shift_summary`, `plan_shortfalls`, `hourly_output`, `machine_ranking`, `compare_week`, `downtime_events`, `defect_breakdown`, `equipment_load`.
