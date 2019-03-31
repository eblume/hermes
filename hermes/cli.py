# -*- coding: utf-8 -*-

# NOTE ON TYPING:
# Types are DISABLED on this file. I tried to fill in as much as I could
# but in general click doesn't play nice with typing due to 'magic' variables.
# It's entirely possible to fix this, but it quickly becomes a lot of lines
# of code just to get the type system to quiet down...

import configparser
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional

from appdirs import user_config_dir

import click

from .clients.gcal import GoogleCalendarClient
from .timespan import date_parse


DEFAULT_CONFIG_FILE = Path(user_config_dir()) / "hermes.ini"

DEFAULT_CONFIG = {"hermes": {}}


class CallContext:
    def __init__(self, config: Optional[str] = None, debug: bool = False):
        self.debug = debug
        parser = configparser.ConfigParser()
        parser.read_dict(DEFAULT_CONFIG)
        if config:
            config_file = Path(config).resolve()
            if config_file.is_file():
                parser.read_file(config_file.open())
            else:
                raise ValueError("Invalid config file", config)
        elif DEFAULT_CONFIG_FILE.is_file():
            parser.read_file(DEFAULT_CONFIG_FILE.open())
        self.config = parser["hermes"]


class GCalOptions:
    def __init__(self, begins_at: Optional[str], finish_at: Optional[str]):
        self.begins_at: Optional[datetime] = date_parse(
            begins_at
        ) if begins_at else None
        self.finish_at: Optional[datetime] = date_parse(
            finish_at
        ) if finish_at else None
        self.client = GoogleCalendarClient(
            begins_at=self.begins_at, finish_at=self.finish_at
        )


pass_call_context = click.make_pass_decorator(CallContext)


@click.group()
@click.option("--debug/--no-debug", default=False, envvar="HERMES_DEBUG")
@click.option("--config", default=None, envvar="HERMES_CONFIG")
@click.pass_context
def cli(ctx, debug, config):
    ctx.obj = CallContext(config=config, debug=debug)


@cli.group()
@click.option(
    "--start-date",
    default=None,
    help='For clients that support it, specify this start date. Example: "02 March 2019 06:00-08:00"',
)
@click.option(
    "--finish-date",
    default=None,
    help='For clients that support it, specify this finish date. Example: "March 2nd 2019 8PM PST"',
)
@pass_call_context
def calendars(
    context: CallContext,
    start_date: Optional[str] = None,
    finish_date: Optional[str] = None,
) -> None:
    """Query and manipulate calendars"""
    context.gcal = GCalOptions(begins_at=start_date, finish_at=finish_date)


@calendars.command()
@pass_call_context
def list(context: CallContext) -> None:
    """List all known calendars, and their source."""
    click.secho("Google Calendars:", bold=True)
    click.secho("(This may ask you to authenticate via OAuth.)\n")
    for cal in context.gcal.client.calendars():
        click.echo(f"{cal['summary']} [{cal['id']}]")


@calendars.command()
@click.option("--calendar", default=None, help="Name of the calendar to use.")
@click.option("--calendar-id", default=None, help="ID of the calendar to use.")
@click.option(
    "--pretty/--no-pretty",
    default=True,
    help="Format the output to be nice for human consumption, or if not, be terse.",
)
@pass_call_context
def events(
    context: CallContext,
    calendar: Optional[str] = None,
    calendar_id: Optional[str] = None,
    pretty: bool = True,
) -> None:
    """List all events. Use options to narrow the search. If no calendar is specified, all calendars will be searched."""
    search_calendars: List[str] = []
    if calendar is None and calendar_id is None:
        search_calendars = [cal["id"] for cal in context.gcal.client.calendars()]
    elif calendar is not None and calendar_id is not None:
        click.echo(context.get_help())
        context.fail(
            "You must specify only one of --calendar and --calendar-id, or neither - not both."
        )
    elif calendar is not None:
        search_calendars = [context.gcal.client.calendar_by_name(calendar)["id"]]
    else:
        search_calendars = [calendar_id]

    if not search_calendars:
        context.fail("No calendars found on your account!")

    load_opts = {}
    if (
        pretty
        and context.gcal.begins_at is not None
        and context.gcal.finish_at is not None
    ):
        load_opts["progress"] = _make_progress_iter(context)

    for cal_id in search_calendars:
        cal_data = context.gcal.client.calendar(cal_id)
        if pretty:
            click.secho(f"{cal_data['summary']} [{cal_id}]", bold=True)
        timespan = context.gcal.client.load_gcal(cal_id, **load_opts)
        if pretty:
            click.secho(f"Found {len(timespan)} events.")
        for event in timespan.iter_tags():
            indent = "\t" if pretty else ""
            category = f" ({event.category.fullpath})" if pretty else ""
            click.echo(
                f"{indent}{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>{category}"
            )


def _make_progress_iter(context):
    def _item_show(event: Optional[Dict[str, Any]]) -> str:
        if event is None:
            return "<none>"
        else:
            start = event.get("start")
            start_dt = start.get("dateTime", start.get("date", None))
            if start_dt is None:
                return "<none>"
            else:
                return date_parse(start_dt).isoformat()

    progress_options = {
        "item_show_func": _item_show,
        "show_eta": False,
        "show_pos": True,
    }
    span = context.gcal.finish_at - context.gcal.begins_at
    progress_options["length"] = span.total_seconds()
    return partial(click.progressbar, **progress_options)


if __name__ == "__main__":
    cli()
