import datetime as dt
from .utils import immutable


@immutable
class Tag:
    '''A tag on the timeline. Could be an event, could be an annotation.'''
    name: str
    valid_from: dt.datetime
    valid_to: dt.datetime
