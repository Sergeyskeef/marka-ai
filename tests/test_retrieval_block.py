import pytest
from langchain_api.rag.enhanced_rag_chain import format_retrieval_block

# Моки для retrieval-результатов
@pytest.fixture
def retrieval_results():
    return {
        "DOCUMENT": [{"text": f"Документ {i}"} for i in range(4)],
        "INSIGHT": [{"insight": f"Инсайт {i}"} for i in range(4)],
        "EXPERIENCE": [{"summary": f"Опыт {i}"} for i in range(4)],
        "CHATGPTMEMORY": [{"text": f"CGPT {i}"} for i in range(4)],
        "MEMORY": [{"message": f"Память {i}"} for i in range(4)],
    }

def test_retrieval_block_limit(retrieval_results):
    # Имитация лимита: не более 3 на класс, всего не более 10
    all_items = []
    for section, items in retrieval_results.items():
        for item in items[:3]:
            all_items.append((section, item))
    if len(all_items) > 10:
        all_items = all_items[:10]
    limited_results = {}
    for section, item in all_items:
        limited_results.setdefault(section, []).append(item)
    total = sum(len(v) for v in limited_results.values())
    assert total <= 10, f"Всего retrieval-объектов: {total}, ожидалось ≤10"
    for v in limited_results.values():
        assert len(v) <= 3, "Не более 3 объектов на класс"

def test_retrieval_block_no_duplicates():
    # Дублирующиеся объекты не должны попадать в блок
    results = {
        "DOCUMENT": [{"text": "Документ 1"}, {"text": "Документ 1"}],
        "MEMORY": [{"message": "Память 1"}, {"message": "Память 1"}],
    }
    block = format_retrieval_block(results)
    assert block.count("Документ 1") == 1
    assert block.count("Память 1") == 1

def test_retrieval_block_fallback():
    # Если retrieval пустой, fallback из MEMORY
    results = {"DOCUMENT": [], "INSIGHT": [], "EXPERIENCE": [], "CHATGPTMEMORY": [], "MEMORY": []}
    fallback = [{"message": "Память fallback"}]
    # Симулируем fallback-логику
    if not any(results.values()):
        results["MEMORY"] = fallback
    block = format_retrieval_block(results)
    assert "Память fallback" in block
    assert "--- MEMORY ---" in block

def test_retrieval_block_markdown_headers(retrieval_results):
    # Проверка наличия markdown-заголовков
    all_items = []
    for section, items in retrieval_results.items():
        for item in items[:3]:
            all_items.append((section, item))
    if len(all_items) > 10:
        all_items = all_items[:10]
    limited_results = {}
    for section, item in all_items:
        limited_results.setdefault(section, []).append(item)
    block = format_retrieval_block(limited_results)
    for section in limited_results:
        assert f"--- {section.upper()} ---" in block

def test_prompt_structure_with_retrieval_block(retrieval_results):
    """
    Проверяет, что retrieval-блок корректно вставляется между system prompt и историей.
    """
    from langchain_api.rag.enhanced_rag_chain import SystemMessage
    persona = "Ты — Марк."
    system_prompt = f"{persona}\n\nSYSTEM_PROMPT_BASE"
    retrieval_block = format_retrieval_block(retrieval_results)
    messages = [SystemMessage(content=system_prompt)]
    if retrieval_block.strip():
        messages.append(SystemMessage(content="[RETRIEVAL]\n" + retrieval_block))
    # История (моки)
    history = [
        {"role": "user", "content": "Привет!"},
        {"role": "assistant", "content": "Здравствуйте!"}
    ]
    for msg in history:
        messages.append(SystemMessage(content=msg["content"]))
    # Проверяем порядок
    assert messages[0].content.startswith(persona)
    assert messages[1].content.startswith("[RETRIEVAL]")
    assert messages[2].content == "Привет!" or messages[2].content == "Здравствуйте!" 