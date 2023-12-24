"this module, or rather its function format_travelynx, renders nice embed describing the current journey"

from itertools import groupby
from datetime import timedelta
import re

import discord
from haversine import haversine

from .helpers import (
    fetch_headsign,
    format_delta,
    format_time,
    get_train_emoji,
    LineEmoji,
    train_type_color,
    train_presentation,
    replace_city_suffix_with_prefix,
)

re_hbf = re.compile(r"(?P<city>.+) Hbf")
re_hauptbahnhof = re.compile(
    r"Hauptbahnhof(?: \(S?\+?U?\)| \(Tram\/Bus\))?, (?P<city>.+)"
)
re_station_city = re.compile(
    r"((S-)?Bahnhof |(S-)?Bh?f\.? )?(?P<station>.+), (?P<city>.+)"
)
re_u_number = re.compile(r"(?P<station>.+) [\(\[]U\d+[\)\]]")


def merge_names(from_name, to_name):
    "if we have equivalent stations like Hauptbahnhof, X and X Hbf, draw a single line change"

    def try_merge(a, b):
        if a.removesuffix("Hbf") == b.removesuffix("Hauptbahnhof"):
            return a

        if (
            (m := re_hbf.match(a))
            and (m2 := re_hauptbahnhof.match(b))
            and m["city"] == m2["city"]
        ):
            return f"{m['city']} Hbf"

        if (
            (m := re_station_city.match(a))
            and m["station"] == "Bahnhof"
            and m["city"] == b
        ):
            return a

        if (
            (m := re_station_city.match(a))
            and (m2 := re_station_city.match(b))
            and m["city"] == m2["city"]
            and m["station"].removesuffix(" (U)") == m2["station"].removesuffix(" (U)")
        ):
            return f"{m['station'].removesuffix(' (U)')}, {m['city']}"

        if (m := re_station_city.match(a)) and b in (
            f"{m['city']} {m['station']}",
            f"{m['city']}-{m['station']}",
        ):
            return b

        if (m := re_u_number.match(a)) and b == m["station"]:
            return m["station"]

        if (
            (m := re_u_number.match(a))
            and (m2 := re_u_number.match(b))
            and m["station"] == m2["station"]
        ):
            return m["station"]

        if a == b + " (S)" or a == b + " (tief)":
            return b

    return try_merge(from_name, to_name) or try_merge(to_name, from_name)


def is_one_line_change(from_station, to_station):
    "check if we should collapse a transfer into one line instead of two (if it's the same station)"
    return (
        (from_station["uic"] == to_station["uic"])
        or (from_station["name"] == to_station["name"])
        or merge_names(from_station["name"], to_station["name"])
    )


def shortened_name(previous_name, this_name):
    "if the last station follows the 'Stop , City' convention and we're still in the same city, drop that suffix"
    if (
        (m := re_station_city.match(previous_name))
        and (m2 := re_station_city.match(this_name))
        and m["city"] == m2["city"]
    ):
        return m2["station"]
    return this_name


def format_travelynx(bot, userid, statuses, continue_link=None):
    """the actual formatting function called by message sends and edits
    to render an embed describing the current journey"""
    user = bot.get_user(userid)

    desc = ""
    color = None

    def _next(statuses, current_index):
        "in the format loop, get the train after the current one or None if we're at the last"
        if (current_index + 1) < len(statuses):
            return statuses[current_index + 1]
        return None

    def _prev(statuses, current_index):
        "in the format loop, get the train before the current one or None if we're at the first"
        if (current_index - 1) >= 0:
            return statuses[current_index - 1]
        return None

    for i, train in enumerate(statuses):
        departure = format_time(
            train["fromStation"]["scheduledTime"], train["fromStation"]["realTime"]
        )
        # compact layout for completed trips
        if continue_link and _next(statuses, i):
            if not _prev(statuses, i):
                name = train["fromStation"]["name"]
                prefix_to_add = replace_city_suffix_with_prefix.get(
                    name.split(", ")[-1]
                )
                if prefix_to_add:
                    name = f"{prefix_to_add} {', '.join(name.split(', ')[0:-1])}"
                desc += f"{LineEmoji.COMPACT_JOURNEY_START}{departure} {name}\n"
                desc += f"{LineEmoji.COMPACT_JOURNEY}{LineEmoji.SPACER}"

            # draw only train type and line number in one line
            train_type, train_line, _ = train_presentation(train)
            desc += get_train_emoji(train_type)
            if train_line:
                desc += f" **{train_line}**"
            # draw an arrow to the next trip in the compact section until the last one in the section
            if _next(statuses, i + 1):
                desc += " → "
            else:
                desc += "\n"
            # ignore the rest of the format loop until we're at the last trip of the journey
            continue

        # regular layout for full journey display
        # if we're the first trip of the journey, draw a journey start icon
        if not _prev(statuses, i):
            name = train["fromStation"]["name"]
            prefix_to_add = replace_city_suffix_with_prefix.get(name.split(", ")[-1])
            if prefix_to_add:
                name = f"{prefix_to_add} {', '.join(name.split(', ')[0:-1])}"
            desc += f"{LineEmoji.START}{departure} **{name}**\n"
        elif prev_train := _prev(statuses, i):
            # if we've just drawn the last compact mode entry, draw a station
            if continue_link and not _next(statuses, i):
                desc += f"{LineEmoji.CHANGE_SAME_STOP}{departure} **{train['fromStation']['name']}**\n"
            # if our trip starts on a different station than the last ended, draw a new station icon
            elif not is_one_line_change(prev_train["toStation"], train["fromStation"]):
                station_name = (
                    merge_names(
                        prev_train["toStation"]["name"], train["fromStation"]["name"]
                    )
                    or train["fromStation"]["name"]
                )
                station_name = shortened_name(
                    prev_train["toStation"]["name"], station_name
                )
                desc += f"{LineEmoji.CHANGE_ENTER_STOP}{departure} {station_name}\n"
            # if our trip starts on the same station as the last ended, we've already drawn the change icon
            else:
                pass

        train_type, train_line, route_link = train_presentation(train)
        headsign = shortened_name(train["fromStation"]["name"], fetch_headsign(train))
        desc += (
            LineEmoji.RAIL
            + LineEmoji.SPACER
            + get_train_emoji(train_type)
            + (
                f" **{train_line} [» {headsign}]({route_link})**"
                if route_link
                else f" **{train_line} » {headsign}** ✱"
            )
            + (" ●" if train["comment"] else "")
        )
        trip_time = timedelta(
            seconds=train["toStation"]["realTime"] - train["fromStation"]["realTime"]
        )
        desc += f" *· {format_delta(trip_time)}*\n"
        # add extra spacing at last trip in the journey
        if not continue_link and not _next(statuses, i):
            desc += f"{LineEmoji.RAIL}\n"

        arrival = format_time(
            train["toStation"]["scheduledTime"], train["toStation"]["realTime"]
        )
        station_name = shortened_name(
            train["fromStation"]["name"], train["toStation"]["name"]
        )
        # if we're on the last trip of the journey, draw an end icon
        if not _next(statuses, i):
            desc += f"{LineEmoji.END}{arrival} **{station_name}**\n"
        # draw a transfer instead
        elif next_train := _next(statuses, i):
            # if we don't leave the station to change, draw a single change line
            if is_one_line_change(train["toStation"], next_train["fromStation"]):
                station_name = (
                    merge_names(
                        train["toStation"]["name"], next_train["fromStation"]["name"]
                    )
                    or train["toStation"]["name"]
                )
                station_name = shortened_name(
                    next_train["fromStation"]["name"], station_name
                )
                next_train_departure = format_time(
                    next_train["fromStation"]["scheduledTime"],
                    next_train["fromStation"]["realTime"],
                )
                desc += f"{LineEmoji.CHANGE_SAME_STOP}{arrival} – {next_train_departure} {station_name}\n"
            else:
                # if we leave the station, draw the upper part of a two-line change
                desc += f"{LineEmoji.CHANGE_LEAVE_STOP}{arrival} " + f"{station_name}\n"
                train_end_location = (
                    train["toStation"]["latitude"],
                    train["toStation"]["longitude"],
                )
                next_train_start_location = (
                    next_train["fromStation"]["latitude"],
                    next_train["fromStation"]["longitude"],
                )
                change_meters = haversine(
                    train_end_location, next_train_start_location, unit="m"
                )
                if change_meters > 200.0 and not "travelhookfaked" in (
                    train["train"]["id"] + next_train["train"]["id"]
                ):
                    desc += f"{LineEmoji.CHANGE_WALK}{LineEmoji.SPACER}*— {int(change_meters)} m —*\n"

        # overwrite last set embed color with the current color
        color = train_type_color.get(train_type, discord.Color.from_str("#2e2e7d"))

    # end of format loop, finish up embed

    if comment := statuses[-1]["comment"]:
        if len(comment) >= 500:
            comment = comment[0:500] + "…"
        desc += f"> {comment}\n"

    if continue_link:
        desc += f"**Weiterfahrt ➤** {continue_link}\n"
    else:
        to_time = format_time(
            statuses[-1]["toStation"]["scheduledTime"],
            statuses[-1]["toStation"]["realTime"],
            True,
        )
        desc += f"### ➤ {statuses[-1]['toStation']['name']} {to_time}\n"

    total_time = timedelta(
        seconds=statuses[-1]["toStation"]["realTime"]
        - statuses[0]["fromStation"]["realTime"]
    )
    journey_time = timedelta(
        seconds=sum(
            train["toStation"]["realTime"] - train["fromStation"]["realTime"]
            for train in statuses
        )
    )
    desc += f"*journey {format_delta(total_time)} ({format_delta(journey_time)} in transit) · {len(statuses)} trips*"

    embed = discord.Embed(
        description=desc,
        color=color,
    ).set_author(
        name=f"{user.name} {'war' if not statuses[-1]['checkedIn'] else 'ist'} unterwegs",
        icon_url=user.avatar.url,
    )

    embed = sillies(statuses, embed)

    return embed


def sillies(statuses, embed):
    "do funny things with the embed once it's done"

    sortkey = lambda tup: tup[0] + tup[1]
    train_lines = sorted([train_presentation(train) for train in statuses], key=sortkey)
    grouped = []
    for _, group in groupby(train_lines, key=sortkey):
        grouped.append(list(group))
    grouped = sorted(grouped, key=len, reverse=True)
    if len(grouped[0]) >= 3:
        train_type, train_line, _ = grouped[0][0]
        embed.description += f"\n### {len(grouped[0])}× {get_train_emoji(train_type)} {train_line} COMBO!"

    status = statuses[-1]
    stations = status["fromStation"]["name"] + status["toStation"]["name"]
    if "Durlacher Tor" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/6WhzdSp.png")
    if "Mühlburger Tor" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/jGATXUv.jpg")
    if "Wien Floridsdorf" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/CSBTb0z.gif")
    if "Wien Mitte" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/f7dwfpt.gif")
    if "Gumpendorfer Straße" in stations:
        return embed.set_image(url="https://i.imgur.com/9P15eRQ.png")
    if "Ziegelstein" in stations:
        return embed.set_thumbnail(url="https://i.imgur.com/W3mPNEn.gif")
    if "Erlangen" in status["toStation"]["name"]:
        return embed.set_thumbnail(url="https://i.imgur.com/pHp8Sus.png")
    if status["train"]["type"] == "Schw-B":
        return embed.set_image(url="https://i.imgur.com/8deLTcU.png")
    if status["train"]["line"] == "4" and "uniwuni" in embed.author.name:
        return embed.set_image(url="https://i.imgur.com/zKzgXLp.png")

    return embed
