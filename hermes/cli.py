# -*- coding: utf-8 -*-

# NOTE ON TYPING:
# Types are DISABLED on this file. I tried to fill in as much as I could
# but in general click doesn't play nice with typing due to 'magic' variables.
# It's entirely possible to fix this, but it quickly becomes a lot of lines
# of code just to get the type system to quiet down...

import configparser
from datetime import datetime, timedelta, timezone
from functools import partial
from importlib.util import module_from_spec, spec_from_file_location
import inspect
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from appdirs import user_config_dir
import click
from dateutil.tz import tzlocal

from .clients.gcal import GoogleCalendarClient, GoogleCalendarTimeSpan
from .schedule import dates_between, Schedule
from .span import Span
from .tag import Category
from .timespan import date_parse


DEFAULT_CONFIG_FILE = Path(user_config_dir()) / "hermes" / "hermes.ini"

DEFAULT_CONFIG = {"hermes": {"gcal calendar": ""}}

PYTHON_LIST = list  # DUMB: 'list' is the command word, but click needs that...


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
    def __init__(self, begins_at: Optional[datetime], finish_at: Optional[datetime]):
        self.begins_at = begins_at
        self.finish_at = finish_at
        self.client = GoogleCalendarClient(
            begins_at=self.begins_at, finish_at=self.finish_at
        )


pass_call_context = click.make_pass_decorator(CallContext)


@click.group()
@click.option("--debug/--no-debug", default=False, envvar="HERMES_DEBUG")
@click.option(
    "--config", default=None, type=click.Path(exists=True), envvar="HERMES_CONFIG"
)
@click.pass_context
def cli(ctx, debug, config):
    ctx.obj = CallContext(
        config=None if config is None else click.format_filename(config), debug=debug
    )


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
@click.option(
    "--today",
    is_flag=True,
    help="Shortcut for --start-date and --finish-date to match the current local day.",
)
@click.option(
    "--tomorrow",
    is_flag=True,
    help='Shortcut for --start-date and --finish-date to match the current local "tomorrow".',
)
@pass_call_context
def calendars(
    context: CallContext,
    start_date: Optional[str] = None,
    finish_date: Optional[str] = None,
    today: bool = False,
    tomorrow: bool = False,
) -> None:
    """Query and manipulate calendars"""
    if today:
        if tomorrow or start_date or finish_date:
            context.Fail("You must not specify multiple calendar spans.")
        start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tzlocal()
        )
        stop = start + timedelta(days=1, microseconds=-1)  # Last microsecond of the day
        context.gcal = GCalOptions(begins_at=start, finish_at=stop)
    elif tomorrow:
        if today or start_date or finish_date:
            context.Fail("You must not specify multiple calendar spans.")
        start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tzlocal()
        ) + timedelta(days=1)
        stop = start + timedelta(days=1, microseconds=-1)  # Last microsecond of the day
        context.gcal = GCalOptions(begins_at=start, finish_at=stop)
    else:
        begins_at: Optional[datetime] = date_parse(start_date) if start_date else None
        finish_at: Optional[datetime] = date_parse(finish_date) if finish_date else None
        context.gcal = GCalOptions(begins_at=begins_at, finish_at=finish_at)


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

    search_calendars = _make_search_cals(context, calendar, calendar_id)

    load_opts = {}
    if pretty and context.gcal.client.span.is_finite():
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


@calendars.command()
@click.option("--calendar", default=None, help="Name of the calendar to use.")
@click.option("--calendar-id", default=None, help="ID of the calendar to use.")
@click.option(
    "--yes",
    is_flag=True,
    help="Do not prompt to confirm, just delete the events. (I like to live dangerously.)",
)
@pass_call_context
def clear(context, calendar, calendar_id, yes):
    calendars = _make_search_cals(context, calendar, calendar_id)
    if len(calendars) != 1:
        raise click.UsageError(
            "When clearing a schedule, you must specify one (and only one) calendar."
        )
    target_calendar_id = calendars[0]

    gcal = GoogleCalendarTimeSpan(
        client=context.gcal.client, calendar_id=target_calendar_id
    )
    click.echo("Events:")
    for event in gcal.iter_tags():
        click.echo(
            f"\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}> ({event.category.fullpath}"
        )

    if not yes:
        click.confirm(
            "Do you want to delete these events? (CANNOT BE UNDONE!)", abort=True
        )

    gcal.remove_events()
    gcal.flush()


@calendars.command()
@click.option("--calendar", default=None, help="Name of the calendar to use.")
@click.option("--calendar-id", default=None, help="ID of the calendar to use.")
@click.option(
    "--check-calendar",
    default=None,
    help="Check this calendar first and don't schedule events on top of it.",
    multiple=True,
)
@click.option(
    "--check-calendar-id",
    default=None,
    help="Check this calendar first and don't schedule events on top of it.",
    multiple=True,
)
@click.option(
    "--check-this-calendar/--no-check-this-calendar",
    default=True,
    help="Check the same calendar Hermes is scheduling with and don't schedule events on top of it. You must also set --no-replan.",
)
@click.option(
    "--replan/--no-replan",
    default=True,
    help="Delete any existing Hermes events that the specified plans already define, and replan them. By default, works only on future events (see --replan-past).",
)
@click.option(
    "--replan-past/--no-replan-past",
    default=False,
    help="Allow --replan to delete past events. Events that have already begun but not yet finished are considered 'past events'.",
)
@click.argument("schedules", type=click.Path(exists=True), nargs=-1)
@pass_call_context
def schedule(
    context,
    replan,
    replan_past,
    check_this_calendar,
    calendar=None,
    calendar_id=None,
    schedules=None,
    check_calendar=None,
    check_calendar_id=None,
):
    """Import the specified schedule files (which are python files) and populate
    the specified calendar according to schedule definitions in those files."""

    if not schedules:
        raise click.UsageError("You must specify at least one schedule file.")

    if replan and not check_this_calendar:
        raise click.UsageError(
            "--no-check-this-calendar requires you also set --no-replan explicitly. (Replanning requires checking this calendar.)"
        )

    if replan_past and not replan:
        raise click.UsageError("--replan-past requires that you set --replan")

    calendars = _make_search_cals(context, calendar, calendar_id)
    if len(calendars) != 1:
        raise click.UsageError(
            "When scheduling, you must specify one (and only one) calendar."
        )
    target_calendar_id = calendars[0]

    if not context.gcal.client.span.is_finite():
        raise click.UsageError(
            "You must specify both a start and finish time when scheduling. (You can't plan eternity... yet.)"
        )
    gcal = GoogleCalendarTimeSpan(
        client=context.gcal.client, calendar_id=target_calendar_id, load_events=False
    )
    base_category = Category("Hermes", None) / "Daily Schedule"

    pre_existing_calendars = PYTHON_LIST(check_calendar_id)
    for calendar_name in check_calendar:
        pre_existing_calendars.append(
            context.gcal.client.calendar_by_name(calendar_name)["id"]
        )
    if check_this_calendar:
        pre_existing_calendars.append(target_calendar_id)

    now = datetime.now(timezone.utc)
    if replan_past:
        replan_span = Span(
            begins_at=context.gcal.begins_at, finish_at=context.gcal.finish_at
        )
    else:
        if context.gcal.finish_at <= now:
            raise click.UsageError(
                "Cannot reschedule the past by default. See --reschedule-past."
            )
        replan_span = Span(
            begins_at=max(context.gcal.begins_at, now), finish_at=context.gcal.finish_at
        )

    # When replan'ing, find the replanned events, so we can delete them later
    replanned_events = set()
    # TODO - possible race condition caused by loading this gcal twice. Cache?
    if replan:
        for event in context.gcal.client.load_gcal(target_calendar_id).iter_tags():
            if event.valid_from >= replan_span.begins_at:
                replanned_events |= {event}

    pre_existing_events = []
    for calendar_id in set(pre_existing_calendars):
        for event in context.gcal.client.load_gcal(calendar_id).iter_tags():
            if (
                replan
                and calendar_id == target_calendar_id
                and event in replanned_events
            ):
                continue
            pre_existing_events.append(event)

    if replan and replanned_events:
        click.secho("Removing previously planned events (as per --replan)", bold=True)
        for event in replanned_events:
            click.secho(
                f"\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>"
            )
            gcal.remove_tag(event)
        click.secho("\n")

    for schedule_name, schedule_def in _load_schedules(schedules):
        click.echo(f"Scheduling with {schedule_name}", bold=True)
        category = base_category / (schedule_def.NAME or schedule_name)
        for day in dates_between(
            Span(begins_at=context.gcal.begins_at, finish_at=context.gcal.finish_at)
        ):
            click.echo(f"\ton {day.isoformat()}")
            schedule = schedule_def()
            schedule.schedule()
            if pre_existing_events:
                schedule.pre_existing_events(pre_existing_events)
            try:
                events = schedule.populate(Span.from_date(day))
            except ValueError:
                click.secho(
                    "Error: The scheduling problem was unfeasible. Try relaxing your constraints. Sorry about this!",
                    bold=True,
                )
                click.secho(
                    "(Note that this does not necessarily mean that it was IMPOSSIBLE - scheduling is hard!)"
                )
                click.secho("Nothing was written to your calendar!")
                sys.exit(3)
            for event in events:
                click.echo(
                    f"\t\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>"
                )
                gcal.insert_tag(event.recategorize(category))
    gcal.flush()


def _make_search_cals(context, calendar, calendar_id) -> List[str]:
    search_calendars: List[str] = []
    if calendar is None and calendar_id is None:
        if context.config.get("gcal calendar"):
            # Retrieve calendar from config if set in config
            search_calendars = [
                context.gcal.client.calendar_by_name(
                    context.config.get("gcal calendar")
                )["id"]
            ]
        else:
            search_calendars = [cal["id"] for cal in context.gcal.client.calendars()]
    elif calendar is not None and calendar_id is not None:
        click.echo(context.get_help())
        raise click.UsageError(
            "You must specify only one of --calendar and --calendar-id, or neither - not both."
        )
    elif calendar is not None:
        search_calendars = [context.gcal.client.calendar_by_name(calendar)["id"]]
    else:
        search_calendars = [calendar_id]

    if not search_calendars:
        raise click.UsageError("No matching calendars found on your account!")

    return search_calendars


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
    progress_options["length"] = (
        context.gcal.finish_at - context.gcal.begins_at
    ).total_seconds()
    return partial(click.progressbar, **progress_options)


def _load_schedules(schedules):
    for i, schedule in enumerate(schedules):
        spec = spec_from_file_location(f"user_supplied_module_{i}", schedule)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        for clsname, definition in inspect.getmembers(module):
            if inspect.isclass(definition) and issubclass(definition, Schedule):
                if hasattr(definition, "schedule"):
                    yield clsname, definition


if __name__ == "__main__":
    cli()
