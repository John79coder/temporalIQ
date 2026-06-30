# TemporalIQ Backend

> AI-powered scheduling and time-blocking engine that intelligently extracts tasks from Notion, prioritizes them, and generates optimized time blocks synced with iCloud Calendar.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3-000000?logo=flask)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-4169E1?logo=postgresql)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?logo=redis)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

**TemporalIQ** is an intelligent scheduling system that combines AI with deep integrations to help users manage their time more effectively.

The backend automatically:
- Extracts tasks from Notion databases
- Ranks them using NLP, embeddings, heuristics, and learned user behavior
- Finds available time in the user’s iCloud Calendar
- Generates optimized time blocks while respecting work hours, preferences, and constraints
- Writes the blocks back to the calendar

This repository contains the **Flask backend API** that powers the [TemporalIQ Frontend](https://github.com/John79coder/temporaliq_frontend).

---

## ✨ Key Features

- **AI-Assisted Task Prioritization** — NLP embeddings + heuristics + due-date scoring + learned urgency patterns
- **Smart Time-Block Generation** — Respects user preferences, work hours, max blocks per day, and existing calendar events
- **Deep Notion Integration** — OAuth + intelligent property mapping using AI
- **iCloud Calendar Sync** — Read existing events and write AI-generated time blocks via CalDAV
- **User Preferences System** — Highly configurable (block size, work hours, weekends, timezone, etc.)
- **Secure Authentication** — JWT-based auth with password reset, rate limiting, and CSRF protection
- **Modular & Maintainable Architecture** — Clean separation of concerns with repository pattern

---

## 🛠 Tech Stack

| Category                  | Technology                              | Purpose |
|---------------------------|-----------------------------------------|---------|
| **Web Framework**         | Flask 2.3                               | API & application core |
| **ORM & Migrations**      | SQLAlchemy 2.0 + Alembic (Flask-Migrate)| Database modeling & schema management |
| **Database**              | PostgreSQL                              | Primary data store |
| **Cache / Rate Limiting** | Redis + Flask-Caching + Flask-Limiter   | Performance & abuse protection |
| **Authentication**        | Flask-JWT-Extended + Flask-Login        | Secure JWT & session auth |
| **Integrations**          | `caldav`, `notion-client` (custom)      | iCloud Calendar & Notion |
| **AI / NLP**              | `sentence-transformers`, `transformers`, `spacy`, `openai` | Task ranking, embeddings, smart mapping |
| **Payments**              | Stripe                                  | Premium features & subscriptions |
| **Email**                 | Flask-Mail + SendGrid                   | Transactional emails |
| **Security**              | bcrypt, cryptography, Flask-WTF         | Password hashing, encryption, CSRF |

---

## 📁 Project Structure

```
app/
├── auth/                    # Authentication & user management
├── user_preferences/        # User settings (models, service, routes)
├── features/                # Feature toggles & AI learning scopes
├── scheduling/              # Core intelligence
│   ├── models/
│   ├── routes/
│   └── services/            # Prioritizer, Block Generator, Free Time Finder
├── notion/                  # Notion integration
│   ├── auth/
│   ├── client/
│   ├── smart_mapping/       # AI-powered property mapping
│   ├── models/
│   └── repositories/
├── icloud/                  # iCloud Calendar (CalDAV) integration
├── repositories/            # Base repository abstractions (Repository Pattern)
├── utils/                   # Timezone helpers, exceptions, utilities
├── extensions.py            # Flask extension instances
└── __init__.py              # Application factory (create_app)

migrations/                  # Alembic database migrations
tests/                       # Test suite
config.py                    # Environment-based configuration
main.py                      # Application entrypoint
download_models.py           # Script to download AI models
requirements.txt
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis
- Docker

# 🚀 Getting Started

## Prerequisites

Install the following before getting started:

- Git
- Python 3.11+
- Docker Desktop
- Node.js (optional, for the frontend)

## Installation

Clone the repository and install the Python dependencies:

```bash
git clone https://github.com/John79coder/temporalIQ.git
cd temporalIQ

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt

# Download AI models
python download_models.py
```

## Environment Variables

Create a `.env` file containing the required application secrets and API keys.
Docker-specific configuration is supplied separately through `.env.docker`.

## Build Docker Images

Build the Docker images:

```bash
python docker-builder.py build
```

This only needs to be repeated when Dockerfiles or container dependencies change.

## Start Docker Services

Start all backend services:

```bash
docker compose up -d
```

This starts the Flask backend, PostgreSQL, Redis, and any other required services.

## Apply Database Migrations

Create or update the database schema:

```bash
python docker-builder.py migrate
```

Run this whenever new database migrations are added.

## Start the Frontend

Start the TemporalIQ frontend using its development server (see the frontend repository).
Once the frontend is running, it will connect to the backend running inside Docker.

## Reset the Development Environment

To completely rebuild the development environment, including a fresh PostgreSQL database:

```bash
docker compose down --rmi local -v
python docker-builder.py build
docker compose up -d
python docker-builder.py migrate
```

> **Warning**
> The above command removes all Docker containers, locally built images, and the PostgreSQL data volume. All development data will be permanently deleted.

## Run Tests

```bash
pytest
```

---

## 🏗 Architecture

TemporalIQ follows a **modular, domain-driven design** with clear layering:

- **Application Factory Pattern** (`app/__init__.py`)
- **Repository Pattern** for data access abstraction
- **Service Layer** for business logic (especially in `scheduling/`)
- **Blueprint/Module-based routing** per domain
- **Strong separation** between integrations, core scheduling logic, auth, and preferences

### Core Modules

| Module                | Responsibility |
|-----------------------|----------------|
| `auth`                | User registration, login, JWT, password reset |
| `user_preferences`    | User-configurable scheduling constraints |
| `scheduling`          | Task prioritization, free time detection, block generation |
| `notion`              | Task extraction + AI-powered property mapping |
| `icloud`              | Calendar read/write via CalDAV |
| `features`            | Feature flags & AI learning scopes |
| `repositories`        | Base data access layer |
| `utils`               | Shared helpers (timezones, exceptions, formatting) |

---

## 🤖 AI Components

The "IQ" in TemporalIQ comes from several AI-powered subsystems:

- **Task Prioritizer** — Combines semantic embeddings (`sentence-transformers`), heuristics, due-date scoring, and learned user behavior.
- **Smart Notion Mapping** — Uses NLP to automatically map custom Notion database properties to internal task fields.
- **Behavior Learning** — Tracks user patterns over time to improve future prioritization.
- **Optional LLM support** — OpenAI integration available for advanced reasoning tasks.

---

## 🔗 Frontend Integration

This backend serves a REST/JSON API consumed by the separate [TemporalIQ Frontend](https://github.com/John79coder/temporaliq_frontend) (React + Vite + TypeScript).

Key API domains:
- Authentication
- Onboarding (Notion + Calendar connection)
- Scheduling engine
- User preferences

---

## 🧪 Testing & Quality

- Comprehensive test suite in `tests/`
- Recent improvements around CSRF protection and user preference validation
- Type hints and clean code practices encouraged

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes (follow existing module structure)
4. Run tests and linting
5. Submit a Pull Request

Please open an issue first for major changes.

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Acknowledgments

Built with the goal of helping people reclaim their time through intelligent automation.

---

**TemporalIQ** — *Smarter scheduling. Better days.*
