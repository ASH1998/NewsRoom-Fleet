"""Runtime configuration.

Every cloud-bound capability is an independent switch over an interface that
already has a local implementation. Fixture mode (all switches at their
defaults) needs zero API keys, zero network, zero cloud; `NRF_PRESET=cloud`
flips the whole fleet onto Google Cloud in one variable.

The switches are deliberately orthogonal. The recorded demo runs deterministic
fixture desks on Firestore + Pub/Sub + Cloud Trace, while the same deployment
processes a fresh article with `NRF_MODE=live`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "newsroom_fleet.sqlite3"


def load_dotenv(path: Path | None = None) -> None:
    """Load the repo-root `.env` into the environment, if present.

    Real environment variables always win — Cloud Run injects its configuration
    that way, and a local `.env` must never silently override a deployment. The
    file is gitignored; nothing here should ever be committed.
    """
    path = path or REPO_ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _first(*names: str, default: str | None = None) -> str | None:
    """First non-empty environment variable among `names`.

    Lets the project's own `.env` conventions (`PROJECT_ID`, `GOOGLE_MODEL`) work
    unchanged alongside the explicit `NRF_*` overrides a deployment sets.
    """
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


# Switch values, named once so bootstrap and the /api/runtime view agree.
MODE_FIXTURE, MODE_LIVE = "fixture", "live"
REPO_SQLITE, REPO_FIRESTORE = "sqlite", "firestore"
SCREENER_HEURISTIC, SCREENER_MODEL_ARMOR = "heuristic", "model_armor"
QUEUE_INPROCESS, QUEUE_PUBSUB = "inprocess", "pubsub"
MEMORY_FILE, MEMORY_BANK = "file", "memory_bank"
TRACING_OFF, TRACING_CONSOLE, TRACING_CLOUD = "off", "console", "cloud"
PII_OFF, PII_GEMMA = "off", "gemma"
GROUNDING_OFF, GROUNDING_SEARCH = "off", "search"


def _env_flag(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().lower()


@dataclass
class Settings:
    # --- component switches ------------------------------------------------
    mode: str = MODE_FIXTURE  # fixture (deterministic) | live (ADK + Gemini)
    repository: str = REPO_SQLITE
    screener: str = SCREENER_HEURISTIC
    queue: str = QUEUE_INPROCESS
    memory_backend: str = MEMORY_FILE
    tracing: str = TRACING_OFF
    pii_classifier: str = PII_OFF  # bounded Gemma bonus task at intake
    # Google Search grounding for the Data Checker. Only meaningful in live
    # mode, and billed per grounded query, so it is its own switch rather than
    # something `mode=live` silently turns on.
    grounding: str = GROUNDING_OFF
    #: Extra domains this newsroom will let clear a claim, beyond
    #: domain/authority.py's defaults.
    authoritative_domains: tuple[str, ...] = ()

    # --- local runtime -----------------------------------------------------
    db_path: Path = _DEFAULT_DB_PATH
    desk_timeout_s: float = 5.0
    desk_max_attempts: int = 2
    # Claims reviewed at once. 1 = one claim at a time: a live fleet paces its
    # Gemini/search calls (no rate-limit storms, no event-loop saturation), and
    # the editor UI streams the fleet working down the list — which is also the
    # better demo. Raise it for throughput; fixture desks are instant either way.
    review_concurrency: int = 1
    # Demo hook: name of a desk whose worker crashes on every attempt (graceful
    # degradation proof). None in normal operation.
    fail_desk: str | None = None
    authoritative_dataset: str = "v1"

    # --- Google Cloud ------------------------------------------------------
    gcp_project: str | None = None
    # Matches the existing Firestore database's region (asia-south1). Keeping
    # compute next to state avoids a cross-region hop on every read.
    gcp_location: str = "asia-south1"
    gemini_model: str = "gemini-3.6-flash"
    # Gemma is the bonus model and does one bounded job (intake PII). The A4B
    # mixture-of-experts variant is the cheap end of the family — a
    # five-category classifier does not need the dense 31B.
    gemma_model: str = "gemma-4-26b-a4b-it"
    model_armor_template: str | None = None  # short template id, not the full path
    # The standard Gemini API stores GenerateContent requests server-side by
    # default "to help with debugging". The fleet opts out on every call
    # (`store: false`); set true (NRF_GEMINI_STORE=true) to let Google retain
    # requests when debugging with Google support.
    gemini_store: bool = False
    firestore_database: str = "(default)"
    firestore_prefix: str = "newsroom_fleet"
    pubsub_topic: str = "newsroom-fleet-reviews"
    pubsub_dead_letter_topic: str = "newsroom-fleet-reviews-dlq"
    # Full Agent Engine resource name, e.g.
    # projects/<n>/locations/<loc>/reasoningEngines/<id>
    memory_bank_engine: str | None = None
    # Two accepted proofs of service identity on the /api/internal endpoints.
    # Cloud Scheduler sends the shared secret as a custom header; Pub/Sub push
    # cannot set custom headers, so it presents a Google-signed OIDC token and
    # we check the caller's service account against this allowlist. Both are
    # absent locally, which leaves the guard inert in fixture mode.
    service_token: str | None = None
    service_accounts: list[str] = field(default_factory=list)
    allowed_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ------------------------------------------------------------------ views
    @property
    def uses_cloud(self) -> bool:
        return (
            self.mode == MODE_LIVE
            or self.repository == REPO_FIRESTORE
            or self.screener == SCREENER_MODEL_ARMOR
            or self.queue == QUEUE_PUBSUB
            or self.memory_backend == MEMORY_BANK
            or self.tracing == TRACING_CLOUD
            or self.pii_classifier == PII_GEMMA
        )

    def runtime_view(self) -> dict[str, object]:
        """What the UI shows so judges can see which implementation is live."""
        return {
            "mode": self.mode,
            "repository": self.repository,
            "screener": self.screener,
            "queue": self.queue,
            "memory": self.memory_backend,
            "tracing": self.tracing,
            "pii_classifier": self.pii_classifier,
            "grounding": self.grounding,
            "gemini_store": self.gemini_store,
            "gcp_project": self.gcp_project,
            "gcp_location": self.gcp_location,
            "models": {
                "reasoning": self.gemini_model if self.mode == MODE_LIVE else None,
                "pii": self.gemma_model if self.pii_classifier == PII_GEMMA else None,
            },
            "authoritative_dataset": self.authoritative_dataset,
            "uses_cloud": self.uses_cloud,
        }

    # ------------------------------------------------------------------- env
    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        # One variable moves the whole fleet onto Google Cloud; individual
        # NRF_* variables still win, so a cloud deployment can keep the
        # deterministic fixture desks for the recorded demo.
        cloud = _env_flag("NRF_PRESET", "") == "cloud"
        project = _first("NRF_GCP_PROJECT", "GOOGLE_CLOUD_PROJECT", "PROJECT_ID")
        origins = os.getenv("NRF_ALLOWED_ORIGINS")

        mode = _env_flag("NRF_MODE", MODE_FIXTURE)
        # Fixture desks answer in microseconds, so 5s is a generous ceiling that
        # keeps the failure demo snappy. A live desk is a round trip to Gemini;
        # at 5s every one of them would time out and the whole fleet would
        # escalate for a reason that is purely operational.
        default_timeout = "60" if mode == MODE_LIVE else "5"

        return cls(
            mode=mode,
            repository=_env_flag("NRF_REPOSITORY", REPO_FIRESTORE if cloud else REPO_SQLITE),
            screener=_env_flag(
                "NRF_SCREENER", SCREENER_MODEL_ARMOR if cloud else SCREENER_HEURISTIC
            ),
            queue=_env_flag("NRF_QUEUE", QUEUE_PUBSUB if cloud else QUEUE_INPROCESS),
            memory_backend=_env_flag("NRF_MEMORY", MEMORY_BANK if cloud else MEMORY_FILE),
            tracing=_env_flag("NRF_TRACING", TRACING_CLOUD if cloud else TRACING_OFF),
            pii_classifier=_env_flag("NRF_PII", PII_GEMMA if cloud else PII_OFF),
            # Defaults on in live mode: a fleet that cannot look anything up is
            # the thing this switch exists to fix. Set NRF_GROUNDING=off to
            # review without spending grounded queries.
            grounding=_env_flag(
                "NRF_GROUNDING", GROUNDING_SEARCH if mode == MODE_LIVE else GROUNDING_OFF
            ),
            authoritative_domains=tuple(
                d.strip()
                for d in (os.getenv("NRF_AUTHORITATIVE_DOMAINS") or "").split(",")
                if d.strip()
            ),
            db_path=Path(os.getenv("NRF_DB_PATH", str(_DEFAULT_DB_PATH))),
            desk_timeout_s=float(os.getenv("NRF_DESK_TIMEOUT_S", default_timeout)),
            desk_max_attempts=int(os.getenv("NRF_DESK_MAX_ATTEMPTS", "2")),
            review_concurrency=int(os.getenv("NRF_REVIEW_CONCURRENCY", "1")),
            fail_desk=os.getenv("NRF_FAIL_DESK") or None,
            authoritative_dataset=os.getenv("NRF_AUTHORITATIVE_DATASET", "v1"),
            gcp_project=project,
            gcp_location=_first("NRF_GCP_LOCATION", default="asia-south1"),
            # GOOGLE_MODEL is this project's own .env convention for the
            # reasoning model; NRF_GEMINI_MODEL overrides it in a deployment.
            gemini_model=_first("NRF_GEMINI_MODEL", "GOOGLE_MODEL", default="gemini-3.6-flash"),
            gemma_model=_first("NRF_GEMMA_MODEL", default="gemma-4-26b-a4b-it"),
            model_armor_template=os.getenv("NRF_MODEL_ARMOR_TEMPLATE") or None,
            gemini_store=os.getenv("NRF_GEMINI_STORE", "").strip().lower() in ("1", "true", "yes"),
            firestore_database=os.getenv("NRF_FIRESTORE_DATABASE", "(default)"),
            firestore_prefix=os.getenv("NRF_FIRESTORE_PREFIX", "newsroom_fleet"),
            pubsub_topic=os.getenv("NRF_PUBSUB_TOPIC", "newsroom-fleet-reviews"),
            pubsub_dead_letter_topic=os.getenv("NRF_PUBSUB_DLQ", "newsroom-fleet-reviews-dlq"),
            memory_bank_engine=os.getenv("NRF_MEMORY_BANK_ENGINE") or None,
            # Stripped: Secret Manager payloads routinely carry a trailing
            # newline from however they were written, and Cloud Run injects the
            # payload verbatim. An invisible "\n" here is a 401 with no
            # diagnosable cause.
            service_token=(os.getenv("NRF_SERVICE_TOKEN") or "").strip() or None,
            service_accounts=[
                a.strip() for a in (os.getenv("NRF_SERVICE_ACCOUNTS") or "").split(",") if a.strip()
            ],
            allowed_origins=(
                [o.strip() for o in origins.split(",") if o.strip()]
                if origins
                else ["http://localhost:5173", "http://127.0.0.1:5173"]
            ),
        )
