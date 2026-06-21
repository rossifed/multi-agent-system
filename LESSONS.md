# Lessons

- **2026-06-21** — When changing a FastAPI endpoint's response shape, test an
  actual request (TestClient/curl), not just `import`. I added a nested debug
  dict to `/health` typed `ApiSuccess[dict[str, str]]`; the import succeeded but
  the response failed Pydantic validation at request time → `/health` 500 →
  Railway healthcheck failed → deploy FAILED and the container stopped. An
  import check does not exercise response serialization. Always hit the endpoint.

- **2026-06-21** — Railway env var with a trailing space in the NAME
  (`AGENT_GATEWAY_API_KEY `) is invisible in the dashboard and silently not read
  by the app (it looks for the exact name). Diagnose container-side env by
  listing variable *names* (`railway variables --json` → keys only), not by
  trusting the dashboard. The container's view is ground truth, not the UI.
