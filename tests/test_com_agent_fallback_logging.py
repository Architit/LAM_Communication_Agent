from interfaces.com_agent_interface import ComAgent


def test_com_agent_roundtrip_without_lam_logging_dependency() -> None:
    c = ComAgent()
    c.register_agent("worker", object())
    c.set_credit("worker", 1)

    assert c.send_data("worker", {"intent": "ping", "context": {"task_id": "t-1"}})
    recipient, payload = c.receive_data()

    assert recipient == "worker"
    assert payload.get("intent") == "ping"
    assert c.send_data("missing", {"intent": "ping"}) is False
