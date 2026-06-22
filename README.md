# TemporalIQ — AI‑Assisted Scheduling and Time‑Blocking Engine

**TemporalIQ** is an AI‑powered scheduling system that integrates with Notion and iCloud Calendar to intelligently extract tasks, prioritize them, and generate optimized time‑blocks based on user preferences, constraints, and learned behavior.

## 🛠️ Technology Stack
- **Backend:** Flask
- **Persistence:** PostgreSQL
- **Caching:** Redis
- **Integrations:** Notion API & iCloud CalDAV
- **Frontend:** React & TypeScript (separate repository)
- **Core Logic:** AI‑assisted ranking and block generation

## ✨ Key Features

### AI‑Assisted Scheduling
- Learns urgency patterns from user behavior.
- Ranks tasks using NLP, embeddings, heuristics, and due‑date scoring.
- Generates optimized time‑blocks with strict constraints.

### Deep Integrations
- **Notion:** Extracts tasks, pages, and metadata.
- **iCloud Calendar:** Reads events and writes generated blocks.

### User Preferences System
- Configures block size, max blocks per day, work hours, weekend behavior, and time zones.
- All preferences are validated with database‑level constraints.

## 🏗️ Architecture Overview

```text
app/
├── auth/                 # Authentication and user management
├── user_preferences/     # Preferences models, repository, service, routes
├── features/             # AI feature toggles and learning scopes
├── scheduling/           # Task prioritizer, block generator, free time finder
├── notion/               # Notion extraction engine
├── icloud/               # CalDAV client manager and event service
├── repositories/         # Base repository abstractions
└── utils/                # Time zone, exceptions, helpers
main.py                   # Flask app entrypoint
