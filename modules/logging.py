import logging
import os
import gzip
import shutil
from logging.handlers import RotatingFileHandler
from .config import LOGS_DIR


# Custom RotatingFileHandler with compression
class CompressedRotatingFileHandler(RotatingFileHandler):
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename(
                    "%s.%d.gz" % (self.baseFilename, i)
                )
                dfn = self.rotation_filename(
                    "%s.%d.gz" % (self.baseFilename, i + 1)
                )
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
            dfn = self.rotation_filename(self.baseFilename + ".1")
            if os.path.exists(dfn):
                os.remove(dfn)
            if os.path.exists(self.baseFilename):
                os.rename(self.baseFilename, dfn)
                with open(dfn, 'rb') as f_in:
                    with gzip.open(dfn + '.gz', 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(dfn)
        self.stream = self._open()


def setup_logging():
    """Configure logging with file rotation and console output."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    os.makedirs(LOGS_DIR, exist_ok=True)

    file_handler = CompressedRotatingFileHandler(
        filename=os.path.join(LOGS_DIR, "bot.log"),
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    logger.info("Logging configured successfully")
