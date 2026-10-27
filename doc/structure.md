# Структура проекта

Веб-приложение Hotel Fact Agent. В корне две части: `backend/` и `frontend/`. Страница — приложение React на Vite, стили Tailwind. Публичный API — шлюз на порту 8080. Каждый агент — свой каталог внутри `backend/` и позже свой сервис FastAPI. Формулы луча, шума и пешего пути в шлюзе не живут.

Снимок магазинов и ночных клубов читает `search`. `noise` эти файлы не открывает: клуб в шуме — источник у стены отеля, клуб в поиске — куда пойти вечером.

## Как связаны frontend и backend

В разработке страница открывается через Vite (`npm run dev` в `frontend/`, порт 5173). Запросы к `/api` и `/health` Vite пересылает на шлюз `http://127.0.0.1:8080`. Браузер ходит в один origin, шлюз остаётся единственной дверью к агентам.

На защите наружу публикуется только 8080. Шлюз отдаёт собранный фронт (`npm run build`, каталог `frontend/dist`) и тот же API. Отдельный Node-процесс в Compose не нужен. `docker-compose.yml`, `.env.example` и `README.md` лежат в корне репозитория.

## Дерево

```text
ostrovok_hackathon/
  doc/                              # постановка, концепция, архитектура
    structure.md                    # этот файл
  frontend/                         # React + Vite + Tailwind
    index.html
    vite.config.js                  # proxy /api и /health → :8080
    package.json
    src/
      main.jsx
      App.jsx
  backend/
    gateway/                        # Hotel Fact Agent: публичный API, вызов агентов по YAML, :8080
    geo/                            # контур, сторона, азимут, этажность
    view/                           # луч по контурам зданий и сектор утреннего солнца
    noise/                          # класс дороги и ночной POI у стены. Не децибелы и не рекомендация клуба
    mobility/                       # минуты пешком, магистраль, закрытый выход метро
    events/                         # снимок закрытых выходов метро
    hotelier/                       # вопрос и разбор свободного текста
    conflict/                       # два значения, статус unresolved
    search/                         # слоты фразы и фильтр по фактам
    recipes/                        # YAML характеристик
    data/                           # снимки, только чтение для агентов
      hotels.geojson                # три гостиницы, без контуров зданий
      shops.json                    # дневные покупки, Патриаршие и Садовая
      nightclubs.json               # вечерний клуб, отдельно от noise
      base_card.json                # базовая карта: снимок карточки Островка, пока Пекин
  media/pictures/                   # все картинки проекта, схемы перенесены из doc/
    hotel_fact_agent/               # уже есть разбор фразы
      decompose.py
  docker-compose.yml                # следующий шаг, наружу только 8080
  .env.example
  README.md
```

`frontend/src/App.jsx` — поле фразы и дат и разбор ответа. `backend/gateway/main.py` отдаёт `/health`, `/api/search`, карточку отеля, ответ отельера, `/api/walk` и `/api/quality`. Агенты `geo`, `view`, `noise`, `mobility`, `events`, `hotelier`, `conflict`, `search` — модули того же процесса, у каждого свой `service.py` и `main.py`.

## Кто за что отвечает

| Каталог | Что появится здесь |
|---|---|
| `frontend/` | Диалог: пустой ввод гостя, вопросы агента, справа 2–3 отеля, отдельно ответ отельера |
| `backend/gateway/` | `GET /health`, `POST /api/search`, карточка отеля, ответ отельера, один живой пеший путь, метрики. Отдаёт собранный `frontend/dist` |
| `backend/geo/`, `view/`, `noise/`, `mobility/`, `events/` | Свой `GET /health` и один расчёт по рецепту. Наружу порт не публикуется |
| `backend/hotelier/` | Один вопрос и разбор текста в поля категории и стороны |
| `backend/conflict/` | Оба значения факта остаются, ответ отельера строку OSM не удаляет |
| `backend/search/` | Слоты и фильтр. Магазины, клубы и базовую карту берёт из `data/`, не из `noise` |
| `backend/recipes/` | `facade_visibility.yaml` и рецепт без гео-инструмента |
| `backend/data/` | GeoJSON, якоря, граф, факты, метки, `shops.json`, `nightclubs.json`, `base_card.json` |

## Что уже лежит в репозитории

- `backend/data/shops.json` — пять магазинов у Патриарших, дата снимка 2026-10-25.
- `backend/data/nightclubs.json` — Busters в рекомендации, Different помечен закрытым и в выдачу не идёт.
- `backend/data/base_card.json` — базовая карта Пекина, снимок страницы Островка на 2026-10-26. Фраза про базовую информацию отдаёт её и остальные карты не считает.
- `backend/hotel_fact_agent/decompose.py` — делит фразу на отель, экскурсию, покупки и клуб. Экскурсию не строит. При сборке шлюза этот разбор переезжает в `search/`.
- `frontend/` — React, Vite и Tailwind. Прокси `/api` и `/health` смотрит на порт 8080.
- `backend/gateway/main.py` — шлюз. Поиск собирает слоты, якорь из `data/anchors.json`, покупки, клуб и досье по рецептам в `backend/recipes/`.
- `backend/noise/` не открывает `nightclubs.json`. Вечерний клуб остаётся в поиске.
- `backend/view/raycast.py` — луч по контурам. Без `hotels.geojson` и `buildings.geojson` вердикт «не знаем».
- `backend/hotelier/service.py` разбирает свободный текст в категорию, сторону и этаж. `backend/conflict/service.py` хранит оба значения.

## Чего в этом дереве нет

Голос, Telegram, WhatsApp, Celery, Redis, Prometheus. Это этап 2 из `doc/architecture.md`, отдельные каталоги под них не заводим.
