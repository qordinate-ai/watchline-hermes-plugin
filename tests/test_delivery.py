from watchline_hermes_plugin.delivery import format_delivery, parse_delivery_channel


def test_match_delivery_text_contains_intent_and_event():
    text = format_delivery(
        {
            "type": "watchline.match",
            "intent": "emails from my boss",
            "event": {"subject": "Launch plan"},
        },
    )

    assert "Matched event with user intent: emails from my boss" in text
    assert '"subject": "Launch plan"' in text


def test_parse_default_delivery_channel():
    channel = parse_delivery_channel("main")

    assert channel.is_main


def test_parse_explicit_delivery_channel():
    channel = parse_delivery_channel("telegram:123:456")

    assert not channel.is_main
    assert channel.platform == "telegram"
    assert channel.chat_id == "123"
    assert channel.thread_id == "456"
