import logging


class _TaskLogger(logging.LoggerAdapter):
    def __init__(self, task_name: str):
        super().__init__(logging.getLogger(), {"task_name": task_name})


MAIN = _TaskLogger("MAIN")
INIT = _TaskLogger("INIT")
MPD = _TaskLogger("MPD")
PAST = _TaskLogger("PAST")
SEARCH = _TaskLogger("SEARCH")
LIVE_POLL = _TaskLogger("LIVE-POLL")
LIVE_DL = _TaskLogger("LIVE-DL")
MERGE = _TaskLogger("MERGE")
SUMMARY = _TaskLogger("SUMMARY")
FFPROBE = _TaskLogger("FFPROBE")
