"various helper functions that do more than just pure formatting logic. the icon library lives in here too"
from datetime import datetime, timedelta
from zoneinfo import available_timezones, ZoneInfo
import json
import random
import re
import string
import traceback

import discord
from aiohttp import ClientSession
from pyhafas import HafasClient
from pyhafas.profile import DBProfile
from pyhafas.types.fptf import Stopover
from haversine import haversine

from . import database as DB

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)


def zugid(data):
    """identify a user-trip by its departure time + hafas/iris specific trip id.
    forms the primary key of the trips table together with user id."""
    return f'{data["train"]["id"]}:{data["fromStation"]["scheduledTime"]}'


# globally used timezone
tz = ZoneInfo("Europe/Berlin")
available_tzs = available_timezones()
hafas = HafasClient(DBProfile())


def parse_manual_time(time, timezone):
    try:
        dt = datetime.fromisoformat(time)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone)
        return dt
    except ValueError:
        time = time.split(":")
        return datetime.now(tz=timezone).replace(
            hour=int(time[0]),
            minute=int(time[1]),
            second=0,
        )


async def is_token_valid(token):
    "check if a status api token actually works"
    async with ClientSession() as session:
        async with session.get(
            f"{config['travelynx_instance']}/api/v1/status/{token}"
        ) as r:
            try:
                data = await r.json()
                if r.status == 200 and not "error" in data:
                    return True
                print(f"token {token} invalid: {r.status} {data}")
                return False
            except:  # pylint: disable=bare-except
                print(f"error verifying token {token}:")
                traceback.print_exc()


def format_time(sched, actual, relative=False, timezone=tz):
    """render a nice timestamp for arrival/departure that includes delay information.
    relative=True creates a discord relative timestamp that looks like "in 3 minutes"
    and updates automatically, used for the embed's final destination arrival time.
    """
    time = datetime.fromtimestamp(actual, tz=timezone)

    if relative:
        return f"<t:{int(time.timestamp())}:R>"

    diff = ""
    if actual > sched:
        diff = (actual - sched) // 60
        diff = f" +{diff}′"
    elif actual < sched:
        diff = (sched - actual) // 60
        diff = f" -{diff}′"

    return f"**{time:%H:%M}{diff}**"


def format_delta(delta):
    "turn a timedelta into  representation like 1h37m"
    h, m = divmod(delta, timedelta(hours=1))
    m = int(m.total_seconds() // 60)
    if h > 0:
        return f"{h}:{m:02}h"
    return f"{m}′"


def format_timezone(timezone):
    "print a timezone with name and utc offset"
    offset = timezone.utcoffset(datetime.now()).seconds / 3600
    if offset > 12:
        offset -= 24

    if offset == int(offset):
        return f"{timezone.key} (UTC{'+' if offset > 0 else ''}{int(offset)})"
    else:
        offset_h = int(offset)
        offset_m = int((offset - offset_h) * 60)
        if offset < 0:
            offset_m *= -1
        return f"{timezone.key} (UTC{'+' if offset > 0 else ''}{offset_h}:{offset_m})"


blanket_replace_train_type = {
    "RNV": "STR",
    "O-Bus": "Bus",
    "Tram": "STR",
    "EV": "SEV",
    "SKW": "S",
    "SVG": "FEX",
    "west": "WB",
}


def train_presentation(data):
    "do some cosmetic fixes to train type/line and generate a bahn.expert link for it"
    is_hafas = "|" in data["train"]["id"]

    operator = None
    cached = DB.DB.execute(
        "SELECT hafas_data FROM trips WHERE journey_id = ? AND hafas_data != '{}'",
        (zugid(data),),
    ).fetchone()
    if cached:
        operator = json.loads(cached["hafas_data"]).get("operator")

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

    if train_type == "S" and operator == "Albtal-Verkehrs-Gesellschaft mbH":
        train_type = "KAS"

    if train_type == "STB" and operator == "üstra Hannoversche Verkehrsbetriebe AG":
        train_type = "Ü"

    # the dutch
    if train_type == "RE" and operator == "Nederlandse Spoorwegen":
        train_type = "SPR"
    if not train_type and operator in (
        "Blauwnet",
        "Arriva Nederland",
        "RRReis",
        "R-net",
    ):
        train_type = "ST"

    # special treatment for VAG Nürnberg U-Bahn
    def is_in_nürnberg(lat, lon):
        return haversine((lat, lon), (49.45, 11.05)) < 10

    if train_type == "U" and is_in_nürnberg(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = f"U{train_line}n"
        train_line = ""

    # special treatment for Hamburg HOCHBAHN
    def is_in_hamburg(lat, lon):
        return haversine((lat, lon), (53.54, 10.01)) < 30

    if train_type == "U" and is_in_hamburg(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = f"U{train_line}h"
        train_line = ""

    # special treatment for Berlin BVG U-Bahn
    def is_in_berlin(lat, lon):
        return haversine((lat, lon), (52.52, 13.41)) < 30

    if train_type == "U" and is_in_berlin(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = f"U{train_line}b"
        train_line = ""

    # special treatment for München MVG U-Bahn
    def is_in_münchen(lat, lon):
        return haversine((lat, lon), (48.15, 11.54)) < 30

    if train_type == "U" and is_in_münchen(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = f"U{train_line}m"
        train_line = ""

    # special treatment for Frankfurt RMV U-Bahn
    def is_in_frankfurt(lat, lon):
        return haversine((lat, lon), (50.11, 8.68)) < 30

    if train_type == "U" and is_in_frankfurt(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = f"U{train_line}f"
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

    # special treatment for stadtbahn rhein-ruhr
    def is_in_nrw(lat, lon):
        return (51.06 < lat < 51.68) and (6.46 < lon < 7.77)

    if train_type == "U" and is_in_nrw(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "STB"

    if train_type == "STB":
        train_line = train_line.removeprefix("U")

    if train_type == "RT":
        train_type = "STR"
        train_line = "RT" + train_line

    # special treatment for wien U6 (and the others too i guess)
    if train_type == "U" and data["fromStation"]["name"].startswith("Wien "):
        train_type = data["fromStation"]["name"][-3:-1]
        train_line = ""
    if train_type == "Bus" and data["fromStation"]["name"].startswith("Wien "):
        train_line = train_line.replace("A", "ᴀ").replace("B", "ʙ")

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
        train_line = train_line.removeprefix("L")
        train_type = "SL"

    if train_type == "S" and train_line.startswith("N"):
        train_type = "SN"

    if train_type == "Bus" and train_line.startswith("N"):
        train_type = "BusN"

    if "SEV" in train_line or "EV" in train_line:
        train_type = "SEV"

    if "X" in train_line and train_type == "Bus":
        train_line = train_line.replace("X", "")
        train_type = "BusX"

    link = "https://bahn.expert/details"
    # if HAFAS, add journeyid to link to make sure it gets the right one
    if jid := data["train"]["hafasId"] or (data["train"]["id"] if is_hafas else None):
        jid = jid.replace(
            "#", "%23"
        )  # for some reason urlencode doesn't eat the first one???
        link += f"/0/{data['fromStation']['scheduledTime'] * 1000}/?jid={jid}"
    # if we don't have an hafas jid link it to a station instead to disambiguate
    else:
        link += (
            f"/{data['train']['type']}%20{data['train']['no']}/"
            + str(data["fromStation"]["scheduledTime"] * 1000)
            + f"/?station={data['fromStation']['uic']}"
        )

    if "travelhookfaked" in data["train"]["id"]:
        link = None

    link = data.get("link", link)

    if link:
        # reuse IDs of previously shortened URLs
        previd = DB.Link.find_by_long(long_url=link)

        if previd:
            randid = previd.short_id
        else:
            # handle potential collisions
            while True:
                randid = random_id()
                if not DB.Link.find_by_short(short_id=randid):
                    break

            DB.Link(short_id=randid, long_url=link).write()

        link = config["shortener_url"] + "/" + randid

    return (train_type, train_line, link)


def format_composition_element(element):
    composition_regex = re.compile(
        r"(?P<count>\d+x)? ?((?P<class>\d{3,4}) ?(?P<number>[\dx-]{,5}) ?)?(?P<name>.*)"
    )
    if match := composition_regex.match(element):
        out = ""
        if count := match["count"]:
            out += count[:-1] + "× "
        if numbers := match[2]:
            out += f"**{match['class']}** {match['number']} "
        if name := match["name"]:
            out += f"_{name}_"
        return out.strip()

    return element


def trip_length(trip):
    if dist := trip.status.get("distance"):
        return dist

    trip_length = 0
    if trip.hafas_data:
        trip_started = False
        for i, point in enumerate(trip.hafas_data["polyline"]):
            if (
                point["eva"] == trip.status["fromStation"]["uic"]
                or point["name"] == trip.status["fromStation"]["name"]
            ):
                trip_started = True
            if (
                point["eva"] == trip.status["toStation"]["uic"]
                or point["name"] == trip.status["toStation"]["name"]
                or i + 1 == len(trip.hafas_data["polyline"])
            ):
                break
            if trip_started:
                trip_length += haversine(
                    (point["lat"], point["lon"]),
                    (
                        trip.hafas_data["polyline"][i + 1]["lat"],
                        trip.hafas_data["polyline"][i + 1]["lon"],
                    ),
                )

    return trip_length


def fetch_headsign(status):
    "try to fetch a train headsign or destination name from HAFAS"

    if fhs := status["train"].get("fakeheadsign"):
        return fhs

    if cached := DB.DB.execute(
        "SELECT headsign, json_patch(travelynx_status, status_patch) as status "
        "FROM trips WHERE journey_id = ?",
        (zugid(status),),
    ).fetchone():
        return (
            json.loads(cached["status"])["train"].get("fakeheadsign")
            or cached["headsign"]
            or "?"
        )
    return "?"


def random_id():
    choices = string.ascii_letters + string.digits
    randid = "".join(random.choice(choices) for _ in range(7))
    return randid


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
    COMPOSITION = "<:wr:1222613801472622623>"
    TRIP_SPEED = "<:trip:1222616284253130873>"
    TRIP_SUM = "<:sum:1222616286291562558>"
    DESTINATION = "<:to:1222613802873520189>"
    COMMENT = "<:note:1222613807507968121>"
    WARN = "<:warn:1225520405851410614>"
    INFO = "<:info:1225520403670241381>"


train_type_emoji = {
    "A": "<:A_:1173641257646559312>",
    "AST": "<:ast:1161314515355439126>",
    "ATS": "<:ATS:1170751624612954232>",
    "bike": "<:sbbvelo:1161317270065262683>",
    "boat": "<:sbbboot:1164446951572525136>",
    "Bus": "<:Bus:1160288158374707241>",
    "BusN": "<:BusN:1196411699859816458>",
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
    "FEX": "<:fex0:1235130292096991243><:fex1:1235130290712612915>",
    "FLX": "<:La:1163141817022283836><:Lb:1163141815575253062>",
    "IC": "<:ca:1162760063384039524><:cb:1162760064298393641>",
    "ICD": "<:ca:1162760063384039524><:icd1:1196520061226209310>",
    "ICE": "<:ca:1162760063384039524><:Cb:1162760068857597952>",
    "ICN": "<:icn0:1196520063621136454><:icn1:1196520065244344501>",
    "IR": "<:Ia:1162760071269335272><:db:1162760035760361582>",
    "IRE": "<:ia:1162760103032795187><:ib:1162760104345620480>",
    "KAS": "<:KAS:1166775071105372270>",
    "KM": "<:ka:1163537951846842480><:kb:1163537770011185172>",
    "KML": "<:La:1163536524948807710><:Lb:1163536521979248730>",
    "KS": "<:sa:1163536518690906222><:sb:1163536516866392165>",
    "L": "<:l0:1170703852429910016><:Rb:1162760111975043072>",
    "M": "<:metro:1162032437065416764>",
    "MEX": "<:m0:1170726078319431750><:m1:1170726076855627796>",
    "NJ": "<:Na:1162760106321117258><:Nb:1162760108221153300>",
    "plane": "<:sbbflug:1161317272397287435>",
    "R": "<:Ra:1162760110536405097><:Rb:1162760111975043072>",
    "RB": "<:Ba:1162760114328043680><:Bb:1162760116261617757>",
    "RE": "<:Ea:1162760127556886639><:Eb:1162760129872138261>",
    "RER": "<:RER:1173641262163836979>",
    "REX": "<:Ea:1162760127556886639><:EXb:1162760134334885948>",
    "RJ": "<:2a:1162760135731589233><:2b:1162760137090551929>",
    "RJX": "<:1a:1162760138277519501><:1b:1162760140458573895>",
    "RS": "<:RS:1173641264705568798>",
    "RUF": "<:ruf:1161314243698761898>",
    "S": "<:SBahn:1102206882527060038>",
    "SB": "<:SB:1170796225927331962>",
    "Schw-B": "<:SchwB:1170796229203079218>",
    "SE": "<:se0:1196424800055349348><:se1:1196424803066843136>",
    "SEV": "<:Sa:1163143892540067880><:Sb:1163143891264999494>",
    "SL": "<:SL:1173641259177484358>",
    "SN": "<:SN:1170704004515385385>",
    "SPR": "<:ns0:1170747131087306783><:ns1:1170747129728348171>",
    "ST": "<:s0:1170747126955917452><:s1:1170747125131391102>",
    "STB": "<:STB:1189298046564057148>",
    "steam": "<:sbbsteam:1162032435459006494>",
    "STR": "<:Tram:1160290093400064060>",
    "TER": "<:ta:1162760151384731710><:tb:1162760154769543248>",
    "TGV": "<:Ta:1162760156514357402><:Tb:1162760158854783027>",
    "TLK": "<:ta:1163536529273147473><:tb:1163536526815273000>",
    "U": "<:U_:1189298049990799471>",
    "U1": "<:UWien1:1189299767042396320>",
    "U2": "<:UWien2:1189299765435973642>",
    "U3": "<:UWien3:1189299763007459378>",
    "U4": "<:UWien4:1189299761526878330>",
    "U5": "<:UWien5:1189299759358418986>",
    "U6": "<:UWien6:1189299758062371006>",
    "U1b": "<:UBerlin1:1189300551968632832>",
    "U2b": "<:UBerlin2:1189300553243689081>",
    "U3b": " <:UBerlin3:1189300555542188103>",
    "U4b": "<:UBerlin4:1189300556972433408>",
    "U5b": "<:UBerlin5:1189300559128309829>",
    "U6b": "<:UBerlin6:1189300560302719047>",
    "U7b": "<:UBerlin7:1189300561791684768>",
    "U8b": "<:UBerlin8:1189300564677361744>",
    "U9b": "<:UBerlin9:1189300566246039633>",
    "U12b": "<:UBerlin12:1189300568557113354>",
    "U1f": "<:uffm1:1202307199934926898>",
    "U2f": "<:uffm2:1202307196533362739>",
    "U3f": "<:uffm3:1202307195325382676>",
    "U4f": "<:uffm4:1202307193223774238>",
    "U5f": "<:uffm5:1202307192024485919>",
    "U6f": "<:uffm6:1202307190694891651>",
    "U7f": "<:uffm7:1202307188295471166>",
    "U8f": "<:uffm8:1202307186823266374>",
    "U9f": "<:uffm9:1202307183887527987>",
    "U1h": "<:UHH1:1189301085794484244>",
    "U2h": "<:UHH2:1189301086981472317>",
    "U3h": "<:UHH3:1189301089435136120>",
    "U4h": "<:UHH4:1189301091125432492>",
    "U1m": "<:UM1:1189301541698556005>",
    "U2m": "<:UM2:1189301543074287767>",
    "U3m": "<:UM3:1189301545569894470>",
    "U4m": "<:UM4:1189301546933043320>",
    "U5m": "<:UM5:1189301549600604180>",
    "U6m": "<:UM6:1189301551009906780>",
    "U7m": "<:UM7:1189301553929134200>",
    "U8m": "<:UM8:1189301555422310501>",
    "U1n": "<:UNbg1:1189300098887319572>",
    "U2n": "<:UNbg2:1189300100040757300>",
    "U3n": "<:UNbg3:1189300102351818852>",
    "Ü": "<:UE:1189298047784591431>",
    "walk": "<:sbbwalk:1161321193001992273>",
    "WB": "<:wa:1162760160129855609><:wb:1162760161417515058>",
    "WLB": "<:wlb:1164614809887719474>",
    "ZahnR": "<:zahnr:1226231292954153011>",
}

OEBB_EMOJI = "<:oebb1:1209147711274614815><:oebb2:1209147709437509663>"


def get_train_emoji(train_type):
    "return a train emoji or placeholder"
    return train_type_emoji.get(
        train_type, f"<:sbbzug:1160275971266576494> {train_type}"
    )


bus_color = "#a3167e"
long_distance_color = "#ff0404"
regional_express_color = "#ff4f00"
regional_color = "#204a87"
s_bahn_color = "#2c8e4e"
metro_color = "#014e8d"
night_train_color = "#282559"
tram_color = "#c5161c"

train_type_color = {
    k: discord.Color.from_str(v)
    for (k, v) in {
        "A": "#f49100",
        "AST": "#ffd700",
        "ATS": "#0096d8",
        "Bus": bus_color,
        "BusN": bus_color,
        "BusX": bus_color,
        "CB": "#c91432",
        "D": long_distance_color,
        "EC": long_distance_color,
        "ECE": long_distance_color,
        "EIC": long_distance_color,
        "EN": night_train_color,
        "EST": long_distance_color,
        "CJX": regional_express_color,
        "Fähre": "#00a4db",
        "FEX": regional_express_color,
        "FLX": "#72d800",
        "IC": long_distance_color,
        "ICD": long_distance_color,
        "ICE": long_distance_color,
        "ICN": night_train_color,
        "IR": long_distance_color,
        "IRE": regional_express_color,
        "KAS": tram_color,
        "KM": regional_color,
        "KML": regional_color,
        "KS": regional_color,
        "L": s_bahn_color,
        "M": metro_color,
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
        "RUF": "#ffd700",
        "S": s_bahn_color,
        "SB": metro_color,
        "Schw-B": metro_color,
        "SE": regional_express_color,
        "SL": s_bahn_color,
        "SN": s_bahn_color,
        "STB": tram_color,
        "STR": tram_color,
        "TER": regional_color,
        "TLK": long_distance_color,
        "TGV": long_distance_color,
        "U": metro_color,
        "U1": "#ed1d26",
        "U2": "#9e50af",
        "U3": "#f47114",
        "U4": "#1ea366",
        "U5": "#0098a1",
        "U6": "#926131",
        "U1b": "#7dad4c",
        "U2b": "#da421e",
        "U3b": "#16683d",
        "U4b": "#f0d722",
        "U5b": "#7e5330",
        "U6b": "#8c6dab",
        "U7b": "#528dba",
        "U8b": "#224f86",
        "U9b": "#f3791d",
        "U12b": "#7dad4c",
        "U1f": "#c52b1e",
        "U2f": "#00ab4f",
        "U3f": "#345aaf",
        "U4f": "#fc5cac",
        "U5f": "#0c7d3e",
        "U6f": "#0082ca",
        "U7f": "#f19e2d",
        "U8f": "#ca7fbe",
        "U9f": "#ffd939",
        "U1h": "#0073c0",
        "U2h": "#ff2e17",
        "U3h": "#ffd939",
        "U4h": "#00b2b1",
        "U1m": "#447335",
        "U2m": "#bb0534",
        "U3m": "#e4692a",
        "U4m": "#35aa83",
        "U5m": "#b87c0a",
        "U6m": "#2362ae",
        "U7m": "#447335",
        "U8m": "#e4692a",
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

db_replace_group_classes = {
    "808": "402",  # ICE 2
    "812": "412",  # ICE 4
    "826": "526",  # FLIRT Akku
    "928": "628",  # BR 628
}

db_classes3 = {
    "401": "ICE 1",
    "402": "ICE 2",
    "403": "ICE 3",
    "406": "ICE 3M",
    "407": "ICE 3 Velaro",
    "408": "ICE 3neo",
    "411": "ICE-T",
    "412": "ICE 4",
    "415": "ICE-T",
    "425": "Quietschie",
    "440": "Continental",
    "442": "Talent 2",
    "445": "KISS",
    "460": "Desiro ML",
    "462": "Desiro HC",
    "463": "Mireo",
    "464": "Mireo Smart",
    "526": "FLIRT Akku",
    "554": "iLINT",
    "563": "Mireo Plus H",
    "620": "LINT 81",
    "621": "LINT 81",
    "622": "LINT 54",
    "623": "LINT 41",
    "631": "LINK",
    "632": "LINK",
    "633": "LINK",
    "640": "LINT 27",
    "641": "Coradia A TER",
    "642": "Desiro Classic",
    "643": "Talent 1",
    "644": "Talent 1",
    "648": "LINT 41",
    "650": "RegioShuttle",
}
db_classes4 = {
    "1430": "FLIRT",
    "0427": "FLIRT 1",
    "1427": "FLIRT 3",
    "3427": "FLIRT 3XL",
    "0428": "FLIRT 1",
    "1428": "FLIRT 3",
    "1429": "FLIRT 3",
    "2429": "FLIRT 3 (+NL)",
    "3429": "FLIRT 3XL",
    "1430": "FLIRT 3",
}
db_classes_subtype = {
    "4260": "Babyquietschie",
    "4261": "FLIRT",
    "4290": "FLIRT 1",
    "4291": "FLIRT 3",
}


def describe_class(uic_id: str):
    if not len(uic_id) == 12:
        return None
    # 9x 80 1234 5xx x
    # 234 is commonly reported as "baureihe" in germany, but the register number
    # actually has four digits 1234. sometimes baureihe codes are shared too
    # and you have to determine the actual type by the first digit of the trainset number, 5
    baureihe3 = uic_id[5:8]  # 234
    # for ICE2/ICE4 and two-car multiple units we might have the "wrong" number at the
    # end of the train, replace it with the more commonly used number for that group
    baureihe3 = db_replace_group_classes.get(baureihe3, baureihe3)
    baureihe4 = uic_id[4:8]  # 1234
    baureihe_subtype = uic_id[5:9]  # 2345
    if baureihe3 in db_classes3:
        return db_classes3[baureihe3]
    if baureihe4 in db_classes4:
        return db_classes4[baureihe4]
    if baureihe_subtype in db_classes_subtype:
        return db_classes_subtype[baureihe_subtype]
    return None


# shorthand or better sounding names for HAFAS operator
replace_operators = {
    "Albtal-Verkehrs-Gesellschaft mbH": "der AVG",
    "Bayerische Regiobahn": "der bayerischen Regiobahn",
    "DB Fernverkehr AG": "DB Fernverkehr",
    "DB Regio AG S-Bahn München": "der S-Bahn München",
    "Go-Ahead Baden-Württemberg GmbH": "Go-Ahead",
    "Go-Ahead Bayern GmbH": "Go-Ahead",
    "Österreichische Bundesbahnen": "den ÖBB",
    "Ostdeutsche Eisenbahn GmbH": "der ODEG",
    "S-Bahn Hannover (Transdev)": "der S-Bahn Hannover",
    "Schweizerische Bundesbahnen": "der SBB",
    "üstra Hannoversche Verkehrsbetriebe AG": "dem ÜMO",
}
known_operator_pronouns = {
    "metronom": "dem",
    "SNCF": "der",
    "Wiener Linien": "den",
}


def decline_operator_with_article(operator: str):
    "pick the correct 'mit [der/den/dem]' depending on the operator name"
    if not operator:
        return ""
    if operator in replace_operators:
        return f" mit {replace_operators[operator]}"
    if operator in known_operator_pronouns:
        return f" mit {known_operator_pronouns[operator]} {operator}"
    if operator.startswith("DB Regio"):
        return " mit DB Regio"
    if operator.endswith("mbH"):
        return f" mit der {operator}"
    if operator.split(" ")[0].casefold().endswith("bahn"):
        return f" mit der {operator}"

    return f"mit {operator}"


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
    ("STR13", "Hemmingen (Hannover)"): "Hemmingen",
    # jesus christ KVV please fix this nonsense
    ("S2", "Blankenloch Nord, Stutensee"): "Blankenloch",
    ("S2", "Daxlanden Dornröschenweg, Karlsruhe"): "Rheinstrandsiedlung",
    ("S2", "Hagsfeld Reitschulschlag (Schleife), Karlsruhe"): "Reitschulschlag",
    ("S2", "Mörsch Bach-West, Rheinstetten"): "Rheinstetten",
    ("S2", "Spöck Richard-Hecht-Schule, Stutensee"): "Spöck",
    # 48 stunden ringbahn challenge
    ("S41", "Ring S41"): "Ring ↻",
    ("S42", "Ring S42"): "Ring ↺",
    ("S45", "Flughafen BER - Terminal 1-2 (S-Bahn)"): "Flughafen BER T 1-2",
    # Stuttgart my behated
    ("STBU5", "Leinfelden Bahnhof, Leinfelden-Echterdingen"): "Leinfelden Bf",
    ("STBU6", "Stuttgart Flughafen/Messe, Leinfelden-Echterdingen"): "Flughafen/Messe",
}
