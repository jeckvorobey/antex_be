## Context

В Dockerfile явно указан BuildKit frontend `docker/dockerfile:1.7`. BuildKit
скачивает его с Docker Hub ещё до разбора инструкций. На сервере Coolify это
завершается DNS-ошибкой CDN Docker Hub. В Dockerfile нет возможностей, для
которых нужен внешний frontend: используются `FROM`, `WORKDIR`, `RUN`, `ENV`,
`COPY`, `EXPOSE`, `ENTRYPOINT` и `CMD`.

## Goals / Non-Goals

**Goals:**

- Исключить скачивание внешнего frontend Docker Hub на старте сборки.
- Сохранить все runtime-свойства backend-образа.

**Non-Goals:**

- Не менять DNS, Docker daemon или настройки сети deployment-сервера.
- Не обновлять базовый образ, зависимости, entrypoint или переменные окружения.

## Decisions

- Удалить `# syntax=docker/dockerfile:1.7`, чтобы Docker 28 использовал
  встроенный совместимый frontend. Это минимальная правка, поскольку специальные
  Dockerfile-возможности не используются.
- Не заменять Docker Hub на другой удалённый frontend: это сохраняло бы внешнюю
  сетевую зависимость и не устраняло бы класс сбоя.

## Risks / Trade-offs

- [В будущем появятся Dockerfile-возможности, требующие нового frontend] →
  вернуть явно закреплённую директиву вместе с надёжным registry-mirror или
  проверить совместимость в CI.
- [DNS недоступен и для GHCR] → эта правка не устраняет такой независимый
  инфраструктурный сбой; он должен устраняться на deployment-сервере.

## Migration Plan

1. Задеплоить образ с изменённым Dockerfile.
2. Убедиться в логах, что отсутствует шаг `docker.io/docker/dockerfile:1.7`.
3. При несовместимости откатить один коммит Dockerfile.

## Open Questions

- Нет.
