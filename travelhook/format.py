from datetime import datetime

import discord
from haversine import haversine

from .helpers import format_time, train_type_emoji, line_emoji, train_type_color, tz


def train_presentation(data):
    is_hafas = "|" in data["train"]["id"]

    # account for "ME RE2" instead of "RE 2"
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

    # the funky
    is_in_hannover = lambda lat, lon: (lat > 52.2047 and lat < 52.4543) and (
        lon > 9.5684 and lon < 9.9996
    )
    if train_type == "STR" and is_in_hannover(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "Ü"

    if train_type == "U" and short_from_name.startswith("Wien "):
        train_type = short_from_name[-3:-1]

    link = (
        f'https://bahn.expert/details/{data["train"]["type"]}%20{data["train"]["no"]}/'
        + datetime.fromtimestamp(
            data["fromStation"]["scheduledTime"], tz=tz
        ).isoformat()
        + f'/?station={data["fromStation"]["uic"]}'
    )
    # if HAFAS, add journeyid to link to make sure it gets the right one
    if is_hafas:
        link += "&jid=" + data["train"]["id"]

    return (train_type, train_line, link)


def format_travelynx(bot, userid, statuses, continue_link=None):
    user = bot.get_user(userid)

    desc = ""
    color = None

    for i, train in enumerate(statuses):
        start_emoji = line_emoji["start"] if i == 0 else line_emoji["change_start"]
        departure = format_time(
            train["fromStation"]["scheduledTime"], train["fromStation"]["realTime"]
        )
        desc += f'{start_emoji}{departure} {train["fromStation"]["name"]}\n'

        train_type, train_line, route_link = train_presentation(train)
        train_headsign = f'({train["toStation"]["name"]})'
        desc += f'{line_emoji["rail"]} {train_type_emoji[train_type]} [**{train_line}** ➤ {train_headsign}]({route_link})\n'

        if train["comment"]:
            desc += f'{line_emoji["rail"]} *«{train["comment"]}»*\n'
        desc += f'{line_emoji["rail"]}\n'

        arrival = format_time(
            train["toStation"]["scheduledTime"], train["toStation"]["realTime"]
        )
        if i + 1 < len(statuses):
            desc += f'{line_emoji["change_end"]}{arrival} '

            next_train = statuses[i + 1]

            if train["toStation"]["name"] != next_train["fromStation"]["name"]:
                desc += train["toStation"]["name"]

            desc += "\n"

            distance = (
                haversine(
                    (train["toStation"]["latitude"], train["toStation"]["longitude"]),
                    (
                        next_train["fromStation"]["latitude"],
                        next_train["fromStation"]["longitude"],
                    ),
                )
                * 1000
            )
            if distance > 40:
                desc += f'{line_emoji["change"]} *— {int(distance)}m —*\n'
        else:
            desc += f'{line_emoji["end"]}{arrival} {train["toStation"]["name"]}\n'
            color = train_type_color.get(train_type)

    if continue_link:
        desc += f"**Weiterfahrt ➤** {continue_link}"
    else:
        to_time = format_time(
            statuses[-1]["toStation"]["scheduledTime"],
            statuses[-1]["toStation"]["realTime"],
            True,
        )
        desc += f'### ➤ {statuses[-1]["toStation"]["name"]} {to_time}'

    e = discord.Embed(
        description=desc,
        colour=color,
    ).set_author(
        name=f"{user.name} ist unterwegs",
        icon_url=user.avatar.url,
    )
    return e
