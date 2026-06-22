📘 TemporalIQ — AI‑Assisted Scheduling & Time‑Blocking Engine
TemporalIQ is a full‑stack, AI‑powered scheduling system that integrates with Notion and iCloud Calendar to intelligently extract tasks, prioritize them, and generate optimized time‑blocks based on user preferences, constraints, and learned behavior.

It combines:

A Flask backend

PostgreSQL for persistence

Redis for caching

Notion API for task extraction

iCloud CalDAV for calendar sync

AI‑assisted ranking and block generation

A React + TypeScript frontend (not included in this repo)

🚀 Features
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

All validated with DB‑level constraints

Caching & Performance
Redis‑backed caching for Notion pages, iCloud events, and scheduling results

Clean Architecture
Repository pattern

Service layer

Dependency injection

Domain‑specific error handling

Fully tested with pytest

🏗 Architecture Overview
Code
app/
├── auth/                     # Authentication & user management
├── user_preferences/         # Preferences models, repo, service, routes
├── features/                 # AI feature toggles & learning scopes
├── scheduling/               # Task prioritizer, block generator, free time finder
├── notion/                   # Notion extraction engine
├── icloud/                   # CalDAV client manager & event service
├── repositories/             # Base repository abstractions
├── utils/                    # Time zone, exceptions, helpers
└── main.py                   # Flask app entrypoint
Key Architectural Concepts
ServiceFactory wires all services with dependency injection

Repositories encapsulate DB access

Services contain business logic

Routes are thin controllers

Models are SQLAlchemy entities

Schemas are Pydantic request/response objects

⚙️ Installation
1. Clone the repo
bash
git clone https://github.com/yourusername/temporalIQ.git
cd temporalIQ
2. Create a virtual environment
bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
3. Install dependencies
bash
pip install -r requirements.txt
4. Set environment variables
Create .env:

Code
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
NOTION_API_KEY=...
ICLOUD_USERNAME=...
ICLOUD_PASSWORD=...
SECRET_KEY=...
5. Run database migrations
bash
alembic upgrade head
6. Start the server
bash
flask run
🧪 Testing
Run the full test suite:

bash
pytest -q
Tests cover:

User preference endpoints

Repository behavior

Service logic

Integrity constraints

Authorization

Error handling

🔌 API Endpoints
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

🧠 AI Components
Task Prioritizer
Uses:

Due‑date scoring

NLP urgency extraction

Embedding similarity

Learned user behavior

Time‑zone normalization

Time Block Generator
Respects:

User preferences

Work hours

Max blocks per day

Existing calendar events

Free time windows

Feature Toggles
User‑specific AI settings:

NLP urgency

Embedding similarity

Heuristic scoring

Learning scopes

🛡 Error Handling
TemporalIQ uses a structured error system:

DatabaseError

ExternalServiceError

UnauthorizedError

ValidationError

UserPreferences has custom integrity error mapping:

Block size must be positive

Max blocks per day must be positive

Work hours must be positive

🤝 Contributing
Fork the repo

Create a feature branch

Write tests

Submit a PR
