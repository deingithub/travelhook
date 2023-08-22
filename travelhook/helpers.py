from datetime import datetime
from zoneinfo import ZoneInfo

import discord

tz = ZoneInfo("Europe/Berlin")

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


def format_time(sched, actual, relative=True):
    time = datetime.fromtimestamp(actual, tz=tz)
    diff = ""
    if not relative:
        return f"<t:{int(time.timestamp())}:R>"

    if actual > sched:
        diff = (actual - sched) // 60
        diff = f" **+{diff}′**"

    return f"<t:{int(time.timestamp())}:t>{diff}"
