# LAM_Comunication_Agent
Communication agent for the LAM ecosystem.

## Requirements
- Python 3.12+ (3.13 is OK)

## Install
```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r reqs\requirements.txt
```

## Usage (in-process bus)
```python
from src.interfaces.com_agent_interface import ComAgent

bus = ComAgent()
bus.register_agent("codex", object())

bus.send_data(
    "codex",
    {"task": "ping"},
    sender="operator",
    msg_type="task",
    topic="ping",
    meta={"trace_id": "t-001", "priority": 5},
)

result = bus.receive_data(timeout_s=1.0)
if result:
    name, message = result
    bus.ack(message["id"], success=True)
```

## Envelope contract
```json
{
  "id": "uuid",
  "to": "codex",
  "from": "operator",
  "type": "task|event|reply|log",
  "topic": "analysis|ping|queue|...",
  "ts": 1234567890,
  "payload": {},
  "meta": {"trace_id": "...", "priority": 5}
}
```

## Behavior
- Deterministic in-process queue
- Logging for send/receive/ack/retry
- Memory buffer + JSONL journal (`data/queue.jsonl`)
- Task retries with backoff and DLQ (`data/dlq.jsonl`)
- Automatic queue recovery on startup from JSONL