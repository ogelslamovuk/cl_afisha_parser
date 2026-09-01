# CL Afisha Parser

Локальный Python-парсер расписания Bycard/24afisha для выгрузки афиши в JSON-формате, совместимом со структурой текущего `go2.json`.

Парсер запускается из PyCharm или планировщика Windows через `main.py`, пишет локальные JSON-файлы, обновляет published-файл для GitHub Pages и отправляет краткий Telegram-отчёт.

## Что делает

- Загружает публичный JSON API 24afisha: `/api/v3/pages/objects?jsonld=1`.
- Извлекает события типа `ScreeningEvent`.
- Нормализует данные под структуру `go2.json`.
- Проверяет минимальное количество событий, кинотеатров, дат, обязательные поля, дубликаты `showId` и URL.
- Записывает текущую выгрузку и архив успешных выгрузок.
- Обновляет `docs/data/go2.json`, коммитит и пушит published JSON в `master`.
- Проверяет GitHub Pages deploy через `gh`, если это включено в конфиге.
- Отправляет Telegram-сообщение об успехе, предупреждении валидации или ошибке.

## Fallback источника

Основной источник:

```text
https://api.24afisha.by/api/v3/pages/objects
```

Если API сначала возвращает HTML-страницу `Verification`, клиент забирает краткоживущую cookie `hg-security` и повторяет запрос в той же HTTP-сессии.

Если основной DNS/маршрут падает, клиент пробует резервные IP из `source.fallback_ips`. Подмена DNS действует только внутри процесса парсера: системный `hosts`, браузеры и другие приложения не меняются.

Ответ API читается с лимитом `source.max_response_bytes`, чтобы неожиданный огромный HTML/мусорный ответ не приводил к падению процесса по памяти. Такой ответ считается ошибкой маршрута и даёт шанс fallback.

## Файлы результата

- `output/current/go2.json` — текущая успешная выгрузка.
- `output/current/report.json` — технический отчёт последнего запуска.
- `output/archive/<timestamp>_go2.json` — архивные копии успешных выгрузок.
- `docs/data/go2.json` — файл, публикуемый через GitHub Pages.

Публичный URL:

```text
https://ogelslamovuk.github.io/cl_afisha_parser/data/go2.json
```

## Конфиг

Основной конфиг: `config.yaml`.

Секреты не хранятся в Git. Для локального токена Telegram используй `config.local.yaml`; файл игнорируется Git и автоматически подмешивается поверх `config.yaml`.

Пример:

```yaml
telegram:
  bot_token: "token-from-botfather"
```

Без `config.local.yaml` парсер также может взять токен из переменной окружения, указанной в `telegram.bot_token_env`.

## Запуск

Из корня проекта:

```bash
python main.py
```

Если есть виртуальное окружение:

```bash
.venv\Scripts\python.exe main.py
```

Для планировщика Windows используется:

```text
run_cl_afisha_parser.bat
```

## Тесты

```bash
.venv\Scripts\python.exe -m unittest discover -s tests
```

Тесты покрывают:

- переключение на fallback-IP при сетевой ошибке;
- переключение на fallback-IP при `MemoryError`;
- защиту от слишком большого ответа API;
- применение verification-cookie;
- загрузку всех страниц и удаление дублей `sid`;
- валидацию обязательных полей, URL и дублей;
- локальный override `config.local.yaml`;
- проверку статуса GitHub Pages deploy.

## Ограничения

Скрипт не выполняет покупку билетов, авторизацию, обход капчи или платёжные действия. Он работает только с публично доступными данными афиши.
