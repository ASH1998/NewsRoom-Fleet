"""Review task queue — the seam between in-process asyncio and Pub/Sub.

A review task is the unit of independent work: one claim, one desk. Its
idempotency key is `{article_id}:{claim_id}:{desk}` — claim ids are unique per
article, not globally, so the article scopes the key — and it is the same key
the repository already enforces one persisted verdict against, so duplicate
delivery (Pub/Sub's at-least-once guarantee) cannot produce a duplicate
verdict. The queue moves where the work runs; it does not change what a desk
may see or what the gate reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from newsroom_fleet.domain.contracts import Desk


@dataclass(frozen=True)
class ReviewTask:
    article_id: str
    claim_id: str
    desk: Desk

    @property
    def idempotency_key(self) -> str:
        return f"{self.article_id}:{self.claim_id}:{self.desk.value}"

    def to_dict(self) -> dict[str, str]:
        return {
            "article_id": self.article_id,
            "claim_id": self.claim_id,
            "desk": self.desk.value,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReviewTask:
        return cls(
            article_id=data["article_id"],
            claim_id=data["claim_id"],
            desk=Desk(data["desk"]),
        )


class ReviewQueue(Protocol):
    """Publish independent review tasks for asynchronous execution."""

    name: str

    def publish(self, task: ReviewTask) -> str:
        """Enqueue one task. Returns a broker message id. Raises on failure so
        the caller can fall back to running the review in-process."""
