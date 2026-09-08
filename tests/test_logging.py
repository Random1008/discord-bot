import logging
import logging.handlers

import pytest

from utils.logging import configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)

    yield

    for handler in list(root.handlers):
        if handler not in original_handlers:
            root.removeHandler(handler)
            handler.close()
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_configure_logging_sets_level_and_handlers(tmp_path):
    log_file = tmp_path / "test.log"

    configure_logging(level="DEBUG", log_file=str(log_file))

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
