"""Pub/Sub review queue — the distributed Agent Runtime.

Each claim/desk pair becomes one message. A push subscription delivers it back
to `/api/internal/review-task`, which runs that single desk and persists one
signed verdict. Two properties carry over unchanged from the in-process runner:

* **Idempotency.** The message carries `{claim_id}:{desk}` and the repository
  refuses a second healthy verdict for that pair, so at-least-once delivery
  cannot double-write.
* **Ordering per claim.** Messages are keyed by claim so a claim's desks land
  in a stable order; desks for *different* claims still run concurrently.

Poison messages are handled by the subscription's dead-letter policy (see
`deploy/setup_gcp.sh`), not by silently dropping work: a task that exhausts its
delivery attempts lands in the DLQ, and the claim's missing verdict makes the
Editor Gate escalate to NEEDS_HUMAN. Losing a worker can never imply approval.
"""

from __future__ import annotations

import json
import logging

from newsroom_fleet.orchestration.queue import ReviewTask

log = logging.getLogger(__name__)


class PubSubReviewQueue:
    name = "pubsub"

    def __init__(
        self,
        *,
        project: str | None,
        topic: str,
        dead_letter_topic: str = "",
    ) -> None:
        if not project:
            raise ValueError("Pub/Sub requires a GCP project (NRF_GCP_PROJECT)")
        from google.cloud import pubsub_v1

        self._project = project
        self._dead_letter_topic = dead_letter_topic
        # Ordering keys require the publisher to be configured for them.
        self._publisher = pubsub_v1.PublisherClient(
            publisher_options=pubsub_v1.types.PublisherOptions(enable_message_ordering=True)
        )
        self._topic_path = self._publisher.topic_path(project, topic)
        # No eager get_topic() here. `roles/pubsub.publisher` grants
        # `pubsub.topics.publish` but not `pubsub.topics.get`, so a fail-fast
        # existence check would 403 against a correctly-scoped identity and send
        # the whole fleet back to in-process execution. Widening the role to make
        # a health check pass would be the wrong trade: the router already
        # degrades to in-process on a publish failure and audits it as
        # `queue_degraded`, which is the honest signal anyway.

    def publish(self, task: ReviewTask) -> str:
        future = self._publisher.publish(
            self._topic_path,
            json.dumps(task.to_dict()).encode("utf-8"),
            ordering_key=task.claim_id,
            idempotency_key=task.idempotency_key,
            article_id=task.article_id,
            desk=task.desk.value,
        )
        message_id = future.result(timeout=30)
        log.debug("published review task %s as %s", task.idempotency_key, message_id)
        return message_id


def decode_push_envelope(envelope: dict) -> ReviewTask:
    """Parse a Pub/Sub push envelope into a ReviewTask.

    Push delivery wraps the payload as
    `{"message": {"data": "<base64>", "attributes": {...}}, "subscription": ...}`.
    """
    import base64

    message = envelope.get("message") or {}
    data = message.get("data")
    if not data:
        raise ValueError("push envelope carries no message data")
    payload = json.loads(base64.b64decode(data).decode("utf-8"))
    return ReviewTask.from_dict(payload)
