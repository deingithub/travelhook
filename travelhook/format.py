from datetime import datetime

import discord
from haversine import haversine

from .helpers import (
    fetch_headsign,
    format_time,
    train_type_emoji,
    LineEmoji,
    train_type_color,
    tz,
)


def is_one_line_change(from_station, to_station):
    "check if we should collapse a transfer into one line instead of two (if it's the same station)"
    return (from_station["uic"] == to_station["uic"]) or (
        from_station["name"] == to_station["name"]
    )


def shortened_name(previous_station, this_station):
    "if the last station follows the 'Stop , City' convention and we're still in the same city, drop that suffix"
    previous_name = previous_station["name"].split(", ")
    this_name = this_station["name"].split(", ")
    if not (len(previous_name) > 1 and len(this_name) > 1):
        return this_station["name"]
    elif previous_name[-1] == this_name[-1]:
        return ", ".join(this_name[0:-1])
    else:
        return this_station["name"]


def train_presentation(data):
    is_hafas = "|" in data["train"]["id"]

    # account for "ME RE2" instead of "RE  "
    train_type = data["train"]["type"]
    train_line = data["train"]["line"]
    if train_type not in train_type_emoji.keys():
        if (
            train_line
            and len(train_line) > 2
            and train_line[0:2] in train_type_emoji.keys()
        ):
            train_type = train_line[0:2]
            train_line = train_line[2:]

    if not train_line:
        train_line = data["train"]["no"]

    # special treatment for üstra because i love you
    is_in_hannover = lambda lat, lon: (lat > 52.2047 and lat < 52.4543) and (
        lon > 9.5684 and lon < 9.9996
    )
    if train_type == "STR" and is_in_hannover(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "Ü"

    # special treatment for wien U6 (and the others too i guess)
    if train_type == "U" and data["fromStation"]["name"].startswith("Wien "):
        train_type = data["fromStation"]["name"][-3:-1]

    # special treatment for austrian s-bahn
    if train_type == "S" and (
        str(data["fromStation"]["uic"]).startswith("81")
        or str(data["toStation"]["uic"]).startswith("81")
    ):
        train_type = "ATS"

    link = (
        f'https://bahn.expert/details/{data["train"]["type"]}%20{data["train"]["no"]}/'
        + str(data["fromStation"]["scheduledTime"] * 1000)
    )
    # if HAFAS, add journeyid to link to make sure it gets the right one
    # if we don't have an hafas id link it to a station instead to disambiguate
    if jid := data["train"]["hafasId"] or (data["train"]["id"] if is_hafas else None):
        link += f"/?jid={jid}"
    else:
        link += f'/?station={data["fromStation"]["uic"]}'

    return (train_type, train_line, link)


def format_travelynx(bot, database, userid, statuses, continue_link=None):
    user = bot.get_user(userid)

    desc = ""
    color = None

    # in the format loop, get the train after the current one or None if we're at the last
    _next = (
        lambda statuses, current_index: statuses[current_index + 1]
        if (current_index + 1) < len(statuses)
        else None
    )
    # in the format loop, get the train before the current one or None if we're at the first
    _prev = (
        lambda statuses, current_index: statuses[current_index - 1]
        if (current_index - 1) >= 0
        else None
    )

    for i, train in enumerate(statuses):
        departure = format_time(
            train["fromStation"]["scheduledTime"], train["fromStation"]["realTime"]
        )
        # compact layout for completed trips
        if continue_link and _next(statuses, i):
            if not _prev(statuses, i):
                desc += f"{LineEmoji.COMPACT_JOURNEY_START}{departure} {train['fromStation']['name']}\n"
                desc += f"{LineEmoji.COMPACT_JOURNEY}{LineEmoji.SPACER}"

            # draw only train type and line number in one line
            train_type, train_line, _ = train_presentation(train)
            desc += f"{train_type_emoji.get(train_type, train_type)} **{train_line}**"
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
            desc += f"{LineEmoji.START}{departure} **{train['fromStation']['name']}**\n"
        elif prev_train := _prev(statuses, i):
            # if we've just drawn the last compact mode entry, draw a station
            if continue_link and not _next(statuses, i):
                desc += f"{LineEmoji.CHANGE_SAME_STOP}{departure} **{train['fromStation']['name']}**\n"
            # if our trip starts on a different station than the last ended, draw a new station icon
            elif not is_one_line_change(prev_train["toStation"], train["fromStation"]):
                station_name = shortened_name(
                    prev_train["toStation"], train["fromStation"]
                )
                desc += f"{LineEmoji.CHANGE_ENTER_STOP}{departure} {station_name}\n"
            # if our trip starts on the same station as the last ended, we've already drawn the change icon
            else:
                pass

        train_type, train_line, route_link = train_presentation(train)
        desc += (
            LineEmoji.RAIL
            + LineEmoji.SPACER
            + train_type_emoji.get(train_type, train_type)
            + f" [**{train_line} » {fetch_headsign(database, train)}**]({route_link})"
            + (f"{LineEmoji.SPACER}💬" if train["comment"] else "")
            + "\n"
            # add more spacing for current journey if not compact
            + (
                f"{LineEmoji.RAIL}\n"
                if not _next(statuses, i) and not continue_link
                else ""
            )
        )

        arrival = format_time(
            train["toStation"]["scheduledTime"], train["toStation"]["realTime"]
        )
        # if we're on the last trip of the journey, draw an end icon
        if not _next(statuses, i):
            station_name = shortened_name(train["fromStation"], train["toStation"])
            desc += f"{LineEmoji.END}{arrival} **{station_name}**\n"
        # if we don't leave the station to change, draw a single change line
        elif next_train := _next(statuses, i):
            station_name = shortened_name(next_train["fromStation"], train["toStation"])
            if is_one_line_change(next_train["fromStation"], train["toStation"]):
                next_train_departure = format_time(
                    next_train["fromStation"]["scheduledTime"],
                    next_train["fromStation"]["realTime"],
                )
                desc += f"{LineEmoji.CHANGE_SAME_STOP}{arrival} → {next_train_departure} {station_name}\n"
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
                if change_meters > 200.0:
                    desc += f"{LineEmoji.CHANGE_WALK}{LineEmoji.SPACER}*— {int(change_meters)} m —*\n"

        # overwrite last set embed color with the current color
        color = train_type_color.get(train_type)

    # end of format loop, finish up embed

    if comment := statuses[-1]["comment"]:
        if len(comment) >= 500:
            comment = comment[0:500] + "…"
        desc += f"> {comment}\n"

    if continue_link:
        desc += f"**Weiterfahrt ➤** {continue_link}"
    else:
        to_time = format_time(
            statuses[-1]["toStation"]["scheduledTime"],
            statuses[-1]["toStation"]["realTime"],
            True,
        )
        desc += f'### ➤ {statuses[-1]["toStation"]["name"]} {to_time}'

    embeds = [
        discord.Embed(
            description=desc,
            colour=color,
        ).set_author(
            name=f"{user.name} {'war' if not statuses[-1]['checkedIn'] else 'ist'} unterwegs",
            icon_url=user.avatar.url,
        )
    ]
    embeds[0] = sillies(statuses[-1], embeds[0])

    return embeds


def sillies(status, embed):
    if "Durlacher Tor" in (status["fromStation"]["name"] + status["toStation"]["name"]):
        return embed.set_image(url="https://i.imgur.com/6WhzdSp.png")
    if "Ziegelstein" in (status["fromStation"]["name"] + status["toStation"]["name"]):
        return embed.set_thumbnail(url="https://i.imgur.com/W3mPNEn.gif")
    if "Gumpendorfer Straße" in (
        status["fromStation"]["name"] + status["toStation"]["name"]
    ):
        return embed.set_image(url="https://i.imgur.com/9P15eRQ.png")
    return embed
