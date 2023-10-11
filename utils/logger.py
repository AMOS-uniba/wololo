import logging
import time
from utils import colour as c


class SightingFormatter(logging.Formatter):
    def __init__(self, fmt, timefmt, fmtc):
        super().__init__(fmt, timefmt, fmtc)

    def format(self, record):
        record.levelname = {
            'DEBUG':    c.debug,
            'INFO':     c.none,
            'WARNING':  c.warn,
            'ERROR':    c.ok,
            'CRITICAL': c.critical,
        }[record.levelname](record.levelname[:3])
        return super().format(record)

    def formatTime(self, record, fmt) -> str:
        ct = self.converter(record.created)
        return f"{time.strftime('%H:%M:%S', ct)}.{int(record.msecs):03d}"


def setup(name, *, output=None, fmt='{asctime} [{levelname}] {message}', timefmt='%Y-%m-%d %H:%M:%S', fmtc='{'):
    formatter = SightingFormatter(fmt='[{asctime}] {message}', timefmt=timefmt, fmtc=fmtc)

    if type(output) == str:
        handler = logging.FileHandler(output)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)

    return log
