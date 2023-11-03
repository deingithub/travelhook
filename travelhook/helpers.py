"various helper functions that do more than just pure formatting logic. the icon library lives in here too"
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import traceback

import discord
from aiohttp import ClientSession
from pyhafas import HafasClient
from pyhafas.profile import DBProfile
from pyhafas.types.fptf import Stopover
from haversine import haversine

from . import database as DB


def zugid(data):
    """identify a user-trip by its departure time + hafas/iris specific trip id.
    forms the primary key of the trips table together with user id."""
    return f'{data["train"]["id"]}:{data["fromStation"]["scheduledTime"]}'


# globally used timezone
tz = ZoneInfo("Europe/Berlin")
hafas = HafasClient(DBProfile())


def parse_manual_time(time):
    time = time.split(":")
    return datetime.now(tz=tz).replace(
        hour=int(time[0]),
        minute=int(time[1]),
        second=0,
    )


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


def format_delta(delta):
    "turn a timedelta into  representation like 1h37m"
    h, m = divmod(delta, timedelta(hours=1))
    m = int(m.total_seconds() // 60)
    if h > 0:
        return f"{h}:{m:02}h"
    return f"{m}′"


blanket_replace_train_type = {
    "ZahnR": "SB",
    "RNV": "STR",
    "O-Bus": "Bus",
    "Tram": "STR",
    "EV": "SEV",
    "SKW": "S",
}


def train_presentation(data):
    "do some cosmetic fixes to train type/line and generate a bahn.expert link for it"
    is_hafas = "|" in data["train"]["id"]

    train_type = blanket_replace_train_type.get(
        data["train"]["type"], data["train"]["type"]
    )
    train_line = data["train"]["line"]

    # account for "ME RE2" instead of "RE  "
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
        return (52.20 < lat < 52.45) and (9.56 < lon < 10.0)

    if train_type == "STR" and is_in_hannover(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "Ü"

    # special treatment for VAG Nürnberg U-Bahn
    def is_in_nürnberg(lat, lon):
        return haversine((lat, lon), (49.45, 11.05)) < 10

    if train_type == "U" and is_in_nürnberg(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = f"U{train_line}n"
        train_line = ""

    # bitte beachten sie das verzehrverbot auf kölner stadtgebiet
    def is_in_köln(lat, lon):
        return (50.62 < lat < 51.04) and (6.72 < lon < 7.26)

    if (
        train_type == "STR"
        and is_in_köln(
            data["fromStation"]["latitude"], data["fromStation"]["longitude"]
        )
        and train_line not in ("61", "62", "65")
    ):
        train_type = "STB"

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

    # special treatment for jura
    if train_type == "U" and train_line.casefold().startswith("m"):
        train_type = "M"
    if train_type == "S" and train_line.startswith("L"):
        train_type = "L"

    if "SEV" in train_line or "EV" in train_line:
        train_type = "SEV"

    if "X" in train_line and train_type == "Bus":
        train_line = train_line.replace("X", "")
        train_type = "BusX"

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

    if fhs := status["train"].get("fakeheadsign"):
        return fhs

    # have we already fetched the headsign? just use that.
    cached = DB.DB.execute(
        "SELECT headsign FROM trips WHERE journey_id = ?", (zugid(status),)
    ).fetchone()
    if cached and cached["headsign"]:
        return cached["headsign"]

    def get_headsign_from_stationboard(leg):
        headsign = leg.direction
        train_key = (
            (
                status["train"]["type"]
                + (status["train"]["line"] or status["train"]["no"])
            ),
            headsign,
        )
        return replace_headsign.get(
            train_key,
            headsign,
        )

    def check_same_train(hafas_name, train):
        hafas_name = hafas_name.replace(" ", "")
        train_line = train["type"] + (train["line"] or "").replace(" ", "")
        train_no = train["type"] + train["no"]
        return (
            (hafas_name == train_line)
            or (hafas_name == train_no)
            or (hafas_name == train["type"] == "ZahnR")
        )

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
            if (
                c.id == (status["train"]["hafasId"] or status["train"]["id"])
                or check_same_train(c.name, status["train"])
            )
            and c.dateTime == departure
        ]
        if len(candidates2) == 1:
            headsign = get_headsign_from_stationboard(candidates2[0])
        else:
            for candidate in candidates2:
                trip = hafas.trip(candidate.id)
                stops = [
                    Stopover(
                        stop=trip.destination,
                        arrival=trip.arrival,
                        arrival_delay=trip.arrivalDelay,
                    )
                ]
                if trip.stopovers:
                    stops += trip.stopovers
                if any(
                    stop.stop.id == str(status["toStation"]["uic"])
                    and (
                        stop.arrival
                        and int(stop.arrival.timestamp())
                        == status["toStation"]["scheduledTime"]
                    )
                    for stop in stops
                ):
                    headsign = get_headsign_from_stationboard(candidate)
                    break
            else:
                print_leg = lambda c: f"{c.id} {c.name} {c.direction} {c.dateTime}"
                print(
                    f"can't decide! {status['train']['type']} {status['train']['line']} {status['train']['no']} {departure}",
                    status["fromStation"],
                    status["toStation"],
                    "cand",
                    "\n".join([print_leg(c) for c in candidates]),
                    "cand2",
                    "\n".join([print_leg(c) for c in candidates2]),
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
    "boat": "<:sbbboot:1164446951572525136>",
    "Bus": "<:Bus:1160288158374707241>",
    "BusX": "<:BusX:1166774884156854283>",
    "car": "<:sbbauto:1161317276277031002>",
    "CB": "<:cb:1167885153289388062>",
    "coach": "<:sbbcoach:1164446947592122378>",
    "CJX": "<:Ja:1162760030068678786><:Jb:1162760030903345254>",
    "D": "<:da:1162760033684168724><:db:1162760035760361582>",
    "EC": "<:eca:1162767426337919086><:ecb:1162767427604578305>",
    "ECE": "<:eca:1162767426337919086><:ece:1162767431513681993>",
    "EIC": "<:ia:1163536538391556126><:ib:1163536535732355183>",
    "EN": "<:na:1162760037748441158><:nb:1162760039094812773>",
    "EST": "<:Ta:1163140573486645288><:Tb:1163140572123496649>",
    "Fähre": "<:Faehre:1143105659827658783>",
    "FLX": "<:La:1163141817022283836><:Lb:1163141815575253062>",
    "IC": "<:ca:1162760063384039524><:cb:1162760064298393641>",
    "ICE": "<:ca:1162760063384039524><:Cb:1162760068857597952>",
    "IR": "<:Ia:1162760071269335272><:db:1162760035760361582>",
    "IRE": "<:ia:1162760103032795187><:ib:1162760104345620480>",
    "KAS": "<:KAS:1166775071105372270>",
    "KM": "<:ka:1163537951846842480><:kb:1163537770011185172>",
    "KML": "<:La:1163536524948807710><:Lb:1163536521979248730>",
    "KS": "<:sa:1163536518690906222><:sb:1163536516866392165>",
    "L": "<:lex:1162070841702494208>",
    "M": "<:metro:1162032437065416764>",
    "MEX": "<:ma:1162772943596699729><:mb:1162772944951455838>",
    "NJ": "<:Na:1162760106321117258><:Nb:1162760108221153300>",
    "plane": "<:sbbflug:1161317272397287435>",
    "R": "<:Ra:1162760110536405097><:Rb:1162760111975043072>",
    "RB": "<:Ba:1162760114328043680><:Bb:1162760116261617757>",
    "RE": "<:Ea:1162760127556886639><:Eb:1162760129872138261>",
    "RER": "<:rer:1162070845749997619>",
    "REX": "<:Ea:1162760127556886639><:EXb:1162760134334885948>",
    "RJ": "<:2a:1162760135731589233><:2b:1162760137090551929>",
    "RJX": "<:1a:1162760138277519501><:1b:1162760140458573895>",
    "RS": "<:rs:1162070847645831249>",
    "RT": "<:rt:1163135018328133752>",
    "RUF": "<:ruf:1161314243698761898>",
    "S": "<:SBahn:1102206882527060038>",
    "SB": "<:SB:1160502333143261234>",
    "Schw-B": "<:Schwebebahn:1143108575770726510>",
    "SEV": "<:Sa:1163143892540067880><:Sb:1163143891264999494>",
    "STB": "<:stb:1162051109318295674>",
    "steam": "<:sbbsteam:1162032435459006494>",
    "STR": "<:Tram:1160290093400064060>",
    "SVG": "<:sbbsteam:1162032435459006494> SVG",
    "TER": "<:ta:1162760151384731710><:tb:1162760154769543248>",
    "TGV": "<:Ta:1162760156514357402><:Tb:1162760158854783027>",
    "TLK": "<:ta:1163536529273147473><:tb:1163536526815273000>",
    "U": "<:U_:1160288163214921889>",
    "U1": "<:u1:1160998507533058098>",
    "U2": "<:u2:1160998509059776622>",
    "U3": "<:u3:1160998510997553161>",
    "U4": "<:u4:1160998512742383777>",
    "U5": "<:u5:1160998515967799306>",
    "U6": "<:u6:1160998518744424488>",
    "U1n": "<:U1:1166773948097245256>",
    "U2n": "<:U2:1166773949804322897>",
    "U3n": "<:U3:1166773945341595768>",
    "Ü": "<:UE:1160288194730930196>",
    "walk": "<:sbbwalk:1161321193001992273>",
    "WB": "<:wa:1162760160129855609><:wb:1162760161417515058>",
    "WLB": "<:wlb:1164614809887719474>",
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
tram_color = "#c5161c"

train_type_color = {
    k: discord.Color.from_str(v)
    for (k, v) in {
        "AST": "#ffd700",
        "ATS": "#0096d8",
        "Bus": "#a3167e",
        "BusX": "#a3167e",
        "CB": "#c91432",
        "D": long_distance_color,
        "EC": long_distance_color,
        "ECE": long_distance_color,
        "EIC": long_distance_color,
        "EN": night_train_color,
        "EST": long_distance_color,
        "CJX": regional_express_color,
        "Fähre": "#00a4db",
        "FLX": "#72d800",
        "IC": long_distance_color,
        "ICE": long_distance_color,
        "IR": long_distance_color,
        "IRE": regional_express_color,
        "KAS": tram_color,
        "KM": regional_color,
        "KML": regional_color,
        "KS": regional_color,
        "L": s_bahn_color,
        "M": "#014e8d",
        "MEX": regional_color,
        "NJ": night_train_color,
        "R": regional_color,
        "RB": regional_color,
        "RE": regional_express_color,
        "RER": s_bahn_color,
        "REX": regional_express_color,
        "RJ": "#c63131",
        "RJX": "#c63131",
        "RS": s_bahn_color,
        "RT": tram_color,
        "RUF": "#ffd700",
        "S": s_bahn_color,
        "SB": "#2e2e7d",
        "Schw-B": "#4896d2",
        "STB": tram_color,
        "STR": tram_color,
        "TER": regional_color,
        "TLK": long_distance_color,
        "TGV": long_distance_color,
        "U": "#014e8d",
        "U1": "#ed1d26",
        "U2": "#9e50af",
        "U3": "#f47114",
        "U4": "#1ea366",
        "U5": "#0098a1",
        "U6": "#926131",
        "U1n": "#176fc1",
        "U2n": "#ed1c24",
        "U3n": "#4cc3bc",
        "Ü": "#78b41d",
        "WB": "#2e86ce",
        "WLB": "#175a97",
    }.items()
}

not_registered_embed = discord.Embed(
    title="Oops!",
    color=train_type_color["U1"],
    description="It looks like you're not registered with the travelynx relay bot yet.\n"
    "If you want to fix this minor oversight, use **/register** today!",
)


# this is specifically because Knielinger Allee/Städt. Klinikum, Karlsruhe is very long and doesn't fit in one line
# but look how maintainable this is, you could add any city you like
# you could even abbreviate Berlin to B
# no idea why you would but it's possible now
replace_city_suffix_with_prefix = {"Karlsruhe": "KA", "Leipzig": "L"}

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
    # 48 stunden ringbahn challenge
    ("S41", "Ring S41"): "Ring ↻",
    ("S42", "Ring S42"): "Ring ↺",
}
