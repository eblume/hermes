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
from operator import attrgetter
from pathlib import Path
import random
import sys
from typing import Any, Dict, Optional

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
    help="Shortcut for --start-date and --finish-date to match the current local day.",
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
    else:
        start = date_parse(start_date) if start_date else None
        stop = date_parse(finish_date) if finish_date else None

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
@click.argument("schedules", type=click.Path(exists=True), nargs=-1)
@pass_call_context
def whatsnext(context, schedules, slots):
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
    now = datetime.now(timezone.utc)
    past_events = [e for e in events if e.valid_from < now]
    upcoming_events = sorted(
        (e for e in events if e.valid_from >= now), key=attrgetter("valid_from")
    )

    if upcoming_events:
        slot_list.append(upcoming_events[0])
        slot_schedules[slot_list[0].name] = upcoming_events

    schedules = {
        schedule_name: schedule_def
        for schedule_name, schedule_def in _load_schedules(schedules)
    }

    if now >= context.gcal.finish_at:
        raise click.UsageError(
            "Your target date range for scheduling must be in the future."
        )

    span = Span(
        begins_at=max(context.gcal.begins_at, now), finish_at=context.gcal.finish_at
    )

    unfeasible_count = 0
    while len(slot_list) < slots:
        if unfeasible_count >= 3:
            if not slot_list:
                click.secho(
                    "Sorry! Could not find a feasible next event. Try relaxing your constraints?",
                    bold=True,
                )
                click.secho("Nothing was written to your calendar!")
                sys.exit(3)
            break

        if not schedules:
            # "degrade gracefully", as per click's suggestion
            break
        # TODO - categories
        schedule_name = random.choice(
            list(schedules.keys())
        )  # TODO: random? or in order? or somehow all-together? Hmm.
        schedule = schedules[schedule_name]()
        schedule.schedule()

        if past_events:
            schedule.pre_existing_events(past_events)

        try:
            new_events = sorted(
                schedule.populate(span, no_pick_first={e.name for e in slot_list}),
                key=attrgetter("valid_from"),
            )
        except ValueError:
            unfeasible_count += 1
            continue

        if new_events:
            slot_list.append(new_events[0])
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
        click.secho(
            f"\t{i}:\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>"
        )
        # TODO - show whole plan, somehow? Ugly UI.

    choice = click.prompt(
        "Please enter your choice (ctrl+c to cancel):",
        default=0,
        type=click.Choice(list(str(i) for i in range(len(slot_list)))),
    )

    chosen_schedule = slot_schedules[slot_list[int(choice)].name]

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


@calendars.command()
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
    check_calendar,
    check_calendar_id,
    replan,
    replan_past,
    check_this_calendar,
    schedules=None,
):
    """Import the specified schedule files (which are python files) and populate
    the specified calendar according to schedule definitions in those files."""
    if context.target_calendar_id is None:
        raise click.UsageError(
            "When clearing a schedule, you must specify one (and only one) calendar."
        )

    if replan and not check_this_calendar:
        raise click.UsageError(
            "--no-check-this-calendar requires you also set --no-replan explicitly. (Replanning requires checking this calendar.)"
        )

    if replan_past and not replan:
        raise click.UsageError("--replan-past requires that you set --replan")

    if not context.gcal.client.span.is_finite():
        raise click.UsageError(
            "You must specify both a start and finish time when scheduling. (You can't plan eternity... yet.)"
        )
    gcal = GoogleCalendarTimeSpan(
        client=context.gcal.client,
        calendar_id=context.target_calendar_id,
        load_events=False,
    )
    base_category = Category("Hermes", None) / "Daily Schedule"

    pre_existing_calendars = list(check_calendar_id)
    for calendar_name in check_calendar:
        pre_existing_calendars.append(
            context.gcal.client.calendar_by_name(calendar_name)["id"]
        )
    if check_this_calendar:
        pre_existing_calendars.append(context.target_calendar_id)

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
        for event in context.gcal.client.load_gcal(
            context.target_calendar_id
        ).iter_tags():
            if event.valid_from >= replan_span.begins_at:
                replanned_events |= {event}

    pre_existing_events = []
    for calendar_id in set(pre_existing_calendars):
        for event in context.gcal.client.load_gcal(calendar_id).iter_tags():
            if (
                replan
                and calendar_id == context.target_calendar_id
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
        click.secho(f"Scheduling with {schedule_name}", bold=True)
        category = base_category / (schedule_def.NAME or schedule_name)
        for day in dates_between(
            Span(begins_at=context.gcal.begins_at, finish_at=context.gcal.finish_at)
        ):
            click.secho(f"\ton {day.isoformat()}")
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
                click.secho(
                    f"\t\t{event.name} <{event.valid_from.isoformat()}, {event.valid_to.isoformat()}>"
                )
                gcal.insert_tag(event.recategorize(category))
    gcal.flush()


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
