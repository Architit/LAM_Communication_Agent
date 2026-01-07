import json
import time

import pytest

from src.interfaces.com_agent_interface import ComAgent, Envelope


def create_bus(tmp_path, max_retries=2):
    return ComAgent(
        log_dir=str(tmp_path / "logs"),
        journal_dir=str(tmp_path / "data"),
        max_retries=max_retries,
        receive_poll_s=0.0,
    )


def test_envelope_validate_and_from_dict():
    env = Envelope.new(
        to="codex",
        sender="operator",
        msg_type="task",
        topic="ping",
        payload={"msg": "hello"},
        meta={"trace_id": "t-1"},
    )
    data = env.to_dict()

    Envelope.validate(data)
    parsed = Envelope.from_dict(data)
    assert parsed.to == env.to
    assert parsed.sender == env.sender
    assert parsed.type == env.type

    with pytest.raises(ValueError):
        Envelope.validate({"id": "only"})


def test_receive_timeout_returns_none(tmp_path):
    bus = create_bus(tmp_path)
    assert bus.receive_data(timeout_s=0.01) is None


def test_task_retry_then_ack(tmp_path):
    bus = create_bus(tmp_path, max_retries=2)
    bus.register_agent("codex", object())

    assert bus.send_data(
        "codex",
        {"task": "ping"},
        sender="operator",
        msg_type="task",
        topic="ping",
    )

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result

    bus.ack(message["id"], success=False, error="fail")
    assert len(bus._queue) == 1

    envelope = bus._queue.popleft()
    envelope.meta["available_at"] = int(time.time()) - 1
    bus._queue.append(envelope)

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message_retry = result
    assert message_retry["attempts"] == 1

    bus.ack(message_retry["id"], success=True)
    assert message_retry["id"] not in bus._inflight


def test_task_retries_to_dlq(tmp_path):
    bus = create_bus(tmp_path, max_retries=1)
    bus.register_agent("codex", object())

    assert bus.send_data(
        "codex",
        {"task": "ping"},
        sender="operator",
        msg_type="task",
        topic="ping",
    )

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result

    bus.ack(message["id"], success=False, error="fail-1")

    envelope = bus._queue.popleft()
    envelope.meta["available_at"] = int(time.time()) - 1
    bus._queue.append(envelope)

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message_retry = result

    bus.ack(message_retry["id"], success=False, error="fail-2")
    assert len(bus._queue) == 0

    dlq_path = tmp_path / "data" / "dlq.jsonl"
    records = dlq_path.read_text(encoding="utf-8").strip().splitlines()
    assert records

    record = json.loads(records[-1])
    assert record["event"] == "dlq"
    assert record["envelope"]["id"] == message_retry["id"]


def test_max_retries_exceeded_goes_to_dlq(tmp_path):
    bus = create_bus(tmp_path, max_retries=0)
    bus.register_agent("codex", object())

    assert bus.send_data(
        "codex",
        {"task": "ping"},
        sender="operator",
        msg_type="task",
        topic="ping",
    )

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result

    bus.ack(message["id"], success=False, error="fail-1")

    dlq_path = tmp_path / "data" / "dlq.jsonl"
    records = dlq_path.read_text(encoding="utf-8").strip().splitlines()
    assert records

    record = json.loads(records[-1])
    assert record["event"] == "dlq"
    assert record["envelope"]["id"] == message["id"]


def test_restore_queue_from_journal(tmp_path):
    bus = create_bus(tmp_path)
    bus.register_agent("codex", object())

    assert bus.send_data(
        "codex",
        {"task": "ping"},
        sender="operator",
        msg_type="task",
        topic="ping",
    )

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result

    restored = create_bus(tmp_path)
    restored.register_agent("codex", object())
    restored_result = restored.receive_data(timeout_s=0.01)
    assert restored_result is not None
    _, restored_message = restored_result
    assert restored_message["id"] == message["id"]


def test_restore_order_from_journal(tmp_path):
    journal = tmp_path / "data" / "queue.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)

    first = Envelope.new(
        to="codex",
        sender="operator",
        msg_type="task",
        topic="alpha",
        payload={"seq": 1},
    )
    second = Envelope.new(
        to="codex",
        sender="operator",
        msg_type="task",
        topic="beta",
        payload={"seq": 2},
    )

    records = [
        {"event": "send", "envelope": first.to_dict()},
        {"event": "send", "envelope": second.to_dict()},
    ]
    journal.write_text(
        "\n".join(json.dumps(record, ensure_ascii=True) for record in records) + "\n",
        encoding="utf-8",
    )

    bus = create_bus(tmp_path)
    bus.register_agent("codex", object())

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result
    assert message["id"] == first.id

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result
    assert message["id"] == second.id


def test_idempotency_duplicate_id_in_journal(tmp_path):
    journal = tmp_path / "data" / "queue.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)

    first = Envelope.new(
        to="codex",
        sender="operator",
        msg_type="task",
        topic="alpha",
        payload={"seq": 1},
    )
    first.id = "fixed-id"
    second = Envelope.new(
        to="codex",
        sender="operator",
        msg_type="task",
        topic="beta",
        payload={"seq": 2},
    )
    second.id = "fixed-id"

    records = [
        {"event": "send", "envelope": first.to_dict()},
        {"event": "send", "envelope": second.to_dict()},
    ]
    journal.write_text(
        "\n".join(json.dumps(record, ensure_ascii=True) for record in records) + "\n",
        encoding="utf-8",
    )

    bus = create_bus(tmp_path)
    bus.register_agent("codex", object())

    assert len(bus._queue) == 1
    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result
    assert message["id"] == "fixed-id"
    assert message["payload"]["seq"] == 2


def test_restore_inflight_from_journal(tmp_path):
    journal = tmp_path / "data" / "queue.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)

    inflight = Envelope.new(
        to="codex",
        sender="operator",
        msg_type="task",
        topic="recover",
        payload={"seq": 1},
    )

    record = {"event": "receive", "envelope": inflight.to_dict()}
    journal.write_text(json.dumps(record, ensure_ascii=True) + "\n", encoding="utf-8")

    bus = create_bus(tmp_path)
    bus.register_agent("codex", object())

    result = bus.receive_data(timeout_s=0.01)
    assert result is not None
    _, message = result
    assert message["id"] == inflight.id
    assert message["topic"] == "recover"
