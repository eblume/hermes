# -*- coding: utf-8 -*-
from hermes.clients.gcal import GoogleCalendarTimeSpan

gcal = GoogleCalendarTimeSpan()
for tag in gcal.iter_tags():
    print(tag.name)
