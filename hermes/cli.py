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
import sys
from operator import attrgetter
from pathlib import Path
import random
from typing import Any, Dict, Optional

from appdirs import user_config_dir, user_data_dir
import click
from dateutil.tz import tzlocal

from .chores import Chore, ChoreStore
from .clients.gcal import GoogleClient, GoogleCalendarAPI, GoogleCalendarTimeSpan
from .schedule import Schedule
from .span import Span
from .stochastics import Frequency
from .timespan import date_parse


APP_NAME = "HermesCLI"
APP_AUTHOR = "Hermes"

DEFAULT_CONFIG_FILE = (
    Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "hermes" / "hermes.ini"
)
DEFAULT_AUTH_TOKEN_FILE = (
    Path(user_data_dir(APP_NAME, APP_AUTHOR)) / "hermes" / "gcal.oauth.json"
)
DEFAULT_CHORE_STORE_FILE = (
    Path(user_data_dir(APP_NAME, APP_AUTHOR)) / "hermes" / "chore_store.db"
)
DEFAULT_SCHEDULE_FILE = (
    Path(user_data_dir(APP_NAME, APP_AUTHOR)) / "hermes" / "schedule.py"
)

DEFAULT_CONFIG = {
    "hermes": {
        "gcal calendar": "",
        "gcal token file": str(DEFAULT_AUTH_TOKEN_FILE),
        "chore store": str(DEFAULT_CHORE_STORE_FILE),
        "schedule file": str(DEFAULT_SCHEDULE_FILE),
    }
}


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
    def __init__(self, begins_at, finish_at, auth_file):
        self._span = Span(begins_at=begins_at, finish_at=finish_at)
        if not auth_file.parent.exists():
            auth_file.parent.mkdir(parents=True, exist_ok=True)
        gclient = GoogleClient.from_access_token_file(file=auth_file)
        self.client = GoogleCalendarAPI(client=gclient)

    @property
    def span(self) -> Span:
        return self._span


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

    context.gcal = GCalOptions(
        begins_at=start,
        finish_at=stop,
        auth_file=Path(context.config["gcal token file"]),
    )
    context.target_calendar_id = _make_target_cal(context, calendar, calendar_id)


@calendars.command(name="list")
@pass_call_context
def callist(context: CallContext) -> None:
    """List all known calendars, and their source."""
    click.secho("Google Calendars:", bold=True)
    for cal_id in context.gcal.client.calendars():
        cal = context.gcal.client.calendar_info(cal_id)
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
        search_cals = [calendar for calendar in context.gcal.client.calendars()]
    else:
        search_cals = [context.target_calendar_id]

    load_opts = {"span": context.gcal.span}
    # TODO - progress bar? See _make_progress_iter.

    for cal_id in search_cals:
        cal_data = context.gcal.client.calendar_info(cal_id)
        if pretty:
            click.secho(f"{cal_data['summary']} [{cal_id}]", bold=True)
        timespan = context.gcal.client.load_timespan(cal_id, **load_opts)
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
        client=context.gcal.client,
        calendar_id=context.target_calendar_id,
        load_span=context.gcal.span,
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
@click.option(
    "--schedule",
    type=click.Path(),
    default=None,
    envvar="HERMES_SCHEDULE_FILE",
    help="Path to a python file containing schedule definitions to load.",
    multiple=True,
)
@click.option(
    "--chore-store",
    type=click.Path(),
    default=None,
    envvar="HERMES_CHORE_STORE",
    help="Path to a 'chore store' file. Will be created if it does not exist. A reasonable default is provided according to your operating system.",
)
@pass_call_context
def whatsnext(context, schedule, slots, check_calendar, check_calendar_id, chore_store):
    if context.target_calendar_id is None:
        raise click.UsageError(
            "When building a schedule, you must specify one (and only one) calendar."
        )
    gcal = GoogleCalendarTimeSpan(
        client=context.gcal.client,
        calendar_id=context.target_calendar_id,
        load_span=context.gcal.span,
    )

    # TODO - hack to have chore stores in calendar command. Rethink this.
    store = ChoreStore(
        context.config.get("chore store", None)
        if chore_store is None
        else click.format_filename(chore_store)
    )

    slot_list = []
    slot_schedules = {}
    events = [e for e in gcal.iter_tags()]
    now = datetime.now(tzlocal())
    # TODO - the notion of 'upcoming' as relates to currently in-progress events is tricky
    upcoming_events = sorted(
        (e for e in events if e.valid_to >= now), key=attrgetter("valid_from")
    )

    if now >= context.gcal.span.finish_at:
        raise click.UsageError(
            "Your target date range for scheduling must be in the future."
        )

    if upcoming_events:
        slot_list.append(upcoming_events[0].name)
        slot_schedules[slot_list[0]] = upcoming_events

    schedule = schedule or [context.config.get("schedule file")]
    schedule_files = [Path(click.format_filename(f)) for f in schedule]
    schedules = {
        schedule_name: schedule_def
        for schedule_name, schedule_def in _load_schedules(schedule_files)
    }

    pre_existing_calendars = list(check_calendar_id)
    for calendar_name in check_calendar:
        pre_existing_calendars.append(
            context.gcal.client.calendar_info_by_name(calendar_name)["id"]
        )

    loaded_calendars = [
        GoogleCalendarTimeSpan(
            client=context.gcal.client, calendar_id=cal, load_span=context.gcal.span
        )
        for cal in pre_existing_calendars
    ]

    span = Span(
        begins_at=max(context.gcal.span.begins_at, now),
        finish_at=context.gcal.span.finish_at,
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
                chore_store=store,
                span=span,
                pre_existing_timespans=loaded_calendars,
                no_pick_first=no_pick_first,
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
    found_chore = False
    for chore in context.store:
        click.secho(chore.name)
        found_chore = True

    if not found_chore:
        click.secho("No chores found.")


@chores.command()
@pass_call_context
def reset(context):
    if click.confirm("Are you sure you want to reset the chore store?"):
        context.store.reset()


# TODO - document the fact that these options are eval'ed
@chores.command()
@pass_call_context
@click.argument("name")
@click.option("--frequency_mean", type=str)
@click.option("--frequency_tolerance", type=str)
@click.option("--frequency_minimum", type=str)
@click.option("--frequency_maximum", type=str)
@click.option("--duration", type=str)
def add(
    context,
    name,
    frequency_mean,
    frequency_tolerance,
    frequency_minimum,
    frequency_maximum,
    duration,
):
    freq_args = {}
    if frequency_mean is not None:
        freq_args["mean"] = timedelta(seconds=eval(frequency_mean))
    if frequency_tolerance is not None:
        freq_args["tolerance"] = timedelta(seconds=eval(frequency_tolerance))
    if frequency_minimum is not None:
        freq_args["minimum"] = timedelta(seconds=eval(frequency_minimum))
    if frequency_maximum is not None:
        freq_args["maximum"] = timedelta(seconds=eval(frequency_maximum))
    frequency = Frequency(**freq_args)

    chore_args = {"frequency": frequency, "name": name}
    if duration is not None:
        chore_args["duration"] = timedelta(seconds=eval(duration))
    chore = Chore(**chore_args)

    context.store.add_chore(chore)
    click.secho(f"Added chore {chore.name}")


@chores.command()
@pass_call_context
def filename(context):
    """Helper command to simply print the loaded chore store. Useful for debugging."""
    click.secho(str(context.store.filename))


@cli.group()
@pass_call_context
@click.option(
    "--schedule",
    type=click.Path(),
    default=None,
    envvar="HERMES_SCHEDULE_FILE",
    help="Path to a python file containing schedule definitions to load.",
    multiple=True,
)
def schedules(context, schedule):
    schedule = schedule or [
        _prepare_default_schedule(context.config.get("schedule file"))
    ]
    context.schedule_files = [Path(click.format_filename(f)) for f in schedule]
    context.schedules = {
        schedule_name: schedule_def
        for schedule_name, schedule_def in _load_schedules(context.schedule_files)
    }


@schedules.command(name="list")
@pass_call_context
def list_schedules(context):
    found_schedule = False
    for schedule_name in context.schedules.keys():
        click.secho(schedule_name)
        found_schedule = True

    if not found_schedule:
        click.secho("No schedules found.")


@schedules.command()
@pass_call_context
def filenames(context):
    """Helper command to simply print the loaded schedule files. Useful for debugging."""
    for schedule in context.schedule_files:
        click.secho(str(schedule))


def _make_target_cal(context, calendar, calendar_id) -> str:
    if calendar is not None and calendar_id is not None:
        raise click.UsageError(
            "You must specify only one of --calendar and --calendar-id, not both. You may also specify a default in the hermes config file."
        )
    elif calendar is not None:
        return context.gcal.client.calendar_info_by_name(calendar)["id"]
    elif calendar_id is not None:
        return calendar_id
    elif context.config.get("gcal calendar"):
        # Retrieve calendar from config if set in config
        return context.gcal.client.calendar_info_by_name(
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
    progress_options["length"] = context.gcal.span.duration.total_seconds()
    return partial(click.progressbar, **progress_options)


def _load_schedules(schedules):
    for i, schedule_path in enumerate(schedules):
        schedule = str(schedule_path)
        # TODO - make this reentrant. UUID? Meanwhile, just make sure not to call this twice. names will collide.
        try:
            spec = spec_from_file_location(f"user_supplied_module_{i}", schedule)
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            click.echo(
                "The supplied schedule file contains an error and can't be loaded.",
                err=True,
            )
            exc_type, exc_msg, _ = sys.exc_info()
            raise click.FileError(schedule, hint=f"{exc_type.__name__}: {exc_msg}")
        for clsname, definition in inspect.getmembers(module):
            if inspect.isclass(definition) and issubclass(definition, Schedule):
                if hasattr(definition, "schedule"):
                    yield clsname, definition


# TODO - documentation
_DEFAULT_SCHEDULE = '''
# -*- coding: utf-8 -*-
from hermes.schedule import DailySchedule


class DefaultSchedule(DailySchedule):
    """This is an example schedule. You should replace it with your own!"""
    def schedule(self):
        self.add_event("Example Event")
'''


def _prepare_default_schedule(schedule_file):
    schedule = Path(schedule_file)
    if not schedule.exists():
        schedule.write_text(_DEFAULT_SCHEDULE)
    return schedule_file


if __name__ == "__main__":
    cli()
