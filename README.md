TemporalIQ — AI‑Assisted Scheduling and Time‑Blocking Engine

TemporalIQ is an AI‑powered scheduling system that integrates with Notion and iCloud Calendar to intelligently extract tasks, prioritize them, and generate optimized time‑blocks based on user preferences, constraints, and learned behavior.

It combines:

A Flask backend

PostgreSQL for persistence

Redis for caching

Notion API for task extraction

iCloud CalDAV for calendar sync

AI‑assisted ranking and block generation

A React and TypeScript frontend (separate repository)

FEATURES

AI‑Assisted Scheduling

Learns urgency patterns from user behavior

Ranks tasks using NLP, embeddings, heuristics, and due‑date scoring

Generates optimized time‑blocks with constraints

Deep Integrations

Notion: Extracts tasks, pages, and metadata

iCloud Calendar: Reads events, writes generated blocks

User Preferences System

Block size

Max blocks per day

Work hours

Weekend behavior

Time zone

All validated with database‑level constraints

Caching and Performance

Redis‑backed caching for Notion pages, iCloud events, and scheduling results

Clean Architecture

Repository pattern

Service layer

Dependency injection

Domain‑specific error handling

Fully tested with pytest

ARCHITECTURE OVERVIEW

app/
auth/                      Authentication and user management
user_preferences/          Preferences models, repository, service, routes
features/                  AI feature toggles and learning scopes
scheduling/                Task prioritizer, block generator, free time finder
notion/                    Notion extraction engine
icloud/                    CalDAV client manager and event service
repositories/              Base repository abstractions
utils/                     Time zone, exceptions, helpers
main.py                    Flask app entrypoint

Key Architectural Concepts

ServiceFactory wires all services with dependency injection

Repositories encapsulate database access

Services contain business logic

Routes are thin controllers

Models are SQLAlchemy entities

Schemas are Pydantic request and response objects

INSTALLATION

Clone the repository
git clone https://github.com/yourusername/temporalIQ.git (github.com in Bing)
cd temporalIQ

Create a virtual environment
python -m venv .venv
source .venv/bin/activate   (macOS/Linux)
.venv\Scripts\activate      (Windows)

Install dependencies
pip install -r requirements.txt

Create a .env file with:
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
NOTION_API_KEY=...
ICLOUD_USERNAME=...
ICLOUD_PASSWORD=...
SECRET_KEY=...

Run database migrations
alembic upgrade head

Start the server
flask run

TESTING

Run the full test suite:
pytest -q

Tests cover:

User preference endpoints

Repository behavior

Service logic

Integrity constraints

Authorization

Error handling

API ENDPOINTS

POST /user/preferences
Set or update user preferences.

GET /user/preferences/{user_id}
Retrieve preferences for the authenticated user.

POST /schedule/generate
Generate time‑blocks for a user.

GET /notion/pages
Fetch and aggregate Notion pages.

GET /icloud/events
Retrieve iCloud calendar events.

AI COMPONENTS

Task Prioritizer

Due‑date scoring

NLP urgency extraction

Embedding similarity

Learned user behavior

Time‑zone normalization

Time Block Generator

Respects user preferences

Respects work hours

Respects max blocks per day

Avoids existing calendar events

Fills free time windows

Feature Toggles

NLP urgency

Embedding similarity

Heuristic scoring

Learning scopes

ERROR HANDLING

TemporalIQ uses a structured error system:

DatabaseError

ExternalServiceError

UnauthorizedError

ValidationError

UserPreferences has custom integrity error mapping:

Block size must be positive

Max blocks per day must be positive

Work hours must be positive

CONTRIBUTING

Fork the repository

Create a feature branch

Write tests

Submit a pull request
