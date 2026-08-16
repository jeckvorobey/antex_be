## Why

Coolify прекращает сборку до обработки Dockerfile, когда DNS временно не может
разрешить CDN Docker Hub для внешнего BuildKit frontend `docker/dockerfile:1.7`.
Для текущего набора Dockerfile-инструкций этот внешний frontend не требуется.

## What Changes

- Убрать необязательную директиву внешнего BuildKit frontend из Dockerfile backend.
- Сохранить текущий образ Python, порядок установки зависимостей, entrypoint и
  команду запуска без изменений.

## Capabilities

### New Capabilities

- `buildkit-frontend-independent-build`: Docker-сборка backend не требует
  отдельного скачивания frontend с Docker Hub.

### Modified Capabilities

- Нет.

## Impact

- `Dockerfile` backend и деплой Coolify.
- Публичные API, миграции, runtime-конфигурация и зависимости приложения не
  изменяются.
