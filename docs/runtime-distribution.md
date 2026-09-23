# Runtime distribution

Tracking: issue #5.

Typed-decision candidates share one distribution contract, not one packaging mechanism.

- PACKAGE_REQUIRED: expensive supported runtime; build rarely and consume an immutable verified package.
- PACKAGE_CONDITIONAL: measure feasibility/bootstrap cost first.
- PACKAGE_LIGHT: consume upstream prebuilt runtime/model artifacts with exact identity and integrity checks.
- PACKAGE_NOT_JUSTIFIED: ordinary pinned installation is cheaper than package lifecycle cost.
- RUNTIME_BLOCKED: packaging must not hide an unsupported execution surface.

Runtime/toolchain identity and model artifact identity remain separate. Cache is an optimization only.

## SemIf first slice

The first hosted SemIf CPU canary spent roughly 294 seconds installing its dependency stack and roughly 10 seconds scoring four rows. The observed default PyPI Torch install also downloaded CUDA libraries on a CPU-only runner.

The producer therefore builds a CPU-only runtime package using official torch 2.10.0+cpu, compiles the pinned llama-cpp-python wheel once, installs the pinned SemIf stack into a relocatable site-packages tree, rejects NVIDIA packages, and emits a provenance receipt.

The GGUF remains a separate pinned/checksummed model artifact.

The existing cookbook semantic advisory composite action is not consumed whole by this experiment because that action intentionally couples package preparation to bounded repository-diff input. The verified artifact identity/integrity mechanics remain the reuse target for the consumer slice; decision semantics stay in this repository.
