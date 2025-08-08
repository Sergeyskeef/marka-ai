from utils.openai_proxy_client import chat_model


def test_roundtrip():
    llm = chat_model(model="gpt-4.1-mini", temperature=0.0, timeout=15)
    response = llm.invoke("ping")
    assert hasattr(response, "content")
    assert isinstance(response.content, str)
    assert len(response.content) > 0
