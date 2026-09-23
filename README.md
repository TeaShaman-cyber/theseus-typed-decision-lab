# Theseus Typed Decision Lab

Public Theseus research lab for reproducible typed System-1 decision-model experiments.

This repository is a neutral benchmark and runtime stand. It does not own Needle,
Jev, SemIf, NanoJev, Kev, or the Theseus program contract.

## Canonical coordination

- Program-level research question: `TeaShaman-cyber/theseus-research#76`.
- Typed decision semantics and authority boundary: `TeaShaman-cyber/theseus-needle-lab#55`.
- Needle vs Jev/Nimble-style comparison line: `TeaShaman-cyber/theseus-needle-lab#56`.
- Bootstrap work in this repository: issue #1.
- GitHub Project #9 is a coordination view only; repository issues, Git state,
  receipts, and explicit disposition remain authoritative.

Until Needle #55 versions the common typed decision contract, this lab MUST NOT
invent a competing canonical schema. The bootstrap SemIf fixture is runtime-smoke
input only.

## Research boundary

- Public/synthetic fixtures only.
- No credentials, private conversations, or secret corpora.
- Negative and inconclusive results are first-class outcomes.
- Model confidence is advisory. It cannot grant permission, establish VERIFIED
  state, accept an experiment, or authorize promotion.
- A green workflow proves only its declared postcondition.
- External upstreams are pinned to exact revisions before an experiment.
- Public visibility does not grant reuse rights to this repository. No project
  license has been selected yet; upstream components retain their own licenses.

## Compute surface

The default reproducible compute surface is GitHub Actions on public repositories.
The runner envelope verified for this bootstrap on 2026-09-23 is 4 vCPU, 16 GB RAM,
14 GB SSD per standard Ubuntu job, with no GPU. Parallel jobs are independent VMs,
not a shared-memory machine. Re-check provider limits before relying on them for a
future experiment.

MarcoPolo is the orchestration/research workbench, not the heavy compute target.
The repaired laptop is a later local-Hermes integration surface, not a prerequisite
for the first CPU canary.

## Research flow

```text
Issue / question
  -> branch / PR
  -> tools/dev/check
  -> runtime or model experiment
  -> artifact + provenance receipt
  -> domain evaluation
  -> independent review when needed
  -> explicit disposition
  -> promotion / merge
  -> exact remote readback
```

QA, runtime feasibility, model quality, scientific interpretation, acceptance,
promotion, and authority are separate stages.

## Bootstrap experiment

The first executable experiment is a SemIf CPU-only llama.cpp canary on a small
Qwen3 0.6B GGUF. Its claim scope is deliberately narrow:

`RUNTIME_FEASIBILITY_ONLY`

It checks that the pinned open stack can run on the standard CPU runner and emit
typed probabilities plus a provenance-bearing receipt. It does not establish
quality, calibration, Jev equivalence, or suitability for Hermes.

See:

- `docs/architecture.md`
- `docs/research-lifecycle.md`
- `docs/upstreams.md`
- `experiments/README.md`
- `receipts/README.md`

Run local deterministic QA with:

```bash
tools/dev/check
```
