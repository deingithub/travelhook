from datetime import datetime

import discord
from haversine import haversine

from .helpers import format_time, train_type_emoji, line_emoji, train_type_color, tz


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

    # the funky
    is_in_hannover = lambda lat, lon: (lat > 52.2047 and lat < 52.4543) and (
        lon > 9.5684 and lon < 9.9996
    )
    if train_type == "STR" and is_in_hannover(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "Ü"

    if train_type == "U" and data["fromStation"]["name"].startswith("Wien "):
        train_type = data["fromStation"]["name"][-3:-1]

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
    comments = ""
    color = None

    for i, train in enumerate(statuses):
        start_emoji = line_emoji["start"] if i == 0 else line_emoji["change_start"]
        bold = "**" if i == 0 else ""
        departure = format_time(
            train["fromStation"]["scheduledTime"], train["fromStation"]["realTime"]
        )
        desc += f'{start_emoji}{departure} {bold}{train["fromStation"]["name"]}{bold}\n'

        train_type, train_line, route_link = train_presentation(train)
        train_headsign = f'({train["toStation"]["name"]})'
        desc += (
            f'{line_emoji["rail"]} {train_type_emoji.get(train_type, train_type)} [**{train_line}** ➤ {train_headsign}]({route_link})\n'
            f'{line_emoji["rail"]}\n'
        )

        if train["comment"]:
            comments += f'> **{train_type_emoji.get(train_type, train_type)} {train_line} ➤ {train_headsign}** {train["comment"]}\n'

        arrival = format_time(
            train["toStation"]["scheduledTime"], train["toStation"]["realTime"]
        )
        if i + 1 < len(statuses):
            desc += f'{line_emoji["change_end"]}{arrival} '

            next_train = statuses[i + 1]

            if train["toStation"]["name"] != next_train["fromStation"]["name"]:
                desc += train["toStation"]["name"]

            desc += "\n"

            change_meters = int(
                haversine(
                    (train["toStation"]["latitude"], train["toStation"]["longitude"]),
                    (
                        next_train["fromStation"]["latitude"],
                        next_train["fromStation"]["longitude"],
                    ),
                )
                * 1000,
            )
            if change_meters > 100:
                desc += f'{line_emoji["change"]} *— {change_meters}m —*\n'
        else:
            desc += f'{line_emoji["end"]}{arrival} **{train["toStation"]["name"]}**\n'
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
        if comments:
            desc += "\n" + comments

    e = discord.Embed(
        description=desc,
        colour=color,
    ).set_author(
        name=f"{user.name} ist unterwegs",
        icon_url=user.avatar.url,
    )

    if "Durlacher Tor/KIT-Campus Süd" in (
        statuses[-1]["fromStation"]["name"] + statuses[-1]["toStation"]["name"]
    ):
        e = e.set_image(
            url="https://cdn.discordapp.com/attachments/552251414097690630/1147252343881080832/image.png"
        )

    return e
