import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Literal, Optional, Tuple

MessageType = Literal["task", "event", "reply", "log"]


@dataclass
class Envelope:
    id: str
    to: str
    sender: str
    type: MessageType
    topic: str
    ts: int
    payload: Dict[str, Any]
    meta: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0

    @classmethod
    def new(
        cls,
        *,
        to: str,
        sender: str,
        msg_type: MessageType,
        topic: str,
        payload: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None,
    ) -> "Envelope":
        return cls(
            id=str(uuid.uuid4()),
            to=to,
            sender=sender,
            type=msg_type,
            topic=topic,
            ts=int(time.time()),
            payload=payload,
            meta=meta or {},
        )

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> None:
        cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Envelope":
        required = {"id", "to", "from", "type", "topic", "ts", "payload", "meta"}
        missing = required.difference(data.keys())
        if missing:
            raise ValueError(f"Envelope missing keys: {sorted(missing)}")
        msg_type = data["type"]
        if msg_type not in {"task", "event", "reply", "log"}:
            raise ValueError(f"Invalid message type: {msg_type!r}")
        if not isinstance(data["payload"], dict):
            raise ValueError("payload must be a dict")
        if not isinstance(data["meta"], dict):
            raise ValueError("meta must be a dict")
        if not isinstance(data["ts"], int):
            raise ValueError("ts must be an int")
        return cls(
            id=str(data["id"]),
            to=str(data["to"]),
            sender=str(data["from"]),
            type=msg_type,
            topic=str(data["topic"]),
            ts=int(data["ts"]),
            payload=data["payload"],
            meta=data["meta"],
            attempts=int(data.get("attempts", 0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "to": self.to,
            "from": self.sender,
            "type": self.type,
            "topic": self.topic,
            "ts": self.ts,
            "payload": self.payload,
            "meta": self.meta,
            "attempts": self.attempts,
        }

    def next_backoff_seconds(self) -> int:
        return min(2 ** max(self.attempts, 1), 30)


class ComAgent:
    """In-process communication bus with deterministic logging and retries."""

    def __init__(
        self,
        *,
        log_dir: str = "logs",
        journal_dir: str = "data",
        max_retries: int = 3,
        receive_poll_s: float = 0.05,
    ) -> None:
        self.agent_registry: Dict[str, Any] = {}
        self._queue: Deque[Envelope] = deque()
        self._inflight: Dict[str, Envelope] = {}
        self._max_retries = max_retries
        self._receive_poll_s = receive_poll_s

        self._log_dir = Path(log_dir)
        self._journal_dir = Path(journal_dir)
        self._queue_path = self._journal_dir / "queue.jsonl"
        self._dlq_path = self._journal_dir / "dlq.jsonl"

        self._setup_logging()
        self._ensure_dirs()
        self._load_journal()

    def _setup_logging(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(self._log_dir / "com_agent.log"),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s]: %(message)s",
        )
        self._logger = logging.getLogger(__name__)

    def _ensure_dirs(self) -> None:
        self._journal_dir.mkdir(parents=True, exist_ok=True)

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def _load_journal(self) -> None:
        if not self._queue_path.exists() and not self._dlq_path.exists():
            return

        timeline: Dict[str, Tuple[int, str, Envelope]] = {}
        order = 0

        def mark(state: str, envelope: Envelope) -> None:
            nonlocal order
            order += 1
            timeline[envelope.id] = (order, state, envelope)

        if self._queue_path.exists():
            with self._queue_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        self._logger.warning("Journal parse error, skipping line")
                        continue
                    event = record.get("event")
                    envelope_data = record.get("envelope")
                    if not event or not envelope_data:
                        continue
                    try:
                        envelope = Envelope.from_dict(envelope_data)
                    except ValueError:
                        self._logger.warning("Journal envelope invalid, skipping")
                        continue
                    if event in {"send", "retry"}:
                        mark("pending", envelope)
                    elif event == "receive":
                        mark("inflight", envelope)
                    elif event in {"ack", "dlq"}:
                        mark("done", envelope)

        if self._dlq_path.exists():
            with self._dlq_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        self._logger.warning("DLQ parse error, skipping line")
                        continue
                    envelope_data = record.get("envelope")
                    if not envelope_data:
                        continue
                    try:
                        envelope = Envelope.from_dict(envelope_data)
                    except ValueError:
                        self._logger.warning("DLQ envelope invalid, skipping")
                        continue
                    mark("done", envelope)

        if not timeline:
            return

        now = int(time.time())
        pending = 0
        inflight = 0
        for _, state, envelope in sorted(timeline.values(), key=lambda item: item[0]):
            if state == "pending":
                self._queue.append(envelope)
                pending += 1
            elif state == "inflight":
                if int(envelope.meta.get("available_at", 0)) < now:
                    envelope.meta["available_at"] = now
                self._queue.append(envelope)
                inflight += 1

        if pending or inflight:
            self._logger.info("Loaded %s pending, %s inflight messages", pending, inflight)

    def register_agent(self, agent_name: str, agent_obj: Any) -> None:
        self.agent_registry[agent_name] = agent_obj
        self._logger.info("Agent registered: %s", agent_name)

    def unregister_agent(self, agent_name: str) -> None:
        if agent_name in self.agent_registry:
            del self.agent_registry[agent_name]
            self._logger.info("Agent unregistered: %s", agent_name)
        else:
            self._logger.warning("Unregister failed, agent not found: %s", agent_name)

    def list_agents(self) -> list[str]:
        return list(self.agent_registry.keys())

    def send_data(
        self,
        agent_name: str,
        payload: Dict[str, Any],
        *,
        sender: str = "system",
        msg_type: MessageType = "event",
        topic: str = "general",
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if agent_name not in self.agent_registry:
            self._logger.error("Send failed, agent not registered: %s", agent_name)
            return False
        envelope = Envelope.new(
            to=agent_name,
            sender=sender,
            msg_type=msg_type,
            topic=topic,
            payload=payload,
            meta=meta,
        )
        return self.send_envelope(envelope)

    def send_envelope(self, envelope: Envelope) -> bool:
        if envelope.to not in self.agent_registry:
            self._logger.error("Send failed, agent not registered: %s", envelope.to)
            return False
        self._queue.append(envelope)
        self._append_jsonl(self._queue_path, {"event": "send", "envelope": envelope.to_dict()})
        self._logger.info("Enqueued message %s -> %s", envelope.sender, envelope.to)
        return True

    def send_raw(self, data: Dict[str, Any]) -> bool:
        try:
            envelope = Envelope.from_dict(data)
        except ValueError as exc:
            self._logger.error("Invalid envelope: %s", exc)
            return False
        return self.send_envelope(envelope)

    def receive_data(self, timeout_s: float = 1.0) -> Optional[Tuple[str, Dict[str, Any]]]:
        start = time.monotonic()
        while True:
            envelope = self._pop_available()
            if envelope is not None:
                if envelope.type == "task":
                    self._inflight[envelope.id] = envelope
                self._append_jsonl(
                    self._queue_path,
                    {"event": "receive", "envelope": envelope.to_dict()},
                )
                self._logger.info("Dequeued message %s for %s", envelope.id, envelope.to)
                return envelope.to, envelope.to_dict()

            if time.monotonic() - start >= timeout_s:
                self._logger.warning("Receive timeout after %.2fs", timeout_s)
                return None

            time.sleep(self._receive_poll_s)

    def _pop_available(self) -> Optional[Envelope]:
        now = int(time.time())
        for _ in range(len(self._queue)):
            envelope = self._queue.popleft()
            available_ts = int(envelope.meta.get("available_at", 0))
            if available_ts <= now:
                return envelope
            self._queue.append(envelope)
        return None

    def ack(self, message_id: str, *, success: bool = True, error: str = "") -> None:
        envelope = self._inflight.pop(message_id, None)
        if envelope is None:
            self._logger.warning("ACK ignored, unknown message id: %s", message_id)
            return

        if success:
            self._append_jsonl(
                self._queue_path,
                {"event": "ack", "envelope": envelope.to_dict()},
            )
            self._logger.info("ACK success for %s", message_id)
            return

        envelope.attempts += 1
        if envelope.attempts <= self._max_retries:
            backoff = envelope.next_backoff_seconds()
            envelope.meta["available_at"] = int(time.time()) + backoff
            self._queue.append(envelope)
            self._append_jsonl(
                self._queue_path,
                {
                    "event": "retry",
                    "envelope": envelope.to_dict(),
                    "error": error,
                },
            )
            self._logger.warning("Retry %s in %ss", message_id, backoff)
            return

        self._append_jsonl(
            self._queue_path,
            {
                "event": "dlq",
                "envelope": envelope.to_dict(),
                "error": error,
            },
        )
        self._append_jsonl(
            self._dlq_path,
            {
                "event": "dlq",
                "envelope": envelope.to_dict(),
                "error": error,
            },
        )
        self._logger.error("Moved to DLQ: %s", message_id)

    def log_communication(self, event: str, level: str = "INFO") -> None:
        if level == "INFO":
            self._logger.info(event)
        elif level == "WARNING":
            self._logger.warning(event)
        elif level == "ERROR":
            self._logger.error(event)
        else:
            self._logger.debug("Unknown log level %s: %s", level, event)