# Laundry Monitor documentation / Документация

[English](#english) · [Русский](#русский)

## English

### Users

- [Integration overview, installation and configuration](../README.md#laundry-monitor)
- [User manual (EN)](guides/USER_MANUAL.en.md) — settings, calibration, operation and troubleshooting.
- [User manual (RU)](guides/USER_MANUAL.ru.md)
- [Laundry Monitor Card](https://github.com/undel-gh/Laundry-Monitor-Card) — optional Lovelace card, maintained separately.

### Technical reference (canonical English)

- [Specification](reference/SPECIFICATION.md) — product scope and detection model.
- [Requirements](reference/REQUIREMENTS.md) — functional and non-functional requirements.
- [Architecture](reference/ARCHITECTURE.md) — component responsibilities and data flow.
- [State machine](reference/STATE_MACHINE.md) — states, gates, timers, recovery and invariants.
- [Project map](../PROJECT_MAP.md) — task → documentation → implementation → tests.

### Maintainers and releases

- [Release checklist (EN)](maintainers/RELEASE_CHECKLIST.en.md) — authoritative release procedure.
- [Release checklist (RU)](maintainers/RELEASE_CHECKLIST.ru.md)
- [Changelog](../CHANGELOG.md) and [GitHub Releases](https://github.com/undel-gh/HA-Laundry-Monitor/releases).
- Published notes: 0.1.8 [EN](releases/0.1.8.md) / [RU](releases/0.1.8.ru.md); 0.1.8-rc8 [EN](releases/0.1.8-rc8.md) / [RU](releases/0.1.8-rc8.ru.md).

English documentation remains canonical. Published release-note paths and contents remain unchanged.

To verify repository-local Markdown links before opening a PR, install the parser and run:

```sh
python -m pip install markdown-it-py==4.0.0
python scripts/check_doc_links.py
```

Run from the repository root after staging new Markdown files. The check reads tracked Markdown files, validates local paths and heading fragments, and skips external URLs without network access.

## Русский

### Пользователям

- [Обзор интеграции, установка и настройка](../README.md#мониторинг-стирки)
- [Руководство пользователя (RU)](guides/USER_MANUAL.ru.md) — настройки, калибровка, эксплуатация и устранение неполадок.
- [Руководство пользователя (EN)](guides/USER_MANUAL.en.md)
- [Laundry Monitor Card](https://github.com/undel-gh/Laundry-Monitor-Card) — дополнительная Lovelace-карточка, сопровождается отдельно.

### Технический справочник (канонические документы на английском)

- [Спецификация](reference/SPECIFICATION.md) — назначение, область применения и модель обнаружения.
- [Требования](reference/REQUIREMENTS.md) — функциональные и нефункциональные требования.
- [Архитектура](reference/ARCHITECTURE.md) — компоненты и потоки данных.
- [Конечный автомат](reference/STATE_MACHINE.md) — состояния, условия переходов, таймеры и восстановление.
- [Карта проекта](../PROJECT_MAP.md) — задача → документация → реализация → тесты.

### Сопровождение и релизы

- [Контрольный список релиза (RU)](maintainers/RELEASE_CHECKLIST.ru.md)
- [Контрольный список релиза (EN)](maintainers/RELEASE_CHECKLIST.en.md) — нормативная версия.
- [История изменений](../CHANGELOG.md) и [GitHub Releases](https://github.com/undel-gh/HA-Laundry-Monitor/releases).
- Опубликованные заметки: 0.1.8 [RU](releases/0.1.8.ru.md) / [EN](releases/0.1.8.md); 0.1.8-rc8 [RU](releases/0.1.8-rc8.ru.md) / [EN](releases/0.1.8-rc8.md).

Канонической остаётся английская документация. Пути и содержимое опубликованных заметок о релизах не меняются.

Команда проверки ссылок приведена в [английском разделе](#maintainers-and-releases). Проверка читает отслеживаемые Git Markdown-файлы, проверяет локальные пути и якоря заголовков; внешние URL пропускаются без сетевых запросов.
