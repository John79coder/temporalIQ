TemporalIQ — AI‑Assisted Scheduling and Time‑Blocking EngineTemporalIQ is an AI‑powered scheduling system that integrates with Notion and iCloud Calendar to intelligently extract tasks, prioritize them, and generate optimized time‑blocks based on user preferences, constraints, and learned behavior.🛠️ Technology StackBackend: FlaskPersistence: PostgreSQLCaching: RedisIntegrations: Notion API & iCloud CalDAVFrontend: React & TypeScript (separate repository)Core Logic: AI‑assisted ranking and block generation✨ Key FeaturesAI‑Assisted SchedulingLearns urgency patterns from user behavior.Ranks tasks using NLP, embeddings, heuristics, and due‑date scoring.Generates optimized time‑blocks with strict constraints.Deep IntegrationsNotion: Extracts tasks, pages, and metadata.iCloud Calendar: Reads events and writes generated blocks.User Preferences SystemConfigures block size, max blocks per day, work hours, weekend behavior, and time zones.All preferences are validated with database‑level constraints.Caching and PerformanceRedis‑backed caching for Notion pages, iCloud events, and scheduling results.Clean ArchitectureRepository pattern, service layer, dependency injection, and domain‑specific error handling.Fully tested with pytest.🏗️ Architecture OverviewPlaintextapp/
├── auth/                 # Authentication and user management
├── user_preferences/     # Preferences models, repository, service, routes
├── features/             # AI feature toggles and learning scopes
├── scheduling/           # Task prioritizer, block generator, free time finder
├── notion/               # Notion extraction engine
├── icloud/               # CalDAV client manager and event service
├── repositories/         # Base repository abstractions
└── utils/                # Time zone, exceptions, helpers
main.py                   # Flask app entrypoint
Key Architectural ConceptsServiceFactory: Wires all services using dependency injection.Repositories: Encapsulate database access.Services: Contain core business logic.Routes: Act as thin controllers.Models: SQLAlchemy entities.Schemas: Pydantic request and response objects.🚀 InstallationClone the repository:Bashgit clone https://github.com/yourusername/temporalIQ.git
cd temporalIQ
Create a virtual environment:Bash# macOS/Linux
python -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
Install dependencies:Bashpip install -r requirements.txt
Configure Environment: Create a .env file:Code snippetDATABASE_URL=postgresql://...
REDIS_URL=redis://...
NOTION_API_KEY=...
ICLOUD_USERNAME=...
ICLOUD_PASSWORD=...
SECRET_KEY=...
Initialize Database & Run:Bashalembic upgrade head
flask run
🧪 TestingRun the full test suite with:Bashpytest -q
Tests cover: User preference endpoints, repository behavior, service logic, integrity constraints, authorization, and error handling.🔗 API EndpointsMethodEndpointDescriptionPOST/user/preferencesSet or update user preferences.GET/user/preferences/{user_id}Retrieve preferences for the authenticated user.POST/schedule/generateGenerate time‑blocks for a user.GET/notion/pagesFetch and aggregate Notion pages.GET/icloud/eventsRetrieve iCloud calendar events.🤖 AI Components & LogicTask PrioritizerUtilizes due‑date scoring, NLP urgency extraction, embedding similarity, and learned user behavior.Includes time‑zone normalization.Time Block GeneratorRespects user preferences (work hours, block sizes, daily limits).Avoids conflicts with existing calendar events while filling free time windows.Feature TogglesGranular control over NLP urgency, embedding similarity, heuristic scoring, and learning scopes.⚠️ Error HandlingTemporalIQ uses a structured error system (DatabaseError, ExternalServiceError, UnauthorizedError, ValidationError).User preferences include custom integrity error mapping:Block size must be positive.Max blocks per day must be positive.Work hours must be positive.🤝 ContributingFork the repository.Create a feature branch.Write tests.Submit a pull request
