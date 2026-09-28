# Receipts

Receipts are evidence records, not scientific acceptance.

The SemIf CPU canary emits a JSON receipt plus raw output/runtime metadata as a
GitHub Actions artifact. The receipt binds:

- repository commit/run identity;
- upstream revisions;
- fixture SHA-256;
- model/GGUF SHA-256 and byte size;
- runner CPU/memory/disk metadata;
- output SHA-256 and result IDs;
- elapsed time where available;
- explicit claim scope.

Do not commit large model artifacts or transient workflow outputs to Git.

## AnyJev HBR-1 historical blind replay

The small HBR-1 evidence from issue #34 is preserved in Git after successful
hosted run `36458707223`:

- `anyjev-hbr1/run-36458707223-candidate.json` is the immutable raw/L0 candidate
  receipt produced before the later mathematical outcome escrow was interpreted;
- `anyjev-hbr1/run-36458707223-comparison.json` is a deterministic post-score
  comparison receipt that binds the candidate receipt hash and records the
  historical-advisor / later-outcome comparison separately.

The candidate receipt remains the model-observation record. The comparison
receipt is downstream analysis and must not be treated as candidate input,
calibration evidence, scientific acceptance, or authority.
