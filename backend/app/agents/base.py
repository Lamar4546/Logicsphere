"""
Base class for all LogiSphere agents.

SRS §7.1 Agent Coordination requirements this enforces:
  - Agents operate as specialized capabilities within one coordinated platform.
  - Agent outputs are identifiable as observations, predictions,
    recommendations, or actions.
  - Agent failures are observable and do not silently remove critical
    operational visibility (every run is logged to agent_runs, success or fail).
  - An agent does not access data outside its configured authorization scope
    (every agent method takes organization_id explicitly and every query
    filters by it — no agent is allowed a cross-tenant query).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from ..services.supabase_client import get_client

OutputKind = Literal["observation", "prediction", "recommendation", "action"]


class AgentOutput:
    """Structured, typed output every agent must return — never a bare dict,
    so downstream consumers (Central AI Logistics Manager, UI) can always
    tell facts from predictions from recommendations (SRS §14.2)."""

    def __init__(
        self,
        kind: OutputKind,
        summary: str,
        data: dict[str, Any] | None = None,
        confidence: float | None = None,
    ):
        self.kind = kind
        self.summary = summary
        self.data = data or {}
        self.confidence = confidence

    def to_dict(self):
        return {
            "kind": self.kind,
            "summary": self.summary,
            "data": self.data,
            "confidence": self.confidence,
        }


class BaseAgent:
    name: str = "base_agent"

    def _log_run(
        self,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        input_summary: dict,
        output: AgentOutput | None,
        status: str,
        error_message: str | None = None,
        started_at: datetime | None = None,
    ):
        db = get_client()
        db.table("agent_runs").insert(
            {
                "organization_id": organization_id,
                "agent_name": self.name,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "input_summary": input_summary,
                "output_summary": output.to_dict() if output else None,
                "output_kind": output.kind if output else None,
                "status": status,
                "error_message": error_message,
                "started_at": (started_at or datetime.now(timezone.utc)).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

    def run(self, organization_id: str, **kwargs) -> AgentOutput:
        """Subclasses implement _execute; run() wraps it with logging so a
        failure is always observable (SRS §7.1) instead of silently dropped."""
        started_at = datetime.now(timezone.utc)
        entity_type = kwargs.get("entity_type", "unknown")
        entity_id = kwargs.get("entity_id", "unknown")
        try:
            output = self._execute(organization_id=organization_id, **kwargs)
            self._log_run(
                organization_id, entity_type, entity_id, kwargs, output,
                status="success", started_at=started_at,
            )
            return output
        except Exception as exc:
            self._log_run(
                organization_id, entity_type, entity_id, kwargs, None,
                status="failed", error_message=str(exc), started_at=started_at,
            )
            raise

    def _execute(self, organization_id: str, **kwargs) -> AgentOutput:
        raise NotImplementedError
