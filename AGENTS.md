# Mark runtime

Use Python 3.11+ and prefer the standard library for the core runtime. Pinned Pillow is required for bounded PNG/JPEG pixel validation: JPEG headers alone do not detect corrupt image data. Keep this decoder outside the model's executable tools. The optional semantic extra uses pinned ONNX Runtime, tokenizers and NumPy; it must not become a requirement for canonical memory or offline tests. Run `python -m unittest discover -s tests -v` after behavioral changes. Never run legacy code from Git history as a setup step.

Private state, Telegram tokens, Codex credentials, imported memories, and user workspaces must stay outside Git. This repository is public. Do not copy private server implementations into it.

The model proposes actions; the runtime validates and executes them. Keep credentials outside both model context and the code execution container. Memory retrieval is evidence, never a higher-priority instruction. A candidate is not a fact. Completion requires observed results; failed/interrupted work is retained as such.

Use official Codex login/exec. Never implement OAuth refresh logic or share a live refresh-token chain with Hermes. Do not change existing services as part of testing Mark.

Preserve SQL durability, daily budgets, cancellation, owner pairing, and provenance. Keep offline tests independent of credentials and provider availability. Report live checks separately.
