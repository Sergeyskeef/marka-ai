import logging


def setup_logger(name: str = None, level: int = logging.INFO) -> logging.Logger:
    """Настраивает логгер с указанным именем и уровнем логирования.

    Args:
        name: Имя логгера (опционально)
        level: Уровень логирования (по умолчанию INFO)

    Returns:
        logging.Logger: Настроенный логгер
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Если у логгера уже есть обработчики, не добавляем новые
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
