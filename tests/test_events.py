"""Event system."""
import uuid

from pyre_starlette import Event, event


def _unique(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_listen_and_emit_by_name():
    name = _unique("evt")
    received = []

    @event.listen(name)
    def handler(data):
        received.append(data)

    event.emit(name, {"k": 1})
    assert received == [{"k": 1}]


def test_emit_event_object():
    name = _unique("evt")
    received = []

    @event.listen(name)
    def handler(data):
        received.append(data)

    event.emit(Event(name, {"k": 2}))
    assert received == [{"k": 2}]


def test_listener_arity_is_respected():
    name = _unique("evt")
    received = []

    @event.listen(name)
    def no_args():
        received.append("noargs")

    @event.listen(name)
    def one_arg(data):
        received.append(("one", data))

    @event.listen(name)
    def two_args(event_name, data):
        received.append(("two", event_name, data))

    event.emit(name, 42)
    assert "noargs" in received
    assert ("one", 42) in received
    assert ("two", name, 42) in received


def test_listen_for_alias():
    name = _unique("evt")
    received = []

    @event.listen_for(name)
    def handler(data):
        received.append(data)

    event.emit(name, "x")
    assert received == ["x"]


def test_emit_without_parameters_raises():
    import pytest

    with pytest.raises(RuntimeError):
        event.emit()


def test_event_repr():
    evt = Event("name", {"a": 1})
    assert "name" in repr(evt)
    assert evt.data == {"a": 1}
