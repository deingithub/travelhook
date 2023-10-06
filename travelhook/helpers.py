from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from enum import IntEnum
import json

import discord
from haversine import haversine
from pyhafas import HafasClient
from pyhafas.profile import DBProfile


def zugid(data):
    return str(data["fromStation"]["scheduledTime"]) + data["train"]["id"]


class Privacy(IntEnum):
    ME = 0
    EVERYONE = 5
    LIVE = 10


tz = ZoneInfo("Europe/Berlin")
hafas = HafasClient(DBProfile())


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

        return (change_distance > 2.0) or change_duration > timedelta(hours=2)

    return True


def format_time(sched, actual, relative=False):
    time = datetime.fromtimestamp(actual, tz=tz)
    diff = ""
    if relative:
        return f"<t:{int(time.timestamp())}:R>"

    if actual > sched:
        diff = (actual - sched) // 60
        diff = f" +{diff}′"

    return f"**{time:%H:%M}{diff}**"


def fetch_headsign(database, status):
    def get_headsign_from_trip(trip):
        headsign = trip.destination.name
        return replace_headsign.get(
            (status["train"]["type"] + status["train"]["line"], headsign), headsign
        )

    cached = database.execute(
        "SELECT headsign FROM trips WHERE journey_id = ?", (zugid(status),)
    ).fetchone()
    if cached and cached["headsign"]:
        return cached["headsign"]
    else:
        headsign = "?"
        # do a wild guess which train we're on
        try:
            departure = datetime.fromtimestamp(
                status["fromStation"]["scheduledTime"], tz=tz
            )
            arrival = datetime.fromtimestamp(
                status["toStation"]["scheduledTime"], tz=tz
            )

            candidates = hafas.journeys(
                origin=status["fromStation"]["uic"],
                destination=status["toStation"]["uic"],
                date=departure,
                max_changes=0,
            )
            candidates = [
                c
                for c in candidates
                if c.legs[0].departure == departure and c.legs[0].arrival == arrival
            ]
            if len(candidates) == 1:
                headsign = get_headsign_from_trip(hafas.trip(candidates[0].legs[0].id))
            else:
                candidates = [
                    c
                    for c in candidates
                    if c.legs[0].name.removeprefix(status["train"]["type"]).strip()
                    == (status["train"]["line"] or status["train"]["no"])
                ]
                if len(candidates) == 1:
                    headsign = get_headsign_from_trip(
                        hafas.trip(candidates[0].legs[0].id)
                    )
                else:
                    # ok i give up
                    print(origin, destination, departure, candidates)
        except Exception as e:
            print(f"error fetching headsign: {e}")

        database.execute(
            "UPDATE trips SET headsign = ? WHERE journey_id = ?",
            (
                headsign,
                zugid(status),
            ),
        )
        return headsign


class LineEmoji:
    START = "<:A1:1146748019245588561>"
    END = "<:A2:1146748021586010182>"
    CHANGE_SAME_STOP = "<:B0:1152624963677868185>"
    CHANGE_LEAVE_STOP = "<:B2:1146748013490999379>"
    CHANGE_WALK = "<:B3:1152615187375988796>"
    CHANGE_ENTER_STOP = "<:B1:1146748016422821948>"
    RAIL = "<:C1:1146748024358441001>"
    COMPACT_JOURNEY_START = "<:A3:1152995610216104077>"
    COMPACT_JOURNEY = "<:A4:1152930006478106724>"
    SPACER = " "


train_type_emoji = {
    "ATS": "<:SBahn:1152254307660484650>",
    "Bus": "<:Bus:1143105600121741462>",
    "CJX": "<:cjx:1143428699249713233>",
    "EC": "<:EC:1102209838307627082>",
    "Fähre": "<:Faehre:1143105659827658783>",
    "IC": "<:IC:1102209818648911872>",
    "ICE": "<:ICE:1102210303518846976>",
    "IR": "<:IR:1143119119080767649>",
    "IRE": "<:ire:1154136149326045216>",
    "R": "<:r_:1143428700629643324>",
    "RB": "<:rb:1154136145274339368>",
    "RE": "<:re:1154136147975491707>",
    "REX": "<:rex:1143428702751961108>",
    "RJ": "<:RJ:1143109130270281758>",
    "RJX": "<:RJX:1143109133256642590>",
    "S": "<:SBahn:1102206882527060038>",
    "SB": "<:sb:1159896710454194206>",
    "Schw-B": "<:Schwebebahn:1143108575770726510>",
    "STB": "<:UBahn:1143105924421132441>",
    "STR": "<:Tram:1143105662549766188>",
    "TER": "<:TER:1152248180407275591>",
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
        "ATS": "#0096d8",
        "Bus": "#a3167e",
        "EC": "#ff0404",
        "EN": "#282559",
        "CJX": "#cc1d00",
        "Fähre": "#00a4db",
        "IC": "#ff0404",
        "ICE": "#ff0404",
        "IR": "#ff0404",
        "IRE": "#e73f0f",
        "NJ": "#282559",
        "R": "#1d4491",
        "RB": "#1d4491",
        "RE": "#e73f0f",
        "REX": "#1d4491",
        "RJ": "#c63131",
        "RJX": "#c63131",
        "S": "#008d4f",
        "SB": "#211e1e",
        "Schw-B": "#4896d2",
        "STB": "#014e8d",
        "STR": "#da0031",
        "TER": "#1c4aa2",
        "U": "#014e8d",
        "U1": "#ff2e17",
        "U2": "#9864b2",
        "U3": "#ff7d24",
        "U4": "#19a669",
        "U5": "#2e8e95",
        "U6": "#9a6736",
        "Ü": "#78b41d",
        "WB": "#2e86ce",
    }.items()
}
