## ADDED Requirements

### Requirement: Сборка не зависит от внешнего BuildKit frontend
Dockerfile backend MUST NOT задавать внешний BuildKit frontend, если его
инструкции поддерживаются встроенным frontend Docker deployment-сервера.

#### Scenario: Временная DNS-недоступность CDN Docker Hub
- **WHEN** Docker Hub CDN не разрешается DNS во время начала сборки
- **THEN** Docker не пытается получить `docker/dockerfile` только из-за Dockerfile backend

#### Scenario: Сохранение образа приложения
- **WHEN** Docker собирает backend-образ на поддерживаемом Docker deployment-сервере
- **THEN** сохраняются базовый образ, установка зависимостей, entrypoint и команда запуска
