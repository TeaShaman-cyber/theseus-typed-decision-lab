# Architecture

## Purpose

This lab separates a common experimental surface from model ownership.

```text
canonical typed contract (Needle #55, once versioned)
                    |
                    v
            public fixture set
                    |
        +-----------+-----------+
        |           |           |
      Needle      SemIf      NanoJev / Kev / other
        |           |           |
        +-----------+-----------+
                    |
                    v
          normalized measurements
                    |
                    v
          provenance-bearing receipts
                    |
                    v
             explicit disposition
```

Jev itself is an external reference only when an authorized current access route
exists.

## Authority boundary

The learned decision layer may propose a bounded action or probability. It may not:

- promote state to VERIFIED;
- grant permission;
- accept a scientific result;
- authorize merge, release, or production promotion;
- replace a deterministic verifier where the contract requires one.

## Runtime surfaces

### GitHub Actions

Default reproducible CPU compute. Each job is an independent ephemeral VM.
Use matrices for independent shards, replications, or model/config comparisons.
Do not describe many independent runners as one large shared-memory machine.

### MarcoPolo

Orchestration, repository work, inspection, bounded analysis, and readback.
Historical resource ceilings make it unsuitable as the default heavy model runtime.

### Local Hermes host

Later integration surface for an always-on helper after hardware recovery and a
fresh host inventory. It is not an acceptance dependency for the hosted CPU stand.

## Bootstrap dependency graph

```text
repo bootstrap
    -> canonical local QA
    -> pinned upstream inventory
    -> SemIf CPU runtime canary
    -> runtime receipt

Needle #55 canonical contract
    -> shared benchmark fixtures
    -> cross-model comparison
```

The second branch is intentionally blocked until the canonical contract exists.
