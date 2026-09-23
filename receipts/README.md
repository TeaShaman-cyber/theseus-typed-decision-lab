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
