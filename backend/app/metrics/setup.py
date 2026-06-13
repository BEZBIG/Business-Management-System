"""
Prometheus metrics instrumentation setup (NFR-01 criterion #2).

Call setup_metrics(app) immediately after creating the FastAPI app and BEFORE
adding any middleware (Pitfall 5 — instrument() must run before middleware is
stacked, otherwise /metrics returns only process_ metrics without http_ metrics).

The Instrumentator:
  - instrument(app): wraps every HTTP route with timing/counter middleware.
  - expose(app):     adds a GET /metrics endpoint that serves Prometheus text format.

Security note (T-03-02):
  - prometheus-fastapi-instrumentator does not include request bodies, auth tokens,
    or query parameter values in metric labels.
  - No user_id or other PII is used as a label (avoids unbounded label cardinality).
  - The /metrics endpoint is internal-only in production (network-level restriction
    is deferred to Phase 7 infra hardening; acceptable risk for Phase 1 internal tool).
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app: FastAPI) -> None:
    """Wire Prometheus instrumentator to the FastAPI app.

    Must be called BEFORE app.add_middleware() calls (Pitfall 5).
    instrument() attaches the timing middleware; expose() adds the /metrics route.
    """
    Instrumentator().instrument(app).expose(app)
