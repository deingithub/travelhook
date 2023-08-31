from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from enum import IntEnum
import json

import discord
from haversine import haversine


def zugid(data):
    return str(data["fromStation"]["scheduledTime"]) + data["train"]["id"]


class Privacy(IntEnum):
    ME = 0
    EVERYONE = 5
    LIVE = 10


tz = ZoneInfo("Europe/Berlin")


def is_new_journey(database, status, userid):
    "determine if the user has merely changed into a new transport or if they have started another journey altogether"

    if last_journey := database.execute(
        "SELECT to_lat, to_lon, to_time, travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time DESC LIMIT 1;",
        (userid,),
    ).fetchone():
        if (
            status["train"]["id"]
            == json.loads(last_journey["travelynx_status"])["train"]["id"]
        ):
            return False

        next_journey = status["fromStation"]

        change_distance = haversine(
            (last_journey["to_lat"] or 0.0, last_journey["to_lon"] or 0.0),
            (
                next_journey["latitude"] or 90.0,
                next_journey["longitude"] or 90.0,
            ),
        )
        change_duration = datetime.fromtimestamp(
            next_journey["realTime"], tz=tz
        ) - datetime.fromtimestamp(last_journey["to_time"], tz=tz)

        return (change_distance > 0.75) or change_duration > timedelta(hours=1)

    return True


line_emoji = {
    "start": "<:start:1146748019245588561>",
    "end": "<:end:1146748021586010182>",
    "change_start": "<:change_start:1146748016422821948>",
    "change_end": "<:change_end:1146748013490999379>",
    "rail": "<:rail:1146748024358441001>",
    "change": "<:change:1146749106337894490>",
}

train_type_emoji = {
    "Bus": "<:Bus:1143105600121741462>",
    "CJX": "<:cjx:1143428699249713233>",
    "EC": "<:EC:1102209838307627082>",
    "Fähre": "<:Faehre:1143105659827658783>",
    "IC": "<:IC:1102209818648911872>",
    "ICE": "<:ICE:1102210303518846976>",
    "IR": "<:IR:1143119119080767649>",
    "R": "<:r_:1143428700629643324>",
    "RB": "<:RB:1143231656895971349>",
    "RE": "<:RE:1143231659941056512>",
    "REX": "<:rex:1143428702751961108>",
    "RJ": "<:RJ:1143109130270281758>",
    "RJX": "<:RJX:1143109133256642590>",
    "S": "<:SBahn:1102206882527060038>",
    "Schw-B": "<:Schwebebahn:1143108575770726510>",
    "STB": "<:UBahn:1143105924421132441>",
    "STR": "<:Tram:1143105662549766188>",
    "U": "<:UBahn:1143105924421132441>",
    "U1": "<:UWien:1143235532571291859>",
    "U2": "<:UWien:1143235532571291859>",
    "U3": "<:UWien:1143235532571291859>",
    "U4": "<:UWien:1143235532571291859>",
    "U5": "<:UWien:1143235532571291859>",
    "U6": "<:UWien:1143235532571291859>",
    "Ü": "<:uestra:1143092880089550928>",
}
train_type_color = {
    k: discord.Colour.from_str(v)
    for (k, v) in {
        "Bus": "#a3167e",
        "EC": "#ff0404",
        "EN": "#282559",
        "CJX": "#cc1d00",
        "Fähre": "#00a4db",
        "IC": "#ff0404",
        "ICE": "#ff0404",
        "IR": "#ff0404",
        "NJ": "#282559",
        "R": "#1d4491",
        "RB": "#005fa3",
        "RE": "#e93c13",
        "REX": "#1d4491",
        "RJ": "#c63131",
        "RJX": "#c63131",
        "S": "#008d4f",
        "Schw-B": "#4896d2",
        "STB": "#014e8d",
        "STR": "#da0031",
        "U": "#014e8d",
        "U1": "#ff2e17",
        "U2": "#9864b2",
        "U3": "#ff7d24",
        "U4": "#19a669",
        "U5": "#2e8e95",
        "U6": "#9a6736",
        "Ü": "#78b41d",
    }.items()
}


def format_time(sched, actual, relative=False):
    time = datetime.fromtimestamp(actual, tz=tz)
    diff = ""
    if relative:
        return f"<t:{int(time.timestamp())}:R>"

    if actual > sched:
        diff = (actual - sched) // 60
        diff = f" **+{diff}′**"

    return f"<t:{int(time.timestamp())}:t>{diff}"
