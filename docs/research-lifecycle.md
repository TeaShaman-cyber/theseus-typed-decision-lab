# Research lifecycle

This repository follows the Theseus Research DevOps separation of concerns.

## Stages

```text
QUESTION
  -> IMPLEMENTATION / EXPERIMENT SLICE
  -> LOCAL QA
  -> DOMAIN / RUNTIME VERIFICATION
  -> REVIEW
  -> ACCEPTANCE DECISION
  -> PROMOTION
  -> READBACK
  -> DISPOSITION
```

A later release/publication stage may be added only when a concrete need appears.

## State discipline

Useful states include:

- `QA_PASS`
- `QA_FAILED`
- `VERIFIED`
- `VERIFICATION_DEGRADED`
- `VERIFICATION_FAILED`
- `ACCEPTANCE_PENDING`
- `PROMOTION_NOT_AUTHORIZED`
- `BLOCKED`
- `UNKNOWN`
- `DISPOSITIONED`

These labels describe evidence/lifecycle state. They do not automatically imply
permission or authority.

## Receipt scopes

Bootstrap runtime receipts MUST declare one explicit claim scope. The first canary
uses:

`RUNTIME_FEASIBILITY_ONLY`

A receipt with that scope may establish that a pinned stack executed and produced
well-formed outputs on a recorded runtime. It does not establish model quality,
calibration, semantic correctness, Jev equivalence, or production readiness.

## Failure handling

Preserve negative results. A timeout, OOM, dependency failure, invalid output, or
model-load failure is evidence about that exact configuration. It is not proof that
the whole model family is unusable.

## Heavy vs light checks

`tools/dev/check` stays cheap and deterministic. Model downloads and inference
belong to manually triggered or otherwise explicitly scoped heavy workflows.
