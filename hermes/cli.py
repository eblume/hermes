# -*- coding: utf-8 -*-

# NOTE ON TYPING:
# Types are DISABLED on this file. I tried to fill in as much as I could
# but in general click doesn't play nice with typing due to 'magic' variables.
# It's entirely possible to fix this, but it quickly becomes a lot of lines
# of code just to get the type system to quiet down...

import configparser
from datetime import datetime, timedelta
from functools import partial
from importlib.util import module_from_spec, spec_from_file_location
import inspect
from operator import attrgetter
from pathlib import Path
import random
from typing import Any, Dict, Optional

from appdirs import user_config_dir
import click
from dateutil.tz import tzlocal

from .chores import ChoreStore
from .clients.gcal import GoogleCalendarClient, GoogleCalendarTimeSpan
from .schedule import Schedule
from .span import Span
from .timespan import date_parse


DEFAULT_CONFIG_FILE = Path(user_config_dir()) / "hermes" / "hermes.ini"

DEFAULT_CONFIG = {"hermes": {"gcal calendar": ""}}


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
    def __init__(self, begins_at, finish_at):
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
    help="Shortcut for --start-date and --finish-date to match the current local day. Chosen by default when no other range is given.",
)
@click.option(
    "--tomorrow",
    is_flag=True,
    help='Shortcut for --start-date and --finish-date to match the current local "tomorrow".',
)
@click.option("--calendar", default=None, help="Name of the calendar to use.")
@click.option("--calendar-id", default=None, help="ID of the calendar to use.")
@pass_call_context
def calendars(
    context: CallContext,
    start_date: Optional[str] = None,
    finish_date: Optional[str] = None,
    calendar: Optional[str] = None,
    calendar_id: Optional[str] = None,
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
    elif tomorrow:
        if today or start_date or finish_date:
            context.Fail("You must not specify multiple calendar spans.")
        start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tzlocal()
        ) + timedelta(days=1)
        stop = start + timedelta(days=1, microseconds=-1)  # Last microsecond of the day
    elif start_date and finish_date:
        start = date_parse(start_date)
        stop = date_parse(finish_date)
    elif start_date or finish_date:
        context.Fail("You must specify both a start and finish date.")
    else:
        # assume 'today'
        start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tzlocal()
        )
        stop = start + timedelta(days=1, microseconds=-1)  # Last microsecond of the day

    context.gcal = GCalOptions(begins_at=start, finish_at=stop)
    context.target_calendar_id = _make_target_cal(context, calendar, calendar_id)


@calendars.command(name="list")
@pass_call_context
def callist(context: CallContext) -> None:
    """List all known calendars, and their source."""
    click.secho("Google Calendars:", bold=True)
    for cal in context.gcal.client.calendars():
        click.secho(f"{cal['summary']} [{cal['id']}]")


@calendars.command()
@click.option(
    "--pretty/--no-pretty",
    default=True,
    help="Format the output to be nice for human consumption, or if not, be terse.",
)
@pass_call_context
def events(context: CallContext, pretty: bool = True) -> None:
    """List all events. Use options to narrow the search. If no calendar is specified, all calendars will be searched."""

    if context.target_calendar_id is None:
        search_cals = [calendar["id"] for calendar in context.gcal.client.calendars()]
    else:
        search_cals = [context.target_calendar_id]

    load_opts = {}
    if pretty and context.gcal.client.span.is_finite():
        load_opts["progress"] = _make_progress_iter(context)

    for cal_id in search_cals:
        cal_data = context.gcal.client.calendar(cal_id)
        if pretty:
            click.secho(f"{cal_data['summary']} [{cal_id}]", bold=True)
        timespan = context.gcal.client.load_gcal(cal_id, **load_opts)
        if pretty:
            click.secho(f"Found {len(timespan)} events.")
        for event in timespan.iter_tags():
            indent = "\t" if pretty else ""
            category = f" ({event.category.fullpath})" if pretty else ""
            click.secho(
                f"{indent}{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>{category}"
            )


@calendars.command()
@click.option(
    "--yes",
    is_flag=True,
    help="Do not prompt to confirm, just delete the events. (I like to live dangerously.)",
)
@pass_call_context
def clear(context, yes):
    if context.target_calendar_id is None:
        raise click.UsageError(
            "When clearing a schedule, you must specify one (and only one) calendar."
        )
    gcal = GoogleCalendarTimeSpan(
        client=context.gcal.client, calendar_id=context.target_calendar_id
    )
    click.secho("Events:")
    for event in gcal.iter_tags():
        click.secho(
            f"\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}> ({event.category.fullpath}"
        )

    if not yes:
        click.confirm(
            "Do you want to delete these events? (CANNOT BE UNDONE!)", abort=True
        )

    gcal.remove_events()
    gcal.flush()


@calendars.command(name="next")
@click.option(
    "--slots", type=int, default=5, help="The number of events to choose from."
)
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
@click.argument("schedules", type=click.Path(exists=True), nargs=-1)
@pass_call_context
def whatsnext(context, schedules, slots, check_calendar, check_calendar_id):
    if context.target_calendar_id is None:
        raise click.UsageError(
            "When clearing a schedule, you must specify one (and only one) calendar."
        )
    gcal = GoogleCalendarTimeSpan(
        client=context.gcal.client, calendar_id=context.target_calendar_id
    )

    slot_list = []
    slot_schedules = {}
    events = [e for e in gcal.iter_tags()]
    now = datetime.now(tzlocal())
    # TODO - the notion of 'upcoming' as relates to currently in-progress events is tricky
    upcoming_events = sorted(
        (e for e in events if e.valid_to >= now), key=attrgetter("valid_from")
    )

    if now >= context.gcal.finish_at:
        raise click.UsageError(
            "Your target date range for scheduling must be in the future."
        )

    if upcoming_events:
        slot_list.append(upcoming_events[0].name)
        slot_schedules[slot_list[0]] = upcoming_events

    schedules = {
        schedule_name: schedule_def
        for schedule_name, schedule_def in _load_schedules(schedules)
    }

    pre_existing_calendars = list(check_calendar_id)
    for calendar_name in check_calendar:
        pre_existing_calendars.append(
            context.gcal.client.calendar_by_name(calendar_name)["id"]
        )

    loaded_calendars = [
        context.gcal.client.load_gcal(cal) for cal in pre_existing_calendars
    ]

    span = Span(
        begins_at=max(context.gcal.begins_at, now), finish_at=context.gcal.finish_at
    )

    unfeasible_count = 0
    while len(slot_list) < slots:
        if unfeasible_count >= 3:
            break
        if not schedules:  # "degrade gracefully", as per click's suggestion
            break

        # TODO - categories
        schedule_name = random.choice(
            list(schedules.keys())
        )  # TODO: random? or in order? or somehow all-together? Hmm.
        schedule = schedules[schedule_name]()
        schedule.schedule()

        no_pick_first = {
            e.name: now for e in schedule.events.values() if e.name in slot_list
        }
        if all(key in no_pick_first for key in schedule.events.keys()):
            break  # We've run out of things to try

        try:
            plan = schedule.populate(
                span, loaded_calendars, no_pick_first=no_pick_first
            )
        except ValueError as e:
            print(e)
            unfeasible_count += 1
            continue

        new_events = sorted(plan.iter_tags(), key=attrgetter("valid_from"))
        if new_events:
            slot_list.append(new_events[0].name)
            slot_schedules[new_events[0].name] = new_events
        else:
            unfeasible_count += 1

    # Display choices
    if not slot_list:
        click.secho(
            "No valid events could be found for this period and these schedules.",
            bold=True,
        )
        return
    click.secho("Choices:", bold=True)
    for i, event in enumerate(slot_list):
        click.secho(f"\t{i}:\t{event}")
        # TODO - show whole plan, somehow? Ugly UI.
        for other in slot_schedules[slot_list[i]]:
            click.secho(
                f"\t\t- {other.name} <{other.valid_from.isoformat()},{other.valid_to.isoformat()}>"
            )

    choice = click.prompt(
        "Please enter your choice (ctrl+c to cancel):",
        default=0,
        type=click.Choice(list(str(i) for i in range(len(slot_list)))),
    )

    chosen_schedule = slot_schedules[slot_list[int(choice)]]

    if sorted(upcoming_events, key=attrgetter("valid_from")) != chosen_schedule:
        click.secho("Removing previously scheduled events:", bold=True)
        for event in upcoming_events:
            click.secho(
                f"\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>"
            )
            gcal.remove_tag(event)

        click.secho("Adding events:", bold=True)
        for event in chosen_schedule:
            click.secho(
                f"\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>"
            )
            gcal.insert_tag(event)
        gcal.flush()
    else:
        click.secho("The current schedule has been chosen, no changes made.")


@cli.group()
@pass_call_context
@click.option(
    "--store",
    type=click.Path(),
    default=None,
    envvar="HERMES_CHORE_STORE",
    help="Path to a 'chore store' file. Will be created if it does not exist. A reasonable default is provided according to your operating system.",
)
def chores(context, store):
    context.store = ChoreStore(
        context.config.get("chore store", None)
        if store is None
        else click.format_filename(store)
    )


@chores.command(name="list")
@pass_call_context
def listchores(context):
    for chore in context.store.chores():
        click.secho(chore.name)
    else:
        click.secho("No chores found.")


def _make_target_cal(context, calendar, calendar_id) -> str:
    if calendar is not None and calendar_id is not None:
        raise click.UsageError(
            "You must specify only one of --calendar and --calendar-id, not both. You may also specify a default in the hermes config file."
        )
    elif calendar is not None:
        return context.gcal.client.calendar_by_name(calendar)["id"]
    elif calendar_id is not None:
        return calendar_id
    elif context.config.get("gcal calendar"):
        # Retrieve calendar from config if set in config
        return context.gcal.client.calendar_by_name(
            context.config.get("gcal calendar")
        )["id"]
    return None


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
