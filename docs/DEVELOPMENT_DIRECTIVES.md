# Development Directives & Code Quality Standards

## Core Directives for Claude Code

### 1. Code Organization

**Do:**
- Create modular, reusable components
- Separate concerns (API routes, business logic, data access)
- Use type hints (Python typing)
- Document complex functions with docstrings
- Follow naming conventions: snake_case for functions/variables, PascalCase for classes

**Don't:**
- Hardcode configuration (use environment variables)
- Mix business logic with API routes
- Create god classes or mega functions
- Skip error handling
- Leave debugging code or print statements

### 2. API Design

**Do:**
- Use RESTful principles for basic CRUD
- Return consistent JSON responses
- Use proper HTTP status codes (200, 201, 400, 404, 500)
- Document endpoints with docstrings
- Validate input before processing

**Response Format:**
```python
# Success
{
  "status": "success",
  "data": {...},
  "timestamp": "2026-06-18T10:00:00Z"
}

# Error
{
  "status": "error",
  "error": "Descriptive error message",
  "code": "ERROR_CODE",
  "timestamp": "2026-06-18T10:00:00Z"
}
```

### 3. Message Protocol

**Standard Message Format:**
```json
{
  "id": "msg-uuid-12345",
  "timestamp": "2026-06-18T10:00:00Z",
  "sender": "architect-001",
  "type": "event",
  "topic": "architecture_ready",
  "payload": {
    "content": "...",
    "metadata": {}
  },
  "version": "1.0"
}
```

### 4. Service Registry Format

**Agent Metadata when registering:**
```json
{
  "agent_id": "developer-001",
  "name": "Developer",
  "status": "active",
  "role": "Code Implementation",
  "publishes_topics": ["code_ready", "code_error", "code_review_requested"],
  "subscribes_topics": ["architecture_ready", "refactor_requested"],
  "api_endpoints": [
    {
      "path": "/generate-code",
      "method": "POST",
      "description": "Generate code from specification",
      "input_schema": {
        "specification": "string",
        "architecture": "object"
      },
      "output_schema": {
        "code": "string",
        "files": ["filename"],
        "explanation": "string"
      }
    }
  ],
  "directives": "Follow SOLID principles, avoid hardcoded values, comprehensive logging",
  "version": "1.0"
}
```

### 5. Error Handling

**Do:**
- Use try/except blocks for external calls
- Log errors with context
- Return meaningful error messages
- Handle timeouts and retries
- Gracefully degrade if a service is down

**Pattern:**
```python
try:
    result = risky_operation()
except TimeoutError:
    logger.error("Operation timed out", extra={"context": "..."})
    return {"status": "error", "code": "TIMEOUT", "retry": True}
except Exception as e:
    logger.error(f"Unexpected error: {str(e)}")
    return {"status": "error", "code": "INTERNAL_ERROR"}
```

### 6. Testing Requirements

**For each new component:**
- Write unit tests (test core logic in isolation)
- Write integration tests (test components working together)
- Aim for 80%+ code coverage
- Test happy path AND error cases
- Test with realistic data

**Example:**
```python
# tests/test_session_manager.py
def test_create_session():
    sm = SessionManager()
    session_id = sm.create_session("test-agent")
    assert session_id is not None
    assert sm.get_session(session_id) is not None

def test_send_message_to_nonexistent_session():
    sm = SessionManager()
    result = sm.send_message("nonexistent", "hello")
    assert result["status"] == "error"
```

### 7. Documentation

**For each file:**
- Module docstring at the top explaining purpose
- Function docstrings with Args, Returns, Raises

**For each component:**
- README.md explaining what it does
- Example usage

**Pattern:**
```python
"""
session_manager.py
Manages Claude Code terminal sessions, routing messages,
and collecting outputs.
"""

def create_session(agent_name: str) -> str:
    """
    Create a new Claude Code terminal session.
    
    Args:
        agent_name: Name of the agent
    
    Returns:
        session_id: Unique session identifier
    
    Raises:
        RuntimeError: If session creation fails
    """
```

### 8. Logging

**Do:**
- Log all significant operations
- Include context (agent_id, session_id, etc.)
- Use appropriate log levels: DEBUG, INFO, WARNING, ERROR
- Structured logging (JSON format for prod)

**Pattern:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Agent started", extra={
    "agent_id": agent_id,
    "role": "Developer"
})
```

### 9. Performance Considerations

**Do:**
- Cache repeated API calls
- Use async/await for I/O operations
- Batch operations when possible
- Monitor response times

**Don't:**
- Call APIs in loops (batch instead)
- Load entire files into memory (stream)
- Block operations (use async)

### 10. Security

**Do:**
- Never hardcode secrets (use env vars)
- Validate all inputs
- Use parameterized queries if using SQL
- Sanitize outputs
- Rate limit API endpoints
- Log security-relevant events

**Don't:**
- Store passwords in plaintext
- Trust user input
- Expose stack traces in error responses
- Log sensitive data

---

## Success Criteria for Each Phase

### Phase 0: Foundation ✅

**Code:**
- [ ] Docker container builds and runs locally
- [ ] FastAPI server starts without errors
- [ ] Base endpoints return correct responses
- [ ] Session Manager creates and manages sessions
- [ ] Can send message to Claude Code and get response back

**Deployment:**
- [ ] Container deployable to Railway
- [ ] Environment variables correctly configured
- [ ] API accessible via public URL

**Testing:**
- [ ] All Session Manager methods have unit tests
- [ ] API endpoints tested with mocked sessions
- [ ] 80%+ code coverage

**Documentation:**
- [ ] README.md with setup instructions
- [ ] API endpoints documented
- [ ] Architecture diagram

**Quality Checks:**
- [ ] No hardcoded secrets
- [ ] No print() statements (use logging)
- [ ] All functions documented
- [ ] Code passes linting (black, flake8)

---

### Phase 1: Two-Agent Communication ✅

**Code:**
- [ ] Redis integration working
- [ ] Message publish/subscribe functioning
- [ ] Service Registry tracking agents
- [ ] Agents can publish and subscribe to topics
- [ ] Message broker persists messages

**Workflow:**
- [ ] Architect Agent publishes "greeting"
- [ ] Developer Agent subscribes to "greeting"
- [ ] Developer receives message and responds
- [ ] Response flows back through broker
- [ ] All messages logged and trackable

**Testing:**
- [ ] Test message publish/subscribe
- [ ] Test agent registration/discovery
- [ ] Test message persistence
- [ ] Test with 10 concurrent messages

**Documentation:**
- [ ] Message protocol documented
- [ ] Agent registration format specified
- [ ] Workflow diagram showing communication flow

**Quality:**
- [ ] All new methods tested (80%+ coverage)
- [ ] No message loss (verify persistence)
- [ ] Graceful error handling
- [ ] Proper logging of all events

---

### Phase 2: API Exposure & Tool Use ✅

**Code:**
- [ ] Each agent exposes HTTP endpoints
- [ ] Endpoints have OpenAPI/JSON schema
- [ ] Service Registry includes endpoint definitions
- [ ] Tool definitions generated from endpoint schemas
- [ ] Claude prompt includes available tools

**Workflow:**
- [ ] Developer calls Architect endpoint directly
- [ ] Request properly routed
- [ ] Response properly formatted
- [ ] Tool use invocations work in Claude prompts

**Testing:**
- [ ] Test endpoint discovery
- [ ] Test tool definition generation
- [ ] Test tool invocation routing
- [ ] Test with multiple agents

**Documentation:**
- [ ] OpenAPI schema per agent
- [ ] Tool definition format documented
- [ ] Example tool invocation documented

**Quality:**
- [ ] All endpoints return consistent format
- [ ] Proper error handling
- [ ] Input validation on all endpoints
- [ ] Schema validation

---

### Phase 3: Orchestration & Simple Workflow ✅

**Code:**
- [ ] Workflow orchestrator implemented
- [ ] YAML workflow files parse correctly
- [ ] Phase transitions work (sequential)
- [ ] State management persists workflow state
- [ ] User can track workflow progress

**Workflow:**
- [ ] "Simple TODO App" workflow completes
- [ ] 4 phases execute in order
- [ ] Outputs from each phase accessible
- [ ] GUI shows real-time progress

**Testing:**
- [ ] Test workflow orchestration
- [ ] Test phase transitions
- [ ] Test state persistence
- [ ] Test workflow with errors (one phase fails)
- [ ] End-to-end test of complete workflow

**Documentation:**
- [ ] Workflow file format documented
- [ ] Orchestration flow diagrammed
- [ ] Example workflow files included

**Quality:**
- [ ] No hardcoded phase logic
- [ ] Proper error recovery
- [ ] All workflow state persisted
- [ ] Comprehensive logging

---

## Testing Strategy

### Unit Tests
- Test each class/function in isolation
- Mock external dependencies
- Cover happy path + error cases
- Target: 80%+ coverage

### Integration Tests
- Test components working together
- Test API endpoints with real services
- Test message flow through broker
- Verify outputs from each phase

### End-to-End Tests
- Run complete workflow
- Verify final outputs
- Check all files created
- Validate outputs meet spec

### Load Testing (Phase 3+)
- Test with 10+ concurrent workflows
- Measure response times
- Identify bottlenecks

---

## Code Quality Standards

### Style Guide
- Follow PEP 8 (Python)
- Use Black for formatting
- Use type hints for all functions
- Max line length: 100 characters

### Linting
- Use flake8 for style checks
- Use pylint for deeper analysis
- Use mypy for type checking
- No warnings allowed in CI

### Pre-commit Checks
```bash
# Before committing:
black . && flake8 . && mypy . && pytest
```

### Git Workflow
- Feature branches for each component
- Commit messages: descriptive, present tense
- Pull requests require tests + docs
- Merge only with passing CI

---

## Known Constraints & Limitations

### Claude Code Terminal
- Ephemeral (terminates after use)
- No persistent background processes
- Must be re-invoked for next task
- Context window limitations (manage intelligently)

### MVP Phase Limitations
- No multi-step workflows (phases run sequentially)
- No parallel phase execution (Phase 3)
- Simple file-based state (upgrade to DB in Phase 2+)
- Limited scalability (focus on correctness first)

### Dependency Management
- Keep dependencies minimal
- Document any breaking versions
- Use requirements.txt for pinning versions

---

## Next Steps After Phase 3

Once Phase 3 is complete:

1. **Phase 4: Advanced Workflows**
   - Parallel phase execution
   - Conditional routing
   - Loop/retry logic

2. **Phase 5: Knowledge Base Integration**
   - Vector database for RAG
   - Document upload/ingestion
   - Web scraping agents

3. **Phase 6: Production Hardening**
   - PostgreSQL for persistence
   - Kubernetes for scaling
   - Observability (metrics, traces, logs)
   - Advanced security

4. **Phase 7: Multi-User & Multi-Project**
   - User management
   - Project isolation
   - Sharing & collaboration

---

## Communication During Development

### Daily Updates Checklist
- [ ] Which components completed
- [ ] Any blockers encountered
- [ ] Tests passing
- [ ] Code coverage percentage
- [ ] Next day's plan

### Code Review Checklist
- [ ] Tests pass locally
- [ ] Code follows style guide
- [ ] No hardcoded values
- [ ] Error handling present
- [ ] Documentation updated
- [ ] No security issues

