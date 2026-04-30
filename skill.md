# Skill: CL Afisha Parser

## Назначение

Проект собирает расписание публичной афиши Bycard/24afisha и сохраняет его локально в JSON-формате, совместимом по структуре с эталонным `go2.json`.

## Эталон структуры

Эталонный файл: `reference/go2.json`.

Корневой объект должен иметь ключ:

```json
{
  "shows": []
}
```

Каждый элемент `shows[]` должен содержать поля по образцу `go2.json`, насколько они доступны из источника.

Обязательные поля первой итерации:

- `title`
- `genres`
- `images`
- `rating`
- `showId`
- `eventId`
- `showUrl`
- `theatre`
- `category`
- `eventUrl`
- `maxPrice`
- `minPrice`
- `promoter`
- `busySeats`
- `theatreId`
- `updatedAt`
- `seatsCount`
- `description`
- `haveTickets`
- `ratingLabel`
- `dttmShowStart`
- `originalTitle`
- `dtLocalRelease`
- `productionYear`
- `lengthInMinutes`
- `theatreAuditorium`
- `presentationMethod`
- `theatreAuditriumId`
- `theatreAndAuditorium`

Если поле недоступно из Bycard, значение должно быть `null`, `false`, `0` или пустая строка только по явно описанному правилу нормализации. Не выдумывать данные.

## Источник первой итерации

Bycard:

- стартовая страница: `https://bycard.by/objects/minsk/2`
- дополнительные страницы пагинации определять из `window.__NUXT__.data[0].objects.last_page`
- расписание извлекать из `window.__NUXT__.data[0].objects.data[].jsonld[]`
- нужный тип JSON-LD: `ScreeningEvent`
- `sid` брать из URL вида `...?sid=...`
- `showUrl` формировать как `https://saleframe.24afisha.by/?sid={sid}`

## Output

Первая итерация пишет локально:

- `output/current/go2.json`
- `output/current/report.json`
- `output/archive/<timestamp>_go2.json`

## Запуск

Основной запуск:

```bash
python main.py
```

Проект должен запускаться из PyCharm кнопкой Run без обязательных CLI-аргументов.
