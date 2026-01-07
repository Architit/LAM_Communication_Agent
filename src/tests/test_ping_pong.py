import json

from codex_agent.core import Core

from src.interfaces.com_agent_interface import ComAgent


def test_ping_pong_ack():
    codex = Core()
    comm = ComAgent()

    comm.register_agent("codex", codex)
    comm.register_agent("operator", object())

    assert comm.send_data(
        "codex",
        {"msg": "ping"},
        sender="operator",
        msg_type="task",
        topic="ping",
    )

    result = comm.receive_data(timeout_s=1.0)
    assert result is not None
    _, message = result

    reply_payload = codex.answer(message["payload"]["msg"])
    assert isinstance(reply_payload, dict)
    comm.ack(message["id"], success=True)

    assert comm.send_data(
        "operator",
        {"reply": reply_payload},
        sender="codex",
        msg_type="reply",
        topic="ping",
    )

    result = comm.receive_data(timeout_s=1.0)
    assert result is not None
    _, reply_message = result
    assert reply_message["payload"]["reply"] == reply_payload

    journal_path = comm._journal_dir / "queue.jsonl"
    records = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert records

    events = [json.loads(line)["event"] for line in records]
    assert "send" in events
    assert "receive" in events
    assert "ack" in events

    first_send = events.index("send")
    first_receive = events.index("receive")
    first_ack = events.index("ack")
    assert first_send < first_receive < first_ack
