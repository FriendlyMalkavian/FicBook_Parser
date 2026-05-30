# ficbook_parser

Скачивает полный текст фанфиков с сайта [ficbook.net](https://ficbook.net).

## Требования

- Python 3.10 или выше
- pip

## Установка

```bash
pip install -r requirements.txt
```

## Использование

```bash
python ficbook_parser.py <URL_или_ID>
```

### Примеры

```bash
# По полной ссылке
python ficbook_parser.py https://ficbook.net/readfic/1081615

# По числовому ID
python ficbook_parser.py 1081615

# С указанием пути для сохранения
python ficbook_parser.py 1081615 -o мой_фанфик.txt

# В формате Markdown
python ficbook_parser.py 1081615 -f md

# В формате JSON
python ficbook_parser.py 1081615 -f json

# В формате EPUB (электронная книга)
python ficbook_parser.py 1081615 -f epub

# В формате FB2 (FictionBook)
python ficbook_parser.py 1081615 -f fb2
```

### Аргументы

| Аргумент | Описание |
|----------|----------|
| `url` | URL фанфика (например, `https://ficbook.net/readfic/1081615`) или числовой/UUID ID |
| `-o, --output` | Путь для сохранения (по умолчанию: `название_фанфика.формат`) |
| `-f, --format` | Формат вывода: `txt` (по умолчанию), `md`, `json`, `epub`, `fb2` |

### Форматы

- **txt** — plain text с разделителями частей и метаданными
- **md** — Markdown с заголовками и форматированием
- **json** — структурированные данные (метаданные + список частей)
- **epub** — электронная книга (EPUB 3, читается на всех устройствах)
- **fb2** — FictionBook 2.0 (популярный формат для русскоязычных читалок)

## Описание

Скрипт загружает главную страницу фанфика, извлекает список всех частей из `<ul class="list-of-fanfic-parts">`, затем загружает каждую часть отдельно и сохраняет весь текст в один UTF-8 файл с метаданными (название, автор, описание, метки).

Поддерживает:
- Фанфики с несколькими частями
- Одночастные фанфики (без списка частей)
- Числовые и UUID идентификаторы
