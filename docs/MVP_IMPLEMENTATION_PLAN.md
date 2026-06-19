# MVP Implementation Plan

## MVP Scope: What We Build First

### Phase 0: Foundation (Week 1)

**Goal:** Get Claude Code terminal accessible via API with basic containerization

#### Phase 0 Deliverables:
1. **Docker Container Setup**
   - Base image: Python 3.11
   - Install Anthropic Claude Code CLI
   - Install FastAPI, Redis, uvicorn
   - Containerization ready for Railway deployment

2. **Session Manager**
   - Manage Claude Code terminal sessions
   - Route messages to/from sessions
   - Persist outputs
   - Simple JSON-based state

3. **Basic API Gateway (FastAPI)**
   ```
   POST /chat
   - Send message to an agent
   - Returns response
   
   POST /agents/create
   - Create new agent instance
   - Returns agent_id
   
   GET /agents
   - List active agents
   
   GET /agents/{agent_id}/outputs
   - Get accumulated outputs from an agent
   ```

4. **Basic Web UI**
   - Simple chat interface
   - Agent list
   - Deploy new agent form
   - Output viewer

**Success Criteria:**
- Can deploy container to Railway
- Can access UI and send messages to a Claude Code session
- Session persists and returns results

---

### Phase 1: Two-Agent Communication (Week 2)

**Goal:** Two agents communicate via message broker in simple ping-pong test

#### Phase 1 Architecture:

```
Redis (Message Broker)
├─ Topics:
│  ├─ agent.architect.output
│  ├─ agent.developer.request
│  ├─ agent.developer.output
│  └─ agent.developer.request
│
├─ Agent Architect (Session 1)
│  ├─ Publishes to: architect.output
│  ├─ Subscribes to: architect.request
│  └─ Message format: {"type": "...", "payload": {...}}
│
└─ Agent Developer (Session 2)
   ├─ Publishes to: developer.output
   ├─ Subscribes to: developer.request
   └─ Listens for architect outputs and responds
```

#### Phase 1 Implementation:

1. **Message Broker Integration**
   - Redis client in orchestrator
   - Publish/subscribe functions
   - Message queue persistence

2. **Service Registry**
   - Simple JSON file tracking agent metadata:
   ```json
   {
     "agents": [
       {
         "id": "architect-001",
         "name": "Architect",
         "status": "running",
         "publishes_to": ["architecture_ready"],
         "subscribes_to": [],
         "api_endpoints": []
       }
     ],
     "topics": [
       {
         "name": "architecture_ready",
         "description": "Architecture design is complete",
         "subscribers": ["developer-001", "security-001"]
       }
     ]
   }
   ```

3. **Agent Communication Protocol**
   - Standard message format
   - Topic subscription/publishing
   - Simple request/response loop

4. **Test Case: Ping-Pong**
   ```
   Agent A: "Hello B, what's your name?"
   ├─ Publishes to: "general.questions"
   
   Agent B: (listens to "general.questions")
   ├─ Receives message
   ├─ Responds: "I'm Agent B"
   └─ Publishes to: "general.answers"
   
   Agent A: (listens to "general.answers")
   ├─ Receives response
   ├─ Acknowledges
   ```

**Success Criteria:**
- Two separate Claude Code sessions running
- Messages flow through Redis pub/sub
- Both agents receive and respond to messages
- Service registry tracks both agents

---

### Phase 2: API Exposure & Tool Use (Week 3)

**Goal:** Agents expose endpoints that other agents can call as tools

#### Phase 2 Architecture:

```
Agent Architect exposes:
├─ POST /design-architecture
│  ├─ Input: requirements (string)
│  ├─ Output: {architecture, decisions, trade_offs}
│  └─ Available as Tool for other agents
│
├─ POST /analyze-scope
│  ├─ Input: project_description
│  └─ Output: {bounded_contexts, sub_projects}
│
└─ Meta: OpenAPI schema published to registry

Agent Developer exposes:
├─ POST /generate-code
│  ├─ Input: specification, architecture
│  └─ Output: {code, file_structure}
│
├─ POST /review-code
│  ├─ Input: code
│  └─ Output: {issues, suggestions, score}
│
└─ Meta: OpenAPI schema published to registry

Registry → Dynamically generates tool definitions for Claude
→ All agents can call any other agent's endpoints directly
```

#### Phase 2 Implementation:

1. **API Endpoint Generator**
   - Each agent exposes HTTP endpoints
   - OpenAPI/JSON schema documentation
   - Returns structured responses

2. **Dynamic Tool Registry**
   - Collect all agent endpoints
   - Generate tool definitions for Claude function_calling
   - Tool invocations route to correct endpoint

3. **Tool Use Integration**
   - Claude prompts include available tools
   - When agent needs help, calls other agent's tool
   - Example: Developer calls Architect.analyze_scope()

**Success Criteria:**
- Agent A has an endpoint with proper schema
- Agent B can discover and call Agent A's endpoint
- Response is properly formatted
- Tool definitions available in Claude prompts

---

### Phase 3: Orchestration & Simple Workflow (Week 4)

**Goal:** Orchestrate a simple multi-agent workflow

#### Phase 3 Workflow Example: "Simple App Builder"

```
USER INPUT:
"Build me a simple TODO app with authentication"

↓

ORCHESTRATOR WORKFLOW:

1. Launch: Architect Agent
   ├─ Input: {"brief": "Simple TODO app with auth"}
   ├─ Architect thinks about architecture
   ├─ Outputs: {architecture.md, decisions.md}
   └─ Publishes: "architecture_ready" → Redis

2. Listen for "architecture_ready" → Launch: Developer Agent
   ├─ Input: Reads architecture from Redis
   ├─ Generates: {code.py, schema.sql, requirements.txt}
   ├─ Outputs: "code_ready" → Redis
   └─ Also: Developer calls Architect.review_architecture()

3. Listen for "code_ready" → Launch: Tester Agent
   ├─ Input: Reads code
   ├─ Generates: {tests.py, test_results.json}
   ├─ Outputs: "tests_complete" → Redis
   └─ Publishes test coverage %

4. Listen for "tests_complete" → Launch: Documentation Agent
   ├─ Input: All outputs so far
   ├─ Generates: {README.md, API.md, SETUP.md}
   └─ Outputs: "documentation_ready"

↓

FINAL OUTPUTS:
├─ /architecture/design.md
├─ /code/app.py
├─ /tests/test_app.py
├─ /docs/README.md
├─ results.json (metrics)
└─ status: "COMPLETE"
```

#### Phase 3 Implementation:

1. **Workflow Orchestrator**
   - Defines phases (sequential or parallel)
   - Triggers agents based on events
   - Manages state transitions

2. **State Management**
   - JSON-based workflow state
   - Track which phases completed
   - Store outputs from each phase

3. **Simple Workflow File**
   ```yaml
   workflow: "simple_app_builder"
   phases:
     - phase: 1
       name: "Architect"
       trigger: "start"
       agent: "architect"
       input: "{brief}"
       wait_for: "architecture_ready"
     
     - phase: 2
       name: "Developer"
       trigger: "architecture_ready"
       agent: "developer"
       inputs: ["architecture.md"]
       parallel_with: ["tester"]
       wait_for: "code_ready"
     
     - phase: 3
       name: "Tester"
       trigger: "code_ready"
       agent: "tester"
       inputs: ["code.py"]
       wait_for: "tests_complete"
     
     - phase: 4
       name: "Documentation"
       trigger: ["code_ready", "tests_complete"]
       agent: "documentation"
       inputs: ["all"]
       wait_for: "done"
   ```

**Success Criteria:**
- Orchestrator can run simple 4-phase workflow
- Each phase waits for previous to complete
- Outputs from each phase accessible
- User can see workflow progress via GUI

---

## Technical Stack

### Backend
- **Language:** Python 3.11
- **API Framework:** FastAPI
- **Message Broker:** Redis (simple pub/sub)
- **Containerization:** Docker
- **Deployment:** Railway
- **LLM:** Anthropic Claude (via your account)

### Frontend
- **Framework:** React/Vue (simple SPA)
- **Styling:** Tailwind CSS
- **Communication:** WebSocket for real-time updates, HTTP for API calls

### Infrastructure
- **Container:** Docker
- **Orchestration:** Docker Compose (for local), Railway (for prod)
- **Storage:** Local JSON files (Phase 0-1), PostgreSQL (Phase 2+)

### Directory Structure

```
agent-platform/
├─ backend/
│  ├─ api/
│  │  ├─ gateway.py (FastAPI app)
│  │  ├─ routes.py (API endpoints)
│  │  └─ websocket.py (WebSocket handling)
│  ├─ core/
│  │  ├─ session_manager.py
│  │  ├─ message_broker.py
│  │  ├─ service_registry.py
│  │  ├─ orchestrator.py
│  │  └─ agent_communicator.py
│  ├─ models/
│  │  ├─ agent.py
│  │  ├─ message.py
│  │  └─ workflow.py
│  ├─ docker-compose.yml
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ components/
│  │  ├─ pages/
│  │  ├─ services/
│  │  └─ App.jsx
│  └─ package.json
├─ agents/
│  ├─ architect/
│  │  ├─ directives.md
│  │  └─ prompt.md
│  ├─ developer/
│  │  ├─ directives.md
│  │  └─ prompt.md
│  └─ [other agents]
├─ workflows/
│  ├─ simple_app_builder.yaml
│  └─ portfolio_optimizer.yaml
├─ docker-compose.yml
├─ Dockerfile
└─ README.md
```

## Deployment Plan

### Local Development
```bash
docker-compose up
# Starts Redis, FastAPI backend, React frontend
# Accessible at: http://localhost:3000
```

### Railway Deployment
1. Push to GitHub
2. Connect Railway to repo
3. Configure environment variables (Anthropic API key)
4. Deploy container
5. Set up Redis add-on
6. Expose public URL

