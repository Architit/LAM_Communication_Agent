from __future__ import annotations

from interfaces.com_agent_interface import ComAgent as _QueueComAgent

class ComAgent(_QueueComAgent):
    """
    Adapter for legacy callers expecting .communicate(dict).

    Expects dict to contain recipient under one of keys:
      - "recipient"
      - "to"
      - "target"
    Sends the whole payload as-is to queue-based ComAgent.send_data(recipient, payload).
    """

    def communicate(self, payload: dict) -> bool:
        recipient = payload.get("recipient") or payload.get("to") or payload.get("target")
        if not recipient:
            raise ValueError("communicate(payload) requires recipient in payload['recipient'|'to'|'target']")
        return self.send_data(str(recipient), payload)
