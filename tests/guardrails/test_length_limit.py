#!/usr/bin/env python3
"""
Тесты для проверки ограничений длины в Guardrails
"""
import pytest
from fastapi.testclient import TestClient
from langchain_api.main import app

client = TestClient(app)


def test_v1_chat_normal_length():
    """Тест нормальной длины сообщения"""
    content = "Привет! Как дела?"
    response = client.post("/v1/chat", json={"content": content})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["error"] is None


def test_v1_chat_too_long():
    """Тест слишком длинного сообщения (>4000 символов)"""
    content = "x" * 5000
    response = client.post("/v1/chat", json={"content": content})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_v1_chat_with_pii():
    """Тест сообщения с персональными данными"""
    content = "Мой email: john.doe@example.com и телефон: +7-999-123-45-67"
    response = client.post("/v1/chat", json={"content": content})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_v1_chat_with_profanity():
    """Тест сообщения с нецензурной лексикой"""
    content = "Это сообщение содержит нецензурные слова"
    response = client.post("/v1/chat", json={"content": content})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_v1_chat_empty_content():
    """Тест пустого сообщения"""
    response = client.post("/v1/chat", json={"content": ""})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_v1_chat_missing_content():
    """Тест отсутствующего поля content"""
    response = client.post("/v1/chat", json={})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data 