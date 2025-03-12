import logging
import colorlog


# Set up logging
logger = colorlog.getLogger(__name__)
if not logger.hasHandlers():
  handler = colorlog.StreamHandler()
  handler.setFormatter(colorlog.ColoredFormatter(
      '%(light_black)s%(asctime)s%(reset)s %(log_color)s%(levelname)s%(reset)s-%(purple)s%(funcName)s%(reset)s: %(message)s',
      log_colors={
          'DEBUG': 'cyan',
          'INFO': 'green',
          'WARNING': 'yellow',
          'ERROR': 'red',
          'CRITICAL': 'red,bg_white',
      }
  ))
  logger.addHandler(handler)
  logger.setLevel(logging.DEBUG)