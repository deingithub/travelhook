from datetime import datetime

import discord

from .helpers import format_time, train_type_emoji, train_type_color, tz


def format_travelynx(bot, userid, data):
    user = bot.get_user(userid)
    if not data["checkedIn"]:
        return discord.Embed().set_author(
            name=f"{user.name} ist gerade nicht unterwegs",
            icon_url=user.avatar.url,
        )

    is_hafas = "|" in data["train"]["id"]

    # chop off long city names in station name
    short_from_name = data["fromStation"]["name"]
    if is_hafas:
        short_from_name = short_from_name.split(", ")[0]
    short_to_name = data["toStation"]["name"]
    if is_hafas:
        short_to_name = short_to_name.split(", ")[0]

    train_headsign = f'({data["toStation"]["name"]})'

    desc = ""
    # TODO multi trip
    # desc += f'### {format_time(data["fromStation"]["scheduledTime"], data["fromStation"]["realTime"])} {data["fromStation"]["name"]}\n'

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

    desc += f"**{train_type_emoji.get(train_type, train_type)} [{train_line} ➤ {train_headsign}]("

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

    desc += link + ")**\n"
    desc += (
        f'{short_from_name} {format_time(data["fromStation"]["scheduledTime"], data["fromStation"]["realTime"])}'
        " – "
        f'{short_to_name} {format_time(data["toStation"]["scheduledTime"], data["toStation"]["realTime"])}\n'
    )
    if comment := data["comment"]:
        desc += f"> {comment}\n"

    # TODO multi trip
    # desc += f'### {format_time(data["toStation"]["scheduledTime"], data["toStation"]["realTime"])} {data["toStation"]["name"]}'

    e = discord.Embed(
        description=desc,
        colour=train_type_color.get(train_type),
    ).set_author(
        name=f"{user.name} ist unterwegs",
        icon_url=user.avatar.url,
    )
    return e
