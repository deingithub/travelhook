"various helper functions that do more than just pure formatting logic. the icon library lives in here too"
from datetime import datetime
from zoneinfo import ZoneInfo
import traceback

import discord
from aiohttp import ClientSession
from pyhafas import HafasClient
from pyhafas.profile import DBProfile

from . import database as DB


def zugid(data):
    """identify a user-trip by its departure time + hafas/iris specific trip id.
    forms the primary key of the trips table together with user id."""
    return str(data["fromStation"]["scheduledTime"]) + data["train"]["id"]


# globally used timezone
tz = ZoneInfo("Europe/Berlin")
hafas = HafasClient(DBProfile())


async def is_token_valid(token):
    "check if a status api token actually works"
    async with ClientSession() as session:
        async with session.get(f"https://travelynx.de/api/v1/status/{token}") as r:
            try:
                data = await r.json()
                if r.status == 200 and not "error" in data:
                    return True
                print(f"token {token} invalid: {r.status} {data}")
                return False
            except:  # pylint: disable=bare-except
                print(f"error verifying token {token}:")
                traceback.print_exc()


def format_time(sched, actual, relative=False):
    """render a nice timestamp for arrival/departure that includes delay information.
    relative=True creates a discord relative timestamp that looks like "in 3 minutes"
    and updates automatically, used for the embed's final destination arrival time.
    """
    time = datetime.fromtimestamp(actual, tz=tz)

    if relative:
        return f"<t:{int(time.timestamp())}:R>"

    diff = ""
    if actual > sched:
        diff = (actual - sched) // 60
        diff = f" +{diff}′"

    return f"**{time:%H:%M}{diff}**"


def train_presentation(data):
    "do some cosmetic fixes to train type/line and generate a bahn.expert link for it"
    is_hafas = "|" in data["train"]["id"]

    # account for "ME RE2" instead of "RE  "
    train_type = data["train"]["type"]
    train_line = data["train"]["line"]
    if train_line and train_type not in train_type_emoji:
        if len(train_line) > 2 and train_line[0:2] in train_type_emoji:
            train_type = train_line[0:2]
            train_line = train_line[2:]
        if train_line[0] in train_type_emoji:
            train_type = train_line[0]
            train_line = train_line[1:]

    if not train_line:
        train_line = data["train"]["no"]

    # special treatment for üstra because i love you
    def is_in_hannover(lat, lon):
        return (52.2047 < lat < 52.4543) and (9.5684 < lon < 9.9996)

    if train_type == "STR" and is_in_hannover(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "Ü"

    # special treatment for wien U6 (and the others too i guess)
    if train_type == "U" and data["fromStation"]["name"].startswith("Wien "):
        train_type = data["fromStation"]["name"][-3:-1]
        train_line = ""

    # special treatment for austrian s-bahn
    if train_type == "S" and (
        str(data["fromStation"]["uic"]).startswith("81")
        or str(data["toStation"]["uic"]).startswith("81")
    ):
        train_type = "ATS"

    # that's not a tram, that's an elevator
    if train_type == "ZahnR":
        train_type = "SB"

    if train_type == "U" and train_line.casefold().startswith("m"):
        train_type = "M"

    link = "https://bahn.expert/details"
    # if HAFAS, add journeyid to link to make sure it gets the right one
    if jid := data["train"]["hafasId"] or (data["train"]["id"] if is_hafas else None):
        link += f"/{data['fromStation']['scheduledTime'] * 1000}/?jid={jid}"
    # if we don't have an hafas jid link it to a station instead to disambiguate
    else:
        link += (
            f"/{data['train']['type']}%20{data['train']['no']}/"
            + str(data["fromStation"]["scheduledTime"] * 1000)
            + f"/?station={data['fromStation']['uic']}"
        )

    if "travelhookfaked" in data["train"]["id"]:
        link = None

    return (train_type, train_line, link)


def fetch_headsign(status):
    "try to fetch a train headsign or destination name from HAFAS"

    # have we already fetched the headsign? just use that.
    cached = DB.DB.execute(
        "SELECT headsign FROM trips WHERE journey_id = ?", (zugid(status),)
    ).fetchone()
    if cached and cached["headsign"]:
        return cached["headsign"]

    if fhs := status["train"].get("fakeheadsign"):
        return fhs

    def get_headsign_from_jid(jid):
        headsign = hafas.trip(jid).destination.name
        return replace_headsign.get(
            (
                status["train"]["type"]
                + (status["train"]["line"] or status["train"]["no"]),
                headsign,
            ),
            headsign,
        )

    headsign = "?"
    # first let's try to get the train directly using its hafas jid
    try:
        jid = status["train"]["hafasId"] or status["train"]["id"]
        if "|" in jid:
            headsign = get_headsign_from_jid(jid)
            DB.DB.execute(
                "UPDATE trips SET headsign = ? WHERE journey_id = ?",
                (
                    headsign,
                    zugid(status),
                ),
            )
            return headsign

    except:  # pylint: disable=bare-except
        print("error fetching headsign from hafas jid:")
        traceback.print_exc()

    # ok that didn't work out somehow, let's do a wild guess which train we're on instead
    # we most likely have an iris checkin, so we'll (again, most likely) have a train number
    try:
        departure = datetime.fromtimestamp(status["fromStation"]["realTime"], tz=tz)
        arrival = datetime.fromtimestamp(status["toStation"]["scheduledTime"], tz=tz)

        candidates = hafas.departures(
            station=status["fromStation"]["uic"], date=departure, duration=5
        )
        if len(candidates) == 1:
            headsign = get_headsign_from_jid(candidates[0].id)
        else:
            candidates = [
                c for c in candidates if c.name.endswith(status["train"]["no"])
            ]
            if len(candidates) == 1:
                headsign = get_headsign_from_jid(candidates[0].id)
            else:
                print(
                    "can't decide!",
                    status["fromStation"],
                    status["toStation"],
                    departure,
                    candidates,
                )

    except:  # pylint: disable=bare-except
        print("error fetching headsign from journey:")
        traceback.print_exc()

    DB.DB.execute(
        "UPDATE trips SET headsign = ? WHERE journey_id = ?",
        (
            headsign,
            zugid(status),
        ),
    )
    return headsign


class LineEmoji:  # pylint: disable=too-few-public-methods
    "namespace for our line-painting emoji stolen from wikipedia"
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
    "AST": "<:ast:1161314515355439126>",
    "ATS": "<:SBahn:1152254307660484650>",
    "bike": "<:sbbvelo:1161317270065262683>",
    "Bus": "<:Bus:1160288158374707241>",
    "car": "<:sbbauto:1161317276277031002>",
    "CJX": "<:cjx:1160298616812994570>",
    "D": "<:D_:1161751115067555870>",
    "EC": "<:EC:1160298680365105232>",
    "EN": "<:en:1161753743545610271>",
    "Fähre": "<:Faehre:1143105659827658783>",
    "IC": "<:IC:1160298681887625287>",
    "ICE": "<:ICE:1160298682793611407>",
    "IR": "<:IR:1160298677156446229>",
    "IRE": "<:IRE:1160280941118374102>",
    "M": "<:metro:1162032437065416764>",
    "NJ": "<:nj:1161753745911197787>",
    "O-Bus": "<:Bus:1160288158374707241>",
    "plane": "<:sbbflug:1161317272397287435>",
    "R": "<:R_:1160502334539956274>",
    "RB": "<:RB:1160502337404674048>",
    "RE": "<:RE:1160280940057215087>",
    "REX": "<:REX:1160298595833102358>",
    "RJ": "<:rj:1160298686316818542>",
    "RJX": "<:rjx:1160298687491227740>",
    "RS": "<:RS:1160502338499391570>",
    "RUF": "<:ruf:1161314243698761898>",
    "S": "<:SBahn:1102206882527060038>",
    "SB": "<:SB:1160502333143261234>",
    "Schw-B": "<:Schwebebahn:1143108575770726510>",
    "STB": "<:U_:1160288163214921889>",
    "steam": "<:sbbsteam:1162032435459006494>",
    "STR": "<:Tram:1160290093400064060>",
    "TER": "<:TER:1152248180407275591>",
    "TGV": "***TGV***",
    "Tram": "<:Tram:1160290093400064060>",
    "U": "<:U_:1160288163214921889>",
    "U1": "<:u1:1160998507533058098>",
    "U2": "<:u2:1160998509059776622>",
    "U3": "<:u3:1160998510997553161>",
    "U4": "<:u4:1160998512742383777>",
    "U5": "<:u5:1160998515967799306>",
    "U6": "<:u6:1160998518744424488>",
    "Ü": "<:UE:1160288194730930196>",
    "walk": "<:sbbwalk:1161321193001992273>",
    "WB": "***west***",
}


def get_train_emoji(train_type):
    "return a train emoji or placeholder"
    return train_type_emoji.get(
        train_type, f"<:sbbzug:1160275971266576494> {train_type}"
    )


long_distance_color = "#ff0404"
regional_express_color = "#e73f0f"
regional_color = "#1d4491"

train_type_color = {
    k: discord.Color.from_str(v)
    for (k, v) in {
        "AST": "#ffd700",
        "ATS": "#0096d8",
        "Bus": "#a3167e",
        "D": long_distance_color,
        "EC": long_distance_color,
        "EN": "#282559",
        "CJX": regional_express_color,
        "Fähre": "#00a4db",
        "IC": long_distance_color,
        "ICE": long_distance_color,
        "IR": long_distance_color,
        "IRE": regional_express_color,
        "M": "#014e8d",
        "NJ": "#282559",
        "O-Bus": "#a3167e",
        "R": regional_color,
        "RB": regional_color,
        "RE": regional_express_color,
        "REX": regional_express_color,
        "RJ": "#c63131",
        "RJX": "#c63131",
        "RS": "#008d4f",
        "RUF": "#ffd700",
        "S": "#008d4f",
        "SB": "#2e2e7d",
        "Schw-B": "#4896d2",
        "STB": "#014e8d",
        "STR": "#c5161c",
        "TER": regional_color,
        "TGV": long_distance_color,
        "Tram": "#c5161c",
        "U": "#014e8d",
        "U1": "#ed1d26",
        "U2": "#9e50af",
        "U3": "#f47114",
        "U4": "#1ea366",
        "U5": "#0098a1",
        "U6": "#926131",
        "Ü": "#78b41d",
        "WB": "#2e86ce",
    }.items()
}

not_registered_embed = discord.Embed(
    title="Oops!",
    color=train_type_color["U1"],
    description="It looks like you're not registered with the travelynx relay bot yet.\n"
    "If you want to fix this minor oversight, use **/register** today!",
)

replace_headsign = {
    # Vienna
    ("U1", "Wien Alaudagasse (U1)"): "Alaudagasse",
    ("U1", "Wien Leopoldau Bahnhst (U1)"): "Leopoldau",
    ("U1", "Wien Oberlaa (U1)"): "Oberlaa",
    ("U2", "Wien Schottentor (U2)"): "Schottentor",
    ("U2", "Wien Seestadt (U2)"): "Seestadt",
    ("U3", "Wien Ottakring Bahnhst (U3)"): "Ottakring",
    ("U3", "Wien Simmering Bahnhof (U3)"): "Simmering",
    ("U4", "Wien Heiligenstadt Bf (U4)"): "Heiligenstadt",
    ("U4", "Wien Hütteldorf Bf (U4)"): "Hütteldorf",
    ("U6", "Wien Floridsdorf Bf (U6)"): "Floridsdorf",
    ("U6", "Wien Siebenhirten (U6)"): "Siebenhirten",
    # Hannover
    ("STR1", "Laatzen (GVH)"): "Laatzen",
    ("STR1", "Langenhagen (Hannover) (GVH)"): "Langenhagen",
    ("STR1", "Sarstedt (Endpunkt GVH)"): "Sarstedt",
    ("STR2", "Rethen(Leine) Nord, Laatzen"): "Rethen/Nord",
    ("STR3", "Altwarmbüchen, Isernhagen"): "Altwarmbüchen",
    ("STR9", "Empelde (Bus/Tram), Ronnenberg"): "Empelde",
    # jesus christ KVV please fix this nonsense
    ("S2", "Blankenloch Nord, Stutensee"): "Blankenloch",
    ("S2", "Daxlanden Dornröschenweg, Karlsruhe"): "Rheinstrandsiedlung",
    ("S2", "Hagsfeld Reitschulschlag (Schleife), Karlsruhe"): "Reitschulschlag",
    ("S2", "Mörsch Bach-West, Rheinstetten"): "Rheinstetten",
    ("S2", "Spöck Richard-Hecht-Schule, Stutensee"): "Spöck",
}
