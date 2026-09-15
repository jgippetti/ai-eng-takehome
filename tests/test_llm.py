from framework.llm import OpenRouterClient, OpenRouterConfig


def test_request_body_includes_default_provider_and_reasoning_configuration() -> None:
    client = OpenRouterClient(OpenRouterConfig(api_key="test-key"))
    try:
        body = client._build_request_body(messages=[])
    finally:
        client._client.close()

    assert body["model"] == "openai/gpt-oss-120b"
    assert body["temperature"] == 0.0
    assert body["provider"] == {
        "order": ["cerebras"],
        "allow_fallbacks": False,
        "require_parameters": True,
    }
    assert body["reasoning"] == {"effort": "medium"}
