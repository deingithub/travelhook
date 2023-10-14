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

    # special treatment for jura
    if train_type == "U" and train_line.casefold().startswith("m"):
        train_type = "M"
    if train_type == "S" and train_line.startswith("L"):
        train_type = "L"

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

    def check_same_train(hafas_name, train):
        hafas_name = hafas_name.replace(" ", "")
        train_line = train["type"] + (train["line"] or "")
        train_no = train["type"] + train["no"]
        return (hafas_name == train_line) or (hafas_name == train_no)

    headsign = "?"
    try:
        departure = datetime.fromtimestamp(
            status["fromStation"]["scheduledTime"], tz=tz
        )
        candidates = hafas.departures(
            station=status["fromStation"]["uic"], date=departure, duration=10
        )
        candidates2 = [
            c
            for c in candidates
            if check_same_train(c.name, status["train"]) and c.dateTime == departure
        ]
        if len(candidates) > 1:
            headsign = get_headsign_from_jid(candidates2[0].id)
        else:
            print(
                "can't decide!",
                status["fromStation"],
                status["toStation"],
                departure,
                candidates,
                candidates2,
                sep="\n",
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
    "CJX": "<:Ja:1162760030068678786><:Jb:1162760030903345254>",
    "D": "<:da:1162760033684168724><:db:1162760035760361582>",
    "EC": "<:eca:1162767426337919086><:ecb:1162767427604578305>",
    "ECE": "<:eca:1162767426337919086><:ece:1162767431513681993>",
    "EN": "<:na:1162760037748441158><:nb:1162760039094812773>",
    "Fähre": "<:Faehre:1143105659827658783>",
    "FLX": "<:fa:1162799739163656334><:fb:1162799736445739128>",
    "IC": "<:ca:1162760063384039524><:cb:1162760064298393641>",
    "ICE": "<:ca:1162760063384039524><:Cb:1162760068857597952>",
    "IR": "<:Ia:1162760071269335272><:db:1162760035760361582>",
    "IRE": "<:ia:1162760103032795187><:ib:1162760104345620480>",
    "L": "<:lex:1162070841702494208>",
    "M": "<:metro:1162032437065416764>",
    "MEX": "<:ma:1162772943596699729><:mb:1162772944951455838>",
    "NJ": "<:Na:1162760106321117258><:Nb:1162760108221153300>",
    "O-Bus": "<:Bus:1160288158374707241>",
    "plane": "<:sbbflug:1161317272397287435>",
    "R": "<:Ra:1162760110536405097><:Rb:1162760111975043072>",
    "RB": "<:Ba:1162760114328043680><:Bb:1162760116261617757>",
    "RE": "<:Ea:1162760127556886639><:Eb:1162760129872138261>",
    "RER": "<:rer:1162070845749997619>",
    "REX": "<:Ea:1162760127556886639><:EXb:1162760134334885948>",
    "RJ": "<:2a:1162760135731589233><:2b:1162760137090551929>",
    "RJX": "<:1a:1162760138277519501><:1b:1162760140458573895>",
    "RS": "<:rs:1162070847645831249>",
    "RUF": "<:ruf:1161314243698761898>",
    "S": "<:SBahn:1102206882527060038>",
    "SB": "<:SB:1160502333143261234>",
    "Schw-B": "<:Schwebebahn:1143108575770726510>",
    "STB": "<:stb:1162051109318295674>",
    "steam": "<:sbbsteam:1162032435459006494>",
    "STR": "<:Tram:1160290093400064060>",
    "SVG": "<:sbbsteam:1162032435459006494> SVG",
    "TER": "<:ta:1162760151384731710><:tb:1162760154769543248>",
    "TGV": "<:Ta:1162760156514357402><:Tb:1162760158854783027>",
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
    "WB": "<:wa:1162760160129855609><:wb:1162760161417515058>",
}


def get_train_emoji(train_type):
    "return a train emoji or placeholder"
    return train_type_emoji.get(
        train_type, f"<:sbbzug:1160275971266576494> {train_type}"
    )


long_distance_color = "#ff0404"
regional_express_color = "#ff4f00"
regional_color = "#204a87"
s_bahn_color = "#008d4f"
night_train_color = "#282559"

train_type_color = {
    k: discord.Color.from_str(v)
    for (k, v) in {
        "AST": "#ffd700",
        "ATS": "#0096d8",
        "Bus": "#a3167e",
        "D": long_distance_color,
        "EC": long_distance_color,
        "ECE": long_distance_color,
        "EN": night_train_color,
        "CJX": regional_express_color,
        "Fähre": "#00a4db",
        "FLX": "#72d800",
        "IC": long_distance_color,
        "ICE": long_distance_color,
        "IR": long_distance_color,
        "IRE": regional_express_color,
        "L": s_bahn_color,
        "M": "#014e8d",
        "MEX": regional_color,
        "NJ": night_train_color,
        "O-Bus": "#a3167e",
        "R": regional_color,
        "RB": regional_color,
        "RE": regional_express_color,
        "RER": s_bahn_color,
        "REX": regional_express_color,
        "RJ": "#c63131",
        "RJX": "#c63131",
        "RS": s_bahn_color,
        "RUF": "#ffd700",
        "S": s_bahn_color,
        "SB": "#2e2e7d",
        "Schw-B": "#4896d2",
        "STB": "#c5161c",
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
