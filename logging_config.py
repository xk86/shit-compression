import logging
import colorlog

class FunctionFilter(logging.Filter):
    def __init__(self, func_names):
        super().__init__()
        self.func_names = func_names

    def filter(self, record):
        return record.funcName in self.func_names

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
  functions_to_watch = ["get_mutated_segments", "adjust_segments_to_keyframes", "add_pass_through_segments", "split_video", "concatenate_segments", "encode_segments", "decode_segments"]
  #functions_to_watch = ["add_pass_through_segments"]

  ff = FunctionFilter(functions_to_watch)
  handler.addFilter(ff)

logger.addHandler(handler)
logger.setLevel(logging.DEBUG)