"various helper functions that do more than just pure formatting logic. the icon library lives in here too"
from datetime import datetime, timedelta
from zoneinfo import available_timezones, ZoneInfo
import json
import random
import re
import string
import traceback
import urllib

import discord
from aiohttp import ClientSession
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
train_types_with_realtime_data_on_bahnexpert_maybe_i_hope = (
    "EC",
    "ECE",
    "EN",
    "EST",
    "FEX",
    "FLX",
    "IC",
    "ICE",
    "MEX",
    "NJ",
    "RB",
    "RE",
    "RS",
    "RJ",
    "RJX",
    "TGV",
    "WB",
)


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


async def is_import_token_valid(token):
    "check if a import api token actually works"
    async with ClientSession() as session:
        async with session.post(
            f"{config['travelynx_instance']}/api/v1/import",
            json={
                "token": token,
                "dryRun": True,
                "train": {
                    "type": "S",
                    "line": "6",
                    "no": "30634",
                },
                "fromStation": {"name": "Essen Hbf", "scheduledTime": 1556083680},
                "toStation": {"name": "Essen Stadtwald", "scheduledTime": 1556083980},
                "intermediateStops": [
                    "Essen Süd",
                ],
            },
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


def generate_train_link(data):
    hafas_data = DB.DB.execute(
        "SELECT hafas_data FROM trips WHERE journey_id = ? AND hafas_data != '{}'",
        (zugid(data),),
    ).fetchone()
    if hafas_data:
        hafas_data = json.loads(hafas_data["hafas_data"])
    else:
        hafas_data = {}

    link = None
    # if train starts in germany and is a "real train" (said in an offensively gatekeepy way. just to be clear.)
    # bahn.expert may have confirmed realtime data for it -- construct a link with the train number
    # otherwise, play it safe and keep the number out to prevent ambiguities for local transit
    if data["backend"]["type"] == "IRIS-TTS" or (
        (data["train"]["no"] or hafas_data.get("no"))
        and (8000000 < data["fromStation"]["uic"] < 8100000)
        and any(
            data["train"]["type"] == tt
            or (data["train"]["line"] and data["train"]["line"].startswith(tt))
            for tt in train_types_with_realtime_data_on_bahnexpert_maybe_i_hope
        )
    ):
        link = (
            "https://bahn.expert/details"
            + f"/{data['train']['type']}%20{data['train']['no'] or hafas_data.get('no')}/"
            + str(data["fromStation"]["scheduledTime"] * 1000)
            + f"/?station={data['fromStation']['uic']}"
        )
    elif (jid := hafas_data.get("id", data["train"]["id"])) and (
        "#" in jid or "|" in jid
    ):
        hafas = data["backend"]["name"]
        if hafas == "bahn.de":
            hafas = "&dbris=bahn.de"
        elif data["backend"]["type"] == "travelcrab.friz64.de":
            hafas = "ÖBB"
        link = (
            "https://dbf.finalrewind.org/z/"
            + urllib.parse.quote(jid)
            + f"?hafas={hafas}"
        )
    else:
        link = None

    link = data.get("link", link)
    if link:
        link = DB.Link.make(link)
        return f"{config['shortener_url']}/{link.short_id}"


def format_composition_element(element):
    composition_regex = re.compile(
        r"(?P<count>\d+x)? ?((?P<class>\d{3,4}) ?(?P<number>[\dx-]{,5}($|\s)))?(?P<name>.*)"
    )
    collapse_spaces = re.compile(r"\s+")
    if match := composition_regex.match(element):
        out = ""
        if count := match["count"]:
            out += count[:-1] + "× "
        if numbers := match[2]:
            out += f"**{match['class']}** {match['number']} "
        if name := match["name"]:
            out += f"*{name}*"
        return collapse_spaces.sub(" ", out.strip())

    return element


def trip_length(trip):
    if dist := trip.status.get("distance"):
        return dist

    trip_length = 0
    if polyline := trip.hafas_data.get("polyline"):
        trip_started = False
        for i, point in enumerate(polyline):
            if (
                point["eva"] == trip.status["fromStation"]["uic"]
                or point["name"] == trip.status["fromStation"]["name"]
            ):
                trip_started = True
            if (
                point["eva"] == trip.status["toStation"]["uic"]
                or point["name"] == trip.status["toStation"]["name"]
                or i + 1 == len(polyline)
            ):
                break
            if trip_started:
                trip_length += haversine(
                    (point["lat"], point["lon"]),
                    (
                        polyline[i + 1]["lat"],
                        polyline[i + 1]["lon"],
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


bus_color = "#a3167e"
long_distance_color = "#ff0404"
regional_express_color = "#ff4f00"
regional_color = "#204a87"
s_bahn_color = "#2c8e4e"
metro_color = "#014e8d"
night_train_color = "#282559"
tram_color = "#c5161c"

# TODO fix and delete the last usage of these
train_type_color = {
    k: discord.Color.from_str(v)
    for (k, v) in {
        "S": s_bahn_color,
        "SB": metro_color,
        "U1": "#ed1d26",
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
    # given the UIC number 9x 80 1234 5xx x:
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
    "Berliner Verkehrsbetriebe": "der BVG",
    "Bayerische Regiobahn": "der bayerischen Regiobahn",
    "DB Fernverkehr AG": "DB Fernverkehr",
    "DB Regio AG S-Bahn München": "der S-Bahn München",
    "Graz-Köflacher Bahn und Busbetrieb GmbH": "der GKB",
    "Kölner Verkehrs-Betriebe": "der KVB",
    "oberpfalzbahn - Die Länderbahn GmbH DLB": "der oberpfalzbahn",
    "Österreichische Bundesbahnen": "den ÖBB",
    "Ostdeutsche Eisenbahn GmbH": "der ODEG",
    "Rhein-Neckar-Verkehr GmbH": "der RNV",
    "Rhein-Neckar-Verkehr GmbH (Oberrheinische Eisenbahn)": "der RNV",
    "Rhein-Neckar-Verkehr GmbH (Rhein-Haardtbahn)": "der RNV",
    "S-Bahn Hannover (Transdev)": "der S-Bahn Hannover",
    "Schweizerische Bundesbahnen": "der SBB",
    "Schweizerische Bundesbahnen SBB": "der SBB",  # bls hafas spelling
    "Schweizerische Südostbahn (sob)": "der SOB",
    "SWEG Südwestdeutsche Landesverkehrs-GmbH": "der SWEG",
    "Transport publics de la Région Lausannoise": "tl",
    "Transports Publics de la Région Lausannoise sa": "tl",  # bls hafas spelling
    "üstra Hannoversche Verkehrsbetriebe AG": "dem ÜMO",
    "VBB - Verkehrsbetriebe Burgenland GesmbH": "den Verkehrsbetrieben Burgenland",
    "Verkehrsbetriebe der Stadt St.Gallen": "vbsg",
    "Wiener Linien GmbH & Co KG": "den Wiener Linien",  # öbb hafas spelling
}
known_operator_pronouns = {
    "CTS": "der",
    "metronom": "dem",
    "SNCF": "der",
    "Wiener Linien": "den",
}


def decline_operator_with_article(operator: str):
    "pick the correct 'mit [der/den/dem]' depending on the operator name"
    if not operator or operator == "Nahreisezug":
        return ""
    if operator in replace_operators:
        return f" mit {replace_operators[operator]}"
    if operator in known_operator_pronouns:
        return f" mit {known_operator_pronouns[operator]} {operator}"
    if operator.startswith("DB Regio"):
        return " mit DB Regio"
    if operator.endswith("mbH") or operator.endswith("AG"):
        return f" mit der {operator}"
    if operator.split(" ")[0].casefold().endswith("bahn"):
        return f" mit der {operator}"

    return f" mit {operator}"


# this is specifically because Knielinger Allee/Städt. Klinikum, Karlsruhe is very long and doesn't fit in one line
# but look how maintainable this is, you could add any city you like
# you could even abbreviate Berlin to B
# no idea why you would but it's possible now
replace_city_suffix_with_prefix = {
    "Karlsruhe": "KA",
    "Leipzig": "L",
    "Ludwigsh": "LU",
    "Ludwigshafen": "LU",
    "Ludwigshafen am Rhein": "LU",
    "Mannheim": "MA",
}

replace_headsign = {
    # Vienna
    ("U1", "Wien Alaudagasse (U1)"): "Alaudagasse",
    ("U1", "Wien Leopoldau Bahnhst (U1)"): "Leopoldau",
    ("U1", "Wien Oberlaa (U1)"): "Oberlaa",
    ("U2", "Wien Karlsplatz (U2)"): "Karlsplatz",
    ("U2", "Wien Seestadt (U2)"): "Seestadt",
    ("U3", "Wien Ottakring Bahnhst (U3)"): "Ottakring",
    ("U3", "Wien Simmering Bahnhof (U3)"): "Simmering",
    ("U4", "Wien Heiligenstadt Bahnhof (U4)"): "Heiligenstadt",
    ("U4", "Wien Hütteldorf Bahnhof (U4)"): "Hütteldorf",
    ("U4", "Wien Heiligenstadt Bf (U4)"): "Heiligenstadt",
    ("U4", "Wien Hütteldorf Bf (U4)"): "Hütteldorf",
    ("U6", "Wien Floridsdorf Bf (U6)"): "Floridsdorf",
    ("U6", "Wien Floridsdorf Bahnhof (U6)"): "Floridsdorf",
    ("U6", "Wien Siebenhirten (U6)"): "Siebenhirten",
    (
        "Tram30",
        "Wien Floridsdorf Bahnhof (Schleife Leopold-Ferstl-",
    ): "Wien Floridsdorf Bahnhof",
    # Hannover
    ("STB1", "Laatzen (GVH)"): "Laatzen",
    ("STB1", "Langenhagen (Hannover) (GVH)"): "Langenhagen",
    ("STB1", "Sarstedt (Endpunkt GVH)"): "Sarstedt",
    ("STB2", " Gleidingen, Laatzen"): "Gleidingen",
    ("STB3", "Altwarmbüchen, Isernhagen"): "Altwarmbüchen",
    ("STB9", "Empelde (Bus/Tram), Ronnenberg"): "Empelde",
    ("STB13", "Hemmingen (Hannover)"): "Hemmingen",
    # jesus christ KVV please fix this nonsense
    ("S2", "Blankenloch Nord, Stutensee"): "Blankenloch",
    ("S2", "Daxlanden Dornröschenweg, Karlsruhe"): "Rheinstrandsiedlung",
    ("S2", "Hagsfeld Reitschulschlag (Schleife), Karlsruhe"): "Reitschulschlag",
    ("S2", "Mörsch Bach-West, Rheinstetten"): "Rheinstetten",
    ("S2", "Spöck Richard-Hecht-Schule, Stutensee"): "Spöck",
    ("STR5", "Karlsruhe Bh West (Gleis 55)"): "Rheinhafen",
    # 48 stunden ringbahn challenge
    ("S41", "Ring S41"): "Ring ↻",
    ("S42", "Ring S42"): "Ring ↺",
    ("S45", "Flughafen BER - Terminal 1-2 (S-Bahn)"): "Flughafen BER T 1-2",
    ("SS41", "Ringbahn S 41"): "Ring ↻",
    ("SS42", "Ringbahn S 42"): "Ring ↺",
    # Stuttgart my behated
    ("STBU5", "Leinfelden Bahnhof, Leinfelden-Echterdingen"): "Leinfelden Bf",
    ("STBU6", "Stuttgart Flughafen/Messe, Leinfelden-Echterdingen"): "Flughafen/Messe",
    ("STBU12", "Neckargröningen Remseck, Remseck am Neckar"): "Neckargröningen Remseck",
    # Nuremberg
    ("U3", "Großreuth _bei Schweinau"): "Großreuth bei Schweinau",
    # rnv
    ("STR1", "Schönau Endstelle, Mannheim"): "Schönau",
    ("STR1", "Rheinau Bahnhof, Mannheim"): "Rheinau Bf",
    ("STR2", "Feudenheim Endstelle, Mannheim"): "Feudenheim",
    ("STR3", "Sandhofen Endstelle, Mannheim"): "Sandhofen",
    ("STR3", "Neckarau Rheingoldhalle, Mannheim"): "Rheingoldhalle",
    ("RNV4", "Waldhof Waldfriedhof, Mannheim"): "Waldfriedhof",
    (
        "RNV4",
        "Oggersheim Comeniusstr., Ludwigshafen am Rhein",
    ): "Oggersheim Comeniusstraße",
    ("RNV4", "Bahnhof, Bad Dürkheim"): "Bad Dürkheim Bf",
    ("RNV4A", "Käfertal Käfertaler Wald, Mannheim"): "Käfertaler Wald",
    (
        "RNV4A",
        "Oggersheim Comeniusstr., Ludwigshafen am Rhein",
    ): "Oggersheim Comeniusstraße",
    ("RNV4A", "Bahnhof, Bad Dürkheim"): "Bad Dürkheim Bf",
    ("RNV5A", "Bahnhof (RNV), Heddesheim"): "Heddesheim Bf",
    ("STR6", "Rheingönheim Neubruch, Ludwigshafen am Rhein"): "Rheingönheim Neubruch",
    ("STR6", "Neuostheim Endstelle, Mannheim"): "Neuostheim",
    ("STR6", "Neuhermsheim SAP Arena S-Bahnhof, Mannheim"): "SAP-Arena S-Bf",
    ("STR6", "Berliner Platz Bahnhof LU Mitte, Ludwigshafen am R"): "Berliner Platz",
    ("STR6A", "Rheingönheim Neubruch, Ludwigshafen am Rhein"): "Rheingönheim Neubruch",
    ("STR6A", "Neuhermsheim SAP Arena S-Bahnhof, Mannheim"): "SAP-Arena S-Bf",
    ("RNV7", "Vogelstang Endstelle, Mannheim"): "Vogelstang",
    ("RNV7", "Oppau Fritz-Haber-Str. BASF Tor12+13, Ludwigshafen"): "Oppau",
    ("RNV9", "Bahnhof, Bad Dürkheim"): "Bad Dürkheim Bf",
    ("RNV9", "Luisenpark/Technoseum, Mannheim"): "Luisenpark/Technoseum",
    ("RNV9", "Neuostheim Endstelle, Mannheim"): "Neuostheim",
}
