# WMS Roundtable Skill

## Runtime Location

The live Codex skill file tracked with this repo lives at:
- [/Volumes/MaxRelocated/WMS/.codex/skills/wms-roundtable/SKILL.md](/Volumes/MaxRelocated/WMS/.codex/skills/wms-roundtable/SKILL.md)

This document is the human-readable design note.
The `.codex/skills/.../SKILL.md` file is the runtime copy that Codex actually loads.

When the skill behavior changes:
- update this design note if the intent changed
- keep the runtime skill file in sync

## Recommended Codex Launch Pattern

For this project, the lowest-friction local launch path is:

```bash
./tools/run_codex_wms.sh
```

That wrapper:
- switches Codex into this repository root
- uses no-alt-screen so scrollback is easier to keep
- starts with approvals and sandbox bypassed for uninterrupted local debugging

For non-interactive use, the same wrapper can forward directly into `codex exec`:

```bash
./tools/run_codex_wms.sh exec --skip-git-repo-check "Reply with exactly: OK"
```

This repository keeps `.codex` ignored by default except for the tracked project skill itself, so local Codex state does not leak into version control.

## Purpose

Use this skill when a WMS decision needs more than one angle of judgment before implementation.

This skill is designed for questions that affect:
- floor operations
- product flow
- data model or API design
- customer rollout or training

The goal is not to generate long debate for its own sake.
The goal is to produce an executable recommendation after structured multi-role review.

## When To Use

Use this skill for:
- redesigning a warehouse workflow
- evaluating a new product direction
- deciding between two implementation paths
- reviewing customer feedback that affects multiple modules
- planning major UX changes across operations pages
- deciding whether a process should be AI-assisted or operator-driven

Do not use this skill for:
- simple CRUD changes
- one-file refactors
- straightforward bug fixes
- questions that already have a single obvious answer

## Roles

Always evaluate the question through these four roles.

### 1. Floor Operations

Focus on:
- what the warehouse operator will actually do
- how many steps are needed
- where scanning, printing, confirmation, or movement may fail
- whether the process increases or reduces operational friction

Ask:
- Will this be easy to use on the floor?
- Where will operators hesitate or mis-scan?
- What will slow receiving, putaway, picking, or shipping?

### 2. Product Design

Focus on:
- information hierarchy
- terminology
- page structure
- consistency with the rest of the product
- whether the workflow is understandable without training

Ask:
- Is the UI understandable at first glance?
- Are the labels and actions clear?
- Does this match the rest of the product's language and flow?

### 3. System Architecture

Focus on:
- models
- APIs
- permissions
- auditability
- upgrade path
- regression risk

Ask:
- What data structures are required?
- Is this safe to evolve?
- Where are the edge cases?
- What should be phase one versus later work?

### 4. Implementation Consulting

Focus on:
- whether customers can adopt it quickly
- rollout complexity
- training burden
- fit across different warehouse types
- exceptions and support risk

Ask:
- Can customers actually go live with this?
- Is the process teachable?
- Will different warehouse shapes or customer types need a variant?

## Standard Workflow

Follow this sequence every time.

### Step 1. Frame The Question

Restate the decision clearly in one sentence.

Include:
- what is changing
- who it affects
- what modules are involved

### Step 2. Role Perspectives

Write one short section per role:
- Floor Operations
- Product Design
- System Architecture
- Implementation Consulting

Each section should include:
- what the role likes
- what the role worries about
- the role's recommended direction

### Step 3. Cross-Examination

Challenge the proposed directions.

Specifically identify:
- assumptions that may be wrong
- hidden operational costs
- technical risks that product may be underestimating
- UX simplifications that may break real-world traceability or controls

### Step 4. Decision

End with a firm recommendation, not a vague summary.

Always output:
- Recommended approach
- Approaches rejected
- Main risks
- Minimum viable next step

## Output Format

Use this exact structure:

### Decision

One-sentence summary of the problem.

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
- Why this path wins
- What not to do yet

### Next Step

- Phase 1
- Phase 2
- Validation needed before rollout

## Decision Rules

Prefer solutions that:
- reduce floor friction
- preserve traceability
- keep the first version teachable
- avoid overbuilding phase one
- leave room for later printer, AI, or workflow expansion

Reject solutions that:
- look elegant in UI but create floor ambiguity
- hide critical exceptions
- require too many manual decisions under time pressure
- overfit to one customer scenario
- introduce a large backend surface area before the workflow is proven

## Example Triggers

This skill is especially suitable for questions like:
- Should receiving be driven by system-generated labels?
- Should warehouse planning support rackless area-based storage?
- Should the AI console be a tool launcher or a conversation-first workspace?
- Should billing changes version forward instead of rewriting history?
- How should import workflows balance preview, mapping, and confirmation?

## Example Invocation Prompt

Use this skill to evaluate the following WMS decision:

`Should receiving move from manual line confirmation to system-label-driven receiving, where the system generates labels, operators scan them at the dock, and the workflow automatically transitions to putaway?`

Review it through:
- Floor Operations
- Product Design
- System Architecture
- Implementation Consulting

Then produce:
- the recommended approach
- main risks
- what to implement in phase one
- what to postpone

## Notes For Adaptation

If this is later turned into a live Codex skill:
- keep the four fixed roles
- keep the output short and decision-oriented
- avoid turning the skill into a generic brainstormer
- prefer concrete implementation advice over abstract philosophy
