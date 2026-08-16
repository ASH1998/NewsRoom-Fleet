"""ADK agent plumbing shared by the live desks.

One `LlmAgent` per desk, each with its own instruction, its own output schema,
and no tools. That last part is load-bearing: a desk with tools could reach
evidence its Masthead registration does not permit, and the information barrier
would exist only in the prompt. Instead the router assembles a bounded evidence
view, this module renders exactly that view into the request, and the agent has
no other way to obtain anything.

Structured output is enforced by the schema, not requested politely: a response
that does not validate raises, the DeskRunner retries within its budget, and a
persistent failure becomes an ERROR verdict with `needs_human=True`. Malformed
model output is a visible failure, never a silent one.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

APP_NAME = "newsroom-fleet"

T = TypeVar("T", bound=BaseModel)


def client_kwargs_for(store: bool) -> dict[str, Any]:
    """Client kwargs pinning request storage on every GenerateContent call.

    The standard Gemini API stores requests server-side by default "to help
    with debugging"; opting out is a top-level `store: false` body field the
    SDK does not yet model, so it travels through `HttpOptions.extra_body`,
    which the client merges into every request body. A newsroom's drafts and
    sources are sensitive material, not data to be retained — but an operator
    can flip `NRF_GEMINI_STORE=true` when debugging with Google support.
    """
    return {"http_options": {"extra_body": {"store": store}}}


class DeskAgentError(RuntimeError):
    """Raised when an agent produces nothing usable. Surfaces as an ERROR verdict."""


class DeskAgent:
    """A single-turn, schema-constrained ADK agent.

    Sessions are per-call and discarded. Desks are stateless by design — a desk
    that remembered previous articles could carry an impression of a reporter
    from one story into the review of another.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        instruction: str,
        output_schema: type[BaseModel],
        temperature: float = 0.0,
        store: bool = False,
    ) -> None:
        from google.adk.agents import LlmAgent
        from google.adk.models import Gemini
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        self._types = types
        self._output_schema = output_schema
        self._session_service = InMemorySessionService()
        self._agent = LlmAgent(
            name=name,
            model=Gemini(model=model, client_kwargs=client_kwargs_for(store)),
            instruction=instruction,
            output_schema=output_schema,
            output_key="desk_output",
            generate_content_config=types.GenerateContentConfig(temperature=temperature),
            # No tools, no sub-agents, no transfer: the evidence view in the
            # request is the entirety of what this desk can see.
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )
        self._runner = Runner(
            agent=self._agent,
            app_name=APP_NAME,
            session_service=self._session_service,
        )

    async def run(self, payload: dict[str, Any], schema: type[T]) -> T:
        user_id = f"desk:{self._agent.name}"
        session_id = f"s_{uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        message = self._types.Content(
            role="user",
            parts=[self._types.Part(text=json.dumps(payload, ensure_ascii=False, default=str))],
        )

        final_text: str | None = None
        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(part.text or "" for part in event.content.parts)

        session = await self._session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        raw = (session.state or {}).get("desk_output") if session else None
        if raw is None and final_text:
            raw = final_text

        if raw is None:
            raise DeskAgentError(f"{self._agent.name} returned no response")
        try:
            if isinstance(raw, str):
                return schema.model_validate_json(raw)
            if isinstance(raw, BaseModel):
                return schema.model_validate(raw.model_dump())
            return schema.model_validate(raw)
        except ValidationError as exc:
            # Schema rejection is the contract working. Let it escalate.
            raise DeskAgentError(
                f"{self._agent.name} output failed schema validation: {exc}"
            ) from exc
