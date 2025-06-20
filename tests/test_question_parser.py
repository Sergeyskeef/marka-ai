import pytest
from scripts.question_parser import QuestionParser

@pytest.fixture
def parser():
    return QuestionParser()

def test_basic_questions(parser):
    """Тест базовых вопросов"""
    questions = [
        "Что ты умеешь?",
        "Какие у тебя режимы?",
        "Расскажи о себе",
        "Как ты работаешь?",
        "Что ты знаешь?",
        "Какие у тебя возможности?",
        "Как ты можешь помочь?",
        "Что ты можешь делать?",
        "Какие у тебя функции?",
        "Расскажи о своих возможностях"
    ]
    
    for question in questions:
        result = parser.parse(question)
        assert result['type'] in ['capabilities', 'modes', 'general']
        assert result['confidence'] > 0.7

def test_specific_questions(parser):
    """Тест специфических вопросов"""
    questions = {
        "Как ты обрабатываешь память?": "memory",
        "Как работает твоя песочница?": "sandbox",
        "Как ты анализируешь себя?": "self_analysis",
        "Какие у тебя есть команды?": "commands",
        "Как ты хранишь информацию?": "storage",
        "Как ты учишься?": "learning",
        "Как ты обновляешься?": "updates",
        "Как ты работаешь с документами?": "documents",
        "Как ты обрабатываешь ошибки?": "error_handling",
        "Как ты обеспечиваешь безопасность?": "security"
    }
    
    for question, expected_type in questions.items():
        result = parser.parse(question)
        assert result['type'] == expected_type
        assert result['confidence'] > 0.7

def test_unknown_questions(parser):
    """Тест неизвестных вопросов"""
    questions = [
        "Какой сегодня день?",
        "Сколько будет 2+2?",
        "Какая погода?",
        "Кто президент?",
        "Что нового?"
    ]
    
    for question in questions:
        result = parser.parse(question)
        assert result['type'] == 'unknown'
        assert result['confidence'] < 0.5

def test_question_variations(parser):
    """Тест вариаций вопросов"""
    base_questions = {
        "Что ты умеешь?": [
            "Расскажи, что ты умеешь",
            "Какие у тебя есть возможности?",
            "Что ты можешь?",
            "Какие у тебя функции?",
            "Что ты знаешь делать?",
            "Какие у тебя способности?",
            "Что ты умеешь делать?",
            "Какие у тебя умения?",
            "Что ты можешь делать?",
            "Какие у тебя навыки?"
        ]
    }
    
    for base, variations in base_questions.items():
        base_result = parser.parse(base)
        for variation in variations:
            var_result = parser.parse(variation)
            assert var_result['type'] == base_result['type']
            assert abs(var_result['confidence'] - base_result['confidence']) < 0.2

def test_performance(parser):
    """Тест производительности парсера"""
    import time
    
    # Генерируем 1000 случайных вопросов
    import random
    questions = [
        "Что ты умеешь?",
        "Как работает память?",
        "Что такое песочница?",
        "Как ты учишься?",
        "Какие у тебя режимы?",
        "Как ты анализируешь?",
        "Что ты знаешь?",
        "Как ты работаешь?",
        "Какие у тебя возможности?",
        "Как ты можешь помочь?"
    ] * 100
    
    random.shuffle(questions)
    
    # Замеряем время
    start_time = time.time()
    for question in questions:
        parser.parse(question)
    end_time = time.time()
    
    # Проверяем, что обработка 1000 вопросов занимает не более 1 секунды
    assert end_time - start_time < 1.0

def test_error_handling(parser):
    """Тест обработки ошибок"""
    # Тест с пустым вопросом
    result = parser.parse("")
    assert result['type'] == 'unknown'
    assert result['confidence'] == 0.0
    
    # Тест с очень длинным вопросом
    long_question = "Что ты умеешь? " * 1000
    result = parser.parse(long_question)
    assert result['type'] in ['capabilities', 'unknown']
    
    # Тест с некорректными символами
    result = parser.parse("Что ты умеешь? " + "".join(chr(i) for i in range(1000)))
    assert result['type'] in ['capabilities', 'unknown'] 