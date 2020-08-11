import datetime as dt

import pytz


def get_now() -> dt.datetime:
    return dt.datetime.now(pytz.UTC).astimezone()
