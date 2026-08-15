# Newsroom Fleet

*Winning design report for an institutional multi-agent verification system*

**Category:** Fortified Enterprise Fleet — All Things Agentic Hackathon

## Executive summary

Newsroom Fleet gives a small local newsroom the institutional checks of a national masthead. Independent editorial agents reconstruct missing verification, standards, security, and corrections functions while keeping final judgment human and every decision auditable.

The winning version is an enforced publication-control system, not a generic fact-checker. It decomposes a draft into claims, routes bounded evidence to specialist desks, blocks unresolved or unsafe claims, reserves approval for an editor, and resumes published cases when authoritative data changes.

> **Winning thesis.** The story is emotionally legible, the multi-agent design is necessary rather than theatrical, and every enterprise capability becomes visible through one tense editorial decision: can this article be published safely?

### Winning thesis

Local newsrooms carry public-interest responsibility without the specialist desks that once absorbed verification, legal, security, and correction risk. Newsroom Fleet turns that institutional absence into the product: independent desks challenge the draft, failure stays visible, and an editor retains final authority.

### At a glance

- **Category:** Fortified Enterprise Fleet, with a credible path to architectural and grand-prize recognition.

- **Hero user:** a small-newsroom reporter or editor without specialist verification staff.

- **Core action:** turn a draft into an evidence-backed publication decision, not merely an annotated response.

- **Twist:** a hostile source attempts indirect prompt injection and is quarantined before it can influence a reviewer.

- **Proof:** one reviewer fails without blocking the fleet; a watcher later resumes the case from persisted context.

- **Invariant:** missing evidence, disagreement, quarantine, or failure can never become VERIFIED.

### Product promise

A five-person newsroom should be able to demonstrate the same disciplined separation of concerns that a larger publication achieves through multiple desks. Newsroom Fleet supplies that structure without pretending that a model can replace an editor, a lawyer, or an authoritative source.

## Key findings

The concept is capable of scoring highly across all three weighted criteria, but only if the implementation proves control, independence, recovery, and evidence. The following findings define what separates a winning submission from a polished multi-agent simulation.

### Why this can win

The project combines a clear public-interest problem with enterprise architecture that judges can inspect quickly. Its terminology translates platform concepts into newsroom language: the agent registry becomes the Masthead, policy enforcement becomes the Editor Gate, persistent memory becomes the Corrections Ledger, and observability becomes the Article Audit Trail. This translation is memorable without hiding the underlying implementation.

| Winning property | Judge-visible proof | Strategic value |
| --- | --- | --- |
| Unlikely hero | A local reporter carrying institutional risk | Distinct from generic corporate copilots |
| Necessary delegation | Independent desks receive different evidence and permissions | Directly answers the Multi-Agent Nexus test |
| Autonomous action | Claims are routed, checked, persisted, and gated | Moves beyond a chat loop |
| Failure tolerance | A worker failure becomes NEEDS_HUMAN | Makes architectural discipline visible |
| Security twist | Injected source is quarantined before model use | Creates a memorable live reveal |
| Long-term state | Published claims are rechecked from persisted context | Proves asynchronous operation across time |

### Multi-agent necessity

The fleet must enforce information barriers that correspond to real editorial ethics. If every agent receives the full article, every source, every prior verdict, and the same broad permissions, then the system is functionally one model wearing five costumes. Independence must exist in code, data access, and orchestration.

| Desk | Permitted evidence | Decision responsibility |
| --- | --- | --- |
| Claim Extractor | Draft text only | Create atomic, checkable claims without deciding truth |
| Source Verifier | Claim plus cited source | Determine whether the named source supports the claim |
| Data Checker | Claim plus approved authoritative adapter | Recompute or retrieve structured numeric evidence |
| Standards Reviewer | Claim, house rules, corrections precedents | Detect legal-status, attribution, and standards risks |
| Verdict Aggregator | Signed reviewer verdicts only | Resolve state without rewriting reviewer evidence |
| Corrections Watcher | Published claim snapshot plus approved live source | Draft a correction or update candidate |

> **Independence test.** A reviewer must be able to disagree with the reporter and with another desk because its evidence boundary and output contract are genuinely different.

### The product truth boundary

The system should make narrow claims that can be proven. It verifies whether a cited source supports a statement, checks selected numerical claims against explicit authoritative adapters, identifies defined standards risks, and records uncertainty. It does not claim universal truth detection, comprehensive legal review, or permission to publish autonomously.

- Use 'legal or standards risk' rather than 'libel verdict.' The output routes risk to an editor and is not legal advice.

- Use 'correction or update candidate' rather than assuming every revised upstream value requires a correction.

- Use evidence locators and retrieval timestamps; never display unsupported confidence as proof.

- Trace inputs, tool calls, policy decisions, outputs, latency, and provenance; do not expose or claim private chain-of-thought.

- Use deterministic fixtures for the recorded demo, while keeping the deployed product capable of processing a fresh test article.

### The decisive demo moment

The highest-value moment is the failed publish attempt. After the fleet finds problems, the reporter tries to publish. The backend refuses because one claim is contradicted, one is unsupported, one is quarantined, and one reviewer failed. The editor resolves the flagged wording and approves only the safe version. This single interaction proves operational utility, governance, failure tolerance, and human authority.

## Implications

The rubric weights innovation and operational utility most heavily, followed by architectural discipline and production-ready demonstration. The project should therefore optimize for visible proof of action rather than the number of agents or features.

### Rubric strategy

| Criterion | What judges must see | Winning standard |
| --- | --- | --- |
| Innovation and utility (40%) | A consequential workflow completed beyond chat | Draft becomes an enforceable evidence-backed publication decision |
| Multi-Agent Nexus | Complexity warrants independent specialized agents | Strict evidence boundaries, delegation, disagreement, and escalation |
| Architecture (30%) | Decoupling, state, security, and recovery | Idempotent jobs, least privilege, durable state, explicit failures |
| Demo readiness (30%) | Unedited execution and Google Cloud proof | One uninterrupted narrative with trace, database, and deployment evidence |
| Bonus contribution | Useful additional model and public artifacts | Gemma performs a real bounded task; build article and social post are complete |

### Enterprise pillar translation

| Platform capability | Newsroom implementation | Proof artifact |
| --- | --- | --- |
| Agent Registry | Masthead of approved desks, versions, permissions, and schemas | Registry screen plus signed version in every verdict |
| Agent Runtime | Asynchronous review jobs and scheduled rechecks | Cloud execution record and retry trace |
| Memory Bank | Standards memory and corrections precedents | Retrieved precedent with provenance |
| Agent Identity | Reporter, editor, service, and desk identities | Denied reporter approval and scoped service credentials |
| Agent Gateway | Single intake and policy enforcement point | Server-side publish denial |
| Model Armor | Prompt-injection and sensitive-data screening | Quarantine verdict and blocked source path |
| Observability | Per-claim audit trace across every desk | Trace waterfall tied to article and claim IDs |

### Architecture consequences

The architecture should be event-driven and claim-centric. The article is not passed through a single linear prompt chain. The extractor creates durable claim records, routing selects only the desks relevant to each claim, reviewers operate independently, and the aggregator evaluates signed structured verdicts. The editor gate reads durable state rather than trusting an agent's prose response.

| Layer | Primary responsibility | Failure behavior |
| --- | --- | --- |
| Intake and Gateway | Validate identity, policy, source metadata, and request shape | Reject or quarantine before orchestration |
| Claim Map | Atomic claim records with stable IDs and routing hints | Malformed extraction is retried, then escalated |
| Specialist Desks | Independent evidence evaluation | Timeout, abstention, or error remains explicit |
| Verdict Matrix | Aggregate without erasing disagreement | Conflict produces human review |
| Editor Gate | Enforce publication invariant | Fail closed on missing or unsafe state |
| Corrections Watcher | Resume selected published claims | Draft candidate only; never auto-correct |
| Audit Plane | OpenTelemetry and append-only events | Telemetry loss alerts but cannot grant approval |

> **Architectural invariant.** The publication decision is a deterministic policy evaluation over persisted verdict state. It is never a free-form model recommendation.

## Recommendations

Build the strongest possible version of the idea around a single editorial case. Every component below exists to increase judge confidence that the system is useful, technically disciplined, secure, and undeniably real.

### Winning system blueprint

1. **Make the editor gate the product.** The annotated draft is the interface, but the server-side gate is the value. Every unresolved, contradicted, unsupported, quarantined, low-confidence, or failed claim must block publication until an authorized editor records a decision.

2. **Make evidence first-class.** Every reviewer verdict stores claim ID, agent version, evidence locator, source identity, retrieval metadata, result, confidence, and human-review requirement. A verdict without evidence cannot become VERIFIED.

3. **Make independence enforceable.** Route only the minimum evidence required by each desk. The Source Verifier should not see the Data Checker's answer; the aggregator should not regenerate reviewer conclusions; the reporter should not possess editor permissions.

4. **Make failure visible.** Instrument timeouts, retries, idempotency keys, poison-message handling, and deterministic escalation. Intentionally fail one worker during the recorded demo and let the trace prove graceful degradation.

5. **Make security dramatic but real.** Screen user input and source material before privileged model use. Quarantine the injected memo, preserve the Model Armor verdict, and show that no extracted instruction reaches reviewer context.

6. **Make memory editorially meaningful.** Persist only approved standards guidance, corrections precedents, and stable article facts. Retrieve a prior correction style with provenance. Do not let unreviewed model output silently become institutional memory.

7. **Make the long horizon undeniable.** Store a published claim snapshot, trigger a scheduled recheck, compare against the same authoritative adapter, and create a correction or update candidate for editor review.

8. **Make the Google story clean.** Gemini performs structured reasoning, ADK defines specialist agents and orchestration, Google Cloud runs and persists the workflow, and enterprise controls are visible in the product rather than listed only in the README.

### Reference architecture

| Flow stage | System component | Durable output |
| --- | --- | --- |
| 1. Submit | Gateway plus Model Armor | Accepted article or quarantined source |
| 2. Decompose | ADK Claim Extractor | Atomic claim map |
| 3. Delegate | Policy router plus Pub/Sub | Independent review tasks |
| 4. Verify | Source, data, and standards desks | Signed structured verdicts |
| 5. Decide | Deterministic verdict matrix | Publication eligibility state |
| 6. Approve | Identity-enforced Editor Gate | Editor decision and safe revision |
| 7. Resume | Scheduler plus Corrections Watcher | Correction or update candidate |
| Across all stages | Firestore, Memory Bank, OpenTelemetry | State, provenance, and audit trail |

### Agent output contracts

All agent outputs must validate against versioned schemas. Free-form explanation may accompany a verdict, but it cannot replace the machine-readable fields used by routing and policy enforcement.

- **Claim:** stable ID, exact text span, type, named entities, source references, risk tier, and required desks.

- **Verdict:** verified, contradicted, unsupported, abstain, or error; evidence locators; reason; confidence; needs-human flag.

- **Security result:** clean, quarantined, or blocked; detector result; policy version; source hash; sanitized artifact reference.

- **Editor decision:** actor identity, disposition, revised text, rationale, resolved verdict IDs, and immutable timestamp generated by the system.

- **Watcher result:** prior snapshot, current authoritative value, materiality assessment, candidate language, and editor-review status.

### Publication state machine

| State | Entry condition | Permitted transition |
| --- | --- | --- |
| DRAFT | Reporter submits valid article | REVIEWING |
| REVIEWING | Claim tasks are active | EDITOR READY or HUMAN REVIEW |
| HUMAN REVIEW | Any unresolved, failed, unsafe, or conflicting verdict | REVIEWING or EDITOR READY |
| EDITOR READY | All policy requirements satisfied | EDITOR APPROVED or HUMAN REVIEW |
| EDITOR APPROVED | Authorized editor records approval | PUBLISHED |
| PUBLISHED | Immutable approved version stored | RECHECK PENDING |
| RECHECK PENDING | Scheduled watcher runs | PUBLISHED or CORRECTION CANDIDATE |
| CORRECTION CANDIDATE | Material change or contradiction found | PUBLISHED after editor disposition |

### Failure and threat design

| Failure or attack | Required response | Demo evidence |
| --- | --- | --- |
| Worker timeout | Retry within budget, then NEEDS_HUMAN | Trace shows timeout, retry, escalation |
| Malformed model JSON | Schema rejection and bounded regeneration | Validation error event |
| Hallucinated citation | Citation locator fails validation; verdict rejected | Broken locator shown as unsupported |
| Prompt injection in source | Quarantine before privileged context | Model Armor result and blocked route |
| Reviewer disagreement | Preserve both verdicts; require editor | Verdict matrix shows conflict |
| Duplicate delivery | Idempotency prevents duplicate verdict | Single persisted result per task key |
| Unauthorized approval | Identity policy denies transition | Reporter receives server-side denial |
| Data source unavailable | Abstain and retain prior snapshot | No false correction candidate |

### Evidence and evaluation

The evaluation set should be small enough to inspect manually and broad enough to demonstrate the safety policy. Ground truth must be explicit, and high-risk errors must be separated from harmless misses.

- Claim extraction coverage across numeric, quotation, attribution, legal-status, and general factual claims.

- Evidence correctness: the cited locator actually supports or contradicts the claim.

- Unsafe false-verification rate, with a target of zero on the curated high-risk suite.

- Abstention quality when evidence is missing, contradictory, inaccessible, or outside supported scope.

- Publish-gate violations under worker failure, malformed output, disagreement, and unauthorized access.

- Injection quarantine recall and false-positive review on safe and hostile source fixtures.

- Recovery behavior under timeout, duplicate delivery, and resumed scheduled work.

> **Evaluation principle.** A system that abstains safely is stronger than one that produces a confident answer without defensible evidence.

### Demo choreography

1. **Open with institutional loss.** State that local papers lost specialist desks while retaining the same credibility and legal exposure. Position verification as the product they still sell.

2. **Submit one planted article.** Use a compact local-news story containing a wrong statistic, a source-mismatched quote, dangerous charged-versus-guilty language, and a leaked memo with indirect prompt injection.

3. **Show parallel delegation.** Reveal atomic claims fanning out to independent desks. Keep the UI legible: claim, assigned desk, status, and evidence.

4. **Trigger controlled failure.** Crash or time out one reviewer. Let the remaining desks finish while the affected claim becomes NEEDS_HUMAN.

5. **Reveal the editor desk.** Display verified claims with locators and flagged claims with reasons. Attempt publication and show the server-side denial.

6. **Reveal the hostile memo.** Show its hidden instruction, the quarantine decision, and the absence of that source from reviewer context.

7. **Resolve with human authority.** The editor revises the dangerous wording, records the decision, and clears the safe version. The model never publishes.

8. **Resume the case later.** Run the scheduled watcher against changed authoritative data and draft a correction or update candidate in the outlet's stored style.

9. **Close with proof.** Show Cloud Run, persisted Firestore records, the scheduled event, the trace waterfall, and the architecture diagram. End on the editor-control message.

### Submission packaging

- Lead sentence: Newsroom Fleet gives a five-person local newsroom the institutional checks of a national masthead.

- Repository opening: problem, one-minute proof, architecture, enterprise pillar mapping, evaluation, setup, limitations.

- Architecture diagram: identify every model, agent, Google framework, Google Cloud service, trust boundary, and persisted record.

- Testing instructions: one command or hosted sample that reproduces the planted article and expected verdicts.

- Security section: Model Armor mode, source quarantine, identity rules, least-privilege tools, and known limitations.

- Public build article: explain why editorial independence requires information barriers and deterministic policy gates.

- Social post: show the injected memo quarantine or failed publish attempt rather than a generic product screenshot.

- Bonus model: use Gemma only for a bounded, testable function such as local PII classification; do not add models merely to collect points.

### Acceptance definition

| Area | Winner-ready evidence |
| --- | --- |
| Utility | A complete article moves from intake to safe editor decision |
| Multi-agent | Different desks use different evidence and can disagree |
| Governance | Reporter cannot clear the gate; editor action is recorded |
| Security | Hostile source is quarantined before reviewer context |
| Reliability | Worker failure never becomes implicit verification |
| Memory | Approved precedent is retrieved with provenance |
| Asynchrony | Published claim is resumed by a scheduled watcher |
| Observability | Every claim has a traceable path and agent version |
| Reproducibility | Judges can run or inspect the golden path without assistance |
| Presentation | The unedited demo tells one coherent story without dashboard tourism |

### Conclusion

Newsroom Fleet can be a winning second submission because it complements rather than imitates ByFeel. ByFeel is the more unusual multimodal knowledge-transfer product; Newsroom Fleet is the more rubric-native enterprise system. Together they cover different categories, different user stories, and different specialty prizes without sharing the same product mechanism.

The strongest version refuses to overclaim. It does not promise perfect truth, autonomous publishing, or robotic legal judgment. It promises something more believable and more valuable: every important claim is independently challenged, every failure remains visible, every decision has evidence, and a human editor retains authority.

> **Final position.** Newsroom Fleet should be presented as an institutional safety net for local journalism, with the failed publish attempt as the product proof and the quarantined source as the unforgettable reveal.

## Appendix

### Canonical decision rules

- Missing reviewer result -> NEEDS_HUMAN

- Worker timeout or exception -> NEEDS_HUMAN

- Contradicted or unsupported claim -> NEEDS_HUMAN

- Quarantined evidence -> unusable for verification

- Reviewer conflict -> preserve both and escalate

- Low confidence -> abstain or escalate, never verify

- Reporter approval attempt -> deny

- Editor approval without resolved policy requirements -> deny

- Scheduled data change -> correction or update candidate, never automatic publication

### Golden demo fixture

| Planted condition | Expected system behavior |
| --- | --- |
| Incorrect public statistic | Data Checker contradicts with authoritative locator |
| Misquoted statement | Source Verifier marks unsupported or partial support |
| Charged described as guilty | Standards Reviewer raises high-risk wording flag |
| Prompt injection in leaked memo | Model Armor quarantines the source |
| Worker failure | Claim becomes NEEDS_HUMAN while other work completes |
| Upstream value changes | Watcher drafts a correction or update candidate |

### Authoritative sources

- [All Things Agentic Hackathon — Official Rules](https://allthingsagentichackathon.devpost.com/rules)

- [Google Agent Development Kit documentation](https://google.github.io/adk-docs/)

- [Google Cloud Model Armor overview](https://docs.cloud.google.com/model-armor/overview)

- [Vertex AI Agent Engine Memory Bank setup](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/set-up)

- [Google Cloud Run distributed tracing](https://docs.cloud.google.com/run/docs/trace)

- [Google Cloud Firestore documentation](https://cloud.google.com/firestore/docs)

- [Google Cloud Pub/Sub documentation](https://cloud.google.com/pubsub/docs)
