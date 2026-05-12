from unittest.mock import MagicMock

from pa.agent.loop import ChatState, chat_once


def test_chat_once_appends_history_and_returns_reply() -> None:
    fake_block = MagicMock(type="text", text="hi there")
    fake_resp = MagicMock(content=[fake_block])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    state = ChatState()
    reply = chat_once(state, "hello", client=fake_client)

    assert reply == "hi there"
    assert [t.role for t in state.history] == ["user", "assistant"]
    assert state.history[0].content == "hello"


def test_chat_once_keeps_full_history_across_turns() -> None:
    def make_client(text: str) -> MagicMock:
        c = MagicMock()
        c.messages.create.return_value = MagicMock(content=[MagicMock(type="text", text=text)])
        return c

    state = ChatState()
    chat_once(state, "one", client=make_client("ack-one"))
    chat_once(state, "two", client=make_client("ack-two"))

    assert [t.content for t in state.history] == ["one", "ack-one", "two", "ack-two"]
