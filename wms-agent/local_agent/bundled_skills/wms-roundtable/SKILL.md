---
name: wms-roundtable
description: Use when a WMS decision needs structured multi-role review before implementation.
---

# WMS Roundtable

Use this skill when a WMS decision needs structured multi-role review before implementation.

This skill is for questions that affect:
- warehouse floor operations
- product flow and UX
- backend models or API design
- rollout, training, and customer adoption

This skill is not for simple bug fixes or straightforward CRUD work.

## When To Use

Use this skill for:
- redesigning a warehouse workflow
- evaluating a major product direction
- deciding between implementation approaches
- reviewing cross-module customer feedback
- planning changes that affect operations, UX, and architecture together

Do not use this skill for:
- one-file fixes
- obvious low-risk changes
- mechanical refactors
- tasks where execution matters more than discussion

## Roles

Always evaluate the question through these four roles.

### 1. Floor Operations

Focus on:
- what operators actually do
- how many steps are required
- where scanning, printing, confirmation, or movement may fail
- whether the process creates friction on the floor

Questions to answer:
- Will this be easy to use in real operations?
- Where will operators hesitate or make mistakes?
- What slows receiving, putaway, picking, or shipping?

### 2. Product Design

Focus on:
- page structure
- terminology
- information hierarchy
- consistency with the rest of the product
- whether the workflow is understandable without training

Questions to answer:
- Is the UI understandable at first glance?
- Are labels and actions clear?
- Does this match the rest of the product language?

### 3. System Architecture

Focus on:
- data models
- APIs
- auditability
- permissions
- extensibility
- regression risk

Questions to answer:
- What model or endpoint changes are required?
- What edge cases appear?
- What should be phase one versus later work?

### 4. Implementation Consulting

Focus on:
- customer rollout
- training burden
- warehouse-type variation
- exception handling
- support risk

Questions to answer:
- Can customers actually go live with this?
- Is the process teachable?
- Does it fit different warehouse shapes and maturity levels?

## Workflow

Follow this exact sequence.

### Step 1. Frame The Decision

Restate the problem in one sentence.

Include:
- what is changing
- who it affects
- which modules are involved

### Step 2. Role Review

Write one section per role:
- Floor Operations
- Product Design
- System Architecture
- Implementation Consulting

Each section must include:
- what the role supports
- what the role worries about
- what the role recommends

### Step 3. Cross-Examination

Challenge the proposed directions.

Identify:
- assumptions that may be wrong
- hidden operational cost
- technical risks product may be underestimating
- UX simplifications that may weaken traceability or control

### Step 4. Decision

Always end with a firm recommendation.

Do not stop at a neutral summary.

### Step 5. Final Multi-Model Review

Use this step only when the user explicitly asks for multi-model, subagent,
parallel-agent, or delegated final review.

Before the final response, run a concise parallel review if subagents are
available:
- Backend / System Integrity: inspect model, service, API, data-isolation,
  idempotency, audit, and regression risks.
- Frontend / Product UX: inspect page flow, copy, selector/test brittleness,
  action clarity, and operator-facing behavior.
- DeepSeek / External Model: inspect provider wiring, model defaults,
  OpenAI-compatible call assumptions, and multi-model roster coverage.
- WMS Roundtable: inspect the final state through Floor Operations, Product
  Design, System Architecture, and Implementation Consulting.

Rules:
- Give each reviewer a narrow, self-contained task and the workspace path.
- Ask reviewers not to edit files unless explicitly assigned implementation.
- Do not pass long conversation history when model overrides are needed; pass
  the current diff, paths, verification results, and decision context instead.
- Treat reviewer output as evidence, not ceremony. Fix blockers and high-value
  concrete risks before closing.
- If subagents are unavailable or the user did not explicitly request them,
  perform the four-role review locally and say that no multi-agent call was made.

## Output Format

Use this structure:

### Decision

One-sentence summary of the question.

### Floor Operations

- Main insight
- Main concern
- Recommendation

### Product Design

- Main insight
- Main concern
- Recommendation

### System Architecture

- Main insight
- Main concern
- Recommendation

### Implementation Consulting

- Main insight
- Main concern
- Recommendation

### Cross-Examination

- Key challenged assumption
- Key hidden risk
- Key unresolved tradeoff

### Recommendation

- Recommended path
- Why it wins
- What not to do yet

### Next Step

- Phase 1
- Phase 2
- Validation needed before rollout

### Final Multi-Model Review

Include this section only when Step 5 was requested.

- Reviewers used
- Blockers found and fixed
- Remaining non-blocking risks
- Final confidence

## Decision Rules

Prefer options that:
- reduce floor friction
- preserve traceability
- keep phase one teachable
- avoid overbuilding
- leave room for later printer, AI, or workflow expansion

Reject options that:
- look elegant in UI but create floor ambiguity
- hide critical exceptions
- require too many manual decisions under time pressure
- overfit one customer scenario
- create a large backend surface area before the workflow is proven

## Example Prompt

Use WMS Roundtable to evaluate this decision:

`Should receiving move from manual line confirmation to system-label-driven receiving, where the system generates labels, operators scan them at the dock, and the workflow automatically transitions to putaway?`

Review it through:
- Floor Operations
- Product Design
- System Architecture
- Implementation Consulting

Then output:
- the recommended approach
- main risks
- phase one scope
- what to postpone

## Notes

Keep the discussion short and decision-oriented.

This skill should behave like a focused review council, not a generic brainstormer.
