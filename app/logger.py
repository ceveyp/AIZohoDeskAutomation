import logging
import sys


def disable_package_loggers():
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("langsmith.client").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("trafilatura").setLevel(logging.WARNING)


def setup_logging():
    """Configure root logging once (idempotent) so app loggers emit to stdout."""
    root = logging.getLogger()
    if not root.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.propagate = False
    root.setLevel(logging.DEBUG)
    disable_package_loggers()


def get_logger(name=None):
    return logging.getLogger(name or __name__)
