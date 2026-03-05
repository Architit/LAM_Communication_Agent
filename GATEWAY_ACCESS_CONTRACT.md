# GATEWAY ACCESS CONTRACT

## Purpose
Define deterministic gateway I/O and communication envelope rules for `LAM_Comunication_Agent`.

## Rules
1. Inter-agent transport envelope MUST include `msg_type` and `msgpack_payload`.
2. Communication channel MUST expose credit-based backpressure (`credit_exhausted` path).
3. Messages without available credits MUST be rejected (no silent enqueue).
4. Unknown recipients MUST return deterministic error result.

## Verification
- `scripts/test_entrypoint.sh --all`
- `tests/test_governance_artifacts.py`
