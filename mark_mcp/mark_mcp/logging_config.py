import logging
from logging.handlers import RotatingFileHandler
from .config import settings


def setup_logging() -> None:
	logger = logging.getLogger()
	if logger.handlers:
		return
	logger.setLevel(logging.INFO)

	fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

	sh = logging.StreamHandler()
	sh.setFormatter(fmt)
	logger.addHandler(sh)

	try:
		fh = RotatingFileHandler(settings.log_file, maxBytes=5_000_000, backupCount=3)
		fh.setFormatter(fmt)
		logger.addHandler(fh)
	except Exception:
		pass
