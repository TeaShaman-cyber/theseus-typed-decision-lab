# Upstream pins

Machine-readable pins live in `config/upstreams.json`.

Observed on 2026-09-23:

- TypeSafe System One adapter: MIT, exact Git revision pinned.
- SemIf / SemIf-OpenJev: MIT, exact Git revision pinned; first CPU runtime canary.
- NanoJev: MIT, exact Git revision pinned; future comparison candidate.
- Kev: Apache-2.0, exact Git revision pinned; future comparison candidate.
- Qwen3 0.6B base and official GGUF: exact Hugging Face revisions pinned for the
  SemIf tokenizer/GGUF runtime smoke.

Pins are experiment inputs, not claims that an upstream remains current later.
Refresh deliberately in an issue-scoped change when currentness matters.

Upstream licenses govern upstream code/models. This repository currently has no
project license.
