import logging
import time
from utils import colour as c


class SightingFormatter(logging.Formatter):
    def __init__(self):
        super().__init__('{message}', "%H:%M:%S", '{')

    def format(self, record):
        record.levelname = {
            'DEBUG':    c.debug,
            'INFO':     c.none,
            'WARNING':  c.warn,
            'ERROR':    c.err,
            'CRITICAL': c.critical,
        }[record.levelname](record.levelname[:3])

        return super().format(record)

    def formatTime(self, record, fmt) -> str:
        ct = self.converter(record.created)
        return f"{time.strftime('%H:%M:%S', ct)}.{int(record.msecs):03d}"


def setup(name, **kwargs):
    formatter = SightingFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)

    return log
