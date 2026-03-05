from interfaces.com_agent_interface import ComAgent


def test_comm_envelope_contains_transport_metadata() -> None:
    c = ComAgent()
    c.register_agent("worker", object())
    c.set_credit("worker", 1)

    payload = {"intent": "ping", "context": {"task_id": "t-1"}}
    assert c.send_data("worker", payload)

    recipient, out = c.receive_data()
    assert recipient == "worker"
    assert out.get("intent") == "ping"
    transport = out.get("_transport", {})
    assert transport.get("msg_type") == "TASK"


def test_credit_backpressure_blocks_when_zero_and_allows_after_refill() -> None:
    c = ComAgent()
    c.register_agent("worker", object())
    c.set_credit("worker", 0)

    assert c.send_data("worker", {"intent": "ping"}) is False

    c.add_credit("worker", 1)
    assert c.get_credit("worker") == 1
    assert c.send_data("worker", {"intent": "ping"}) is True
