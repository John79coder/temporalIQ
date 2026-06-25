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
- Node.js (optional, for frontend)

### Installation

```bash
# Clone the repository
git clone https://github.com/John79coder/temporalIQ.git
cd temporalIQ

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download AI models (sentence-transformers, etc.)
python download_models.py
```

### Environment Variables

Create a `.env` file (or set environment variables):

```env
# Flask
FLASK_SECRET_KEY=your-super-secret-key
ENCRYPTION_KEY=your-fernet-key

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/temporaliq

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET=your-jwt-secret
JWT_EXP_HOURS=24

# Notion OAuth
NOTION_CLIENT_ID=your_notion_client_id
NOTION_CLIENT_SECRET=your_notion_client_secret
NOTION_REDIRECT_URI=http://localhost:5000/notion/callback

# iCloud / Apple
APPLE_CLIENT_ID=your_apple_client_id

# Email (SendGrid)
SENDGRID_API_KEY=your_sendgrid_key
MAIL_DEFAULT_SENDER=no-reply@temporaliq.com

# Stripe (optional)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# AI Models
MODEL_DIR=ai_models_cache
```

### Database Setup

```bash
# Initialize migrations (first time)
flask db init

# Create and apply migrations
flask db migrate -m "Initial migration"
flask db upgrade
```

### Run the Development Server

```bash
python main.py
# or
flask run
```

The API will be available at `http://localhost:5000`.

### Run Tests

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
