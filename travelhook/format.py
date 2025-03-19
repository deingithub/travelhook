"this module, or rather its function format_travelynx, renders nice embed describing the current journey"

from itertools import groupby
import json
from datetime import datetime, timedelta
import re
import urllib

import discord
import tomli
from haversine import haversine

from . import database as DB
from .helpers import (
    config,
    format_delta,
    format_time,
    generate_train_link,
    LineEmoji,
    trip_length,
    random_id,
    replace_city_suffix_with_prefix,
    decline_operator_with_article,
    zugid,
    format_timezone,
)

re_remove_vienna_suffixes = re.compile(r"(?P<name>Wien .+) \(.+\)")
re_hbf = re.compile(r"(?P<city>.+) Hbf")
re_hauptbahnhof = re.compile(
    r"Hauptbahnhof(?: \(S?\+?U?\)| \(Tram\/Bus\))?, (?P<city>.+)"
)
re_station_city = re.compile(
    r"((S-)?Bahnhof |(S-)?Bh?f\.? )?(?P<station>.+), (?P<city>.+)"
)
re_u_number = re.compile(r"(?P<station>.+) [\(\[]U\d+[\)\]]")
re_decompose_him = re.compile(r"(?P<from>.+) - (?P<to>.+): Information\. (?P<msg>.+)")

blanket_replace_train_type = {
    "EV": "SEV",
    "IRE": "RE",
    "RNV": "STR",
    "O-Bus": "Bus",
    "Tram": "STR",
    "Schiff": "boat",
    "SKW": "S",
    "SVG": "FEX",
    "west": "WB",
}


train_types_config = {}
with open("train_types.toml", "rb") as f:
    train_types_config = tomli.load(f)

emoji_cache = {}


def get_network(status):
    if "network" in status:
        return status["network"]

    hafas_data = DB.DB.execute(
        "SELECT hafas_data FROM trips WHERE journey_id = ? AND hafas_data != '{}'",
        (zugid(status),),
    ).fetchone()
    if hafas_data:
        hafas_data = json.loads(hafas_data["hafas_data"])
    else:
        hafas_data = {}

    operator = status.get("operator", hafas_data.get("operator")) or ""

    lat = status["fromStation"]["latitude"]
    lon = status["fromStation"]["longitude"]

    # network NS: Nederlandse Spoorwegen trains
    if operator == "Nederlandse Spoorwegen":
        return "NS"

    # network AVG: Stadtbahn Karlsruhe
    if operator == "Albtal-Verkehrs-Gesellschaft mbH" or (
        f"{status['train']['type']}{status['train']['line']}" == "S2"
        and haversine((lat, lon), (49.009, 8.417)) < 15
    ):
        return "AVG"

    # network RNV: trams in mannheim, ludwigshafen and heidelberg
    if operator.startswith("Rhein-Neckar-Verkehr") or (
        (status["train"]["type"] in ("", "STR", "RNV"))
        and haversine((lat, lon), (49.47884, 8.55787)) < 29
    ):
        return "RNV"

    # network WL: U-Bahn Wien
    if operator.startswith("Wiener Linien"):
        return "WL"

    # network SWien: S-Bahn Wien
    if haversine((lat, lon), (48.21, 16.39)) < 70:
        return "SWien"

    # network AT: austrian trains
    if str(status["fromStation"]["uic"]).startswith("81") or str(
        status["toStation"]["uic"]
    ).startswith("81"):
        return "AT"

    # network Ü: Stadtbahn Hannover
    if (
        status["train"]["type"] in ("STR", "STB")
        and haversine((lat, lon), (52.369, 9.740)) < 20
    ):
        return "Ü"

    # network KVB: Stadtbahn Köln/Bonn
    if (50.62 < lat < 51.04) and (6.72 < lon < 7.26):
        return "KVB"

    # network BVG: U-Bahn Berlin
    if haversine((lat, lon), (52.52, 13.41)) < 30:
        return "BVG"

    # network HHA: U-Bahn Hamburg
    if haversine((lat, lon), (53.54, 10.01)) < 30:
        return "HHA"

    # network MVG: U-Bahn München
    if haversine((lat, lon), (48.15, 11.54)) < 30:
        return "MVG"

    # network NRW: Stadtbahn Rhein/Ruhr
    if (51.06 < lat < 51.68) and (6.46 < lon < 7.77):
        return "NRW"

    # network VAG: U-Bahn Nürnberg
    if haversine((lat, lon), (49.45, 11.05)) < 10:
        return "VAG"

    # network VGF: Stadtbahn Frankfurt
    if haversine((lat, lon), (50.11, 8.68)) < 30:
        return "VGF"

    # network ST: third-party operators in the netherlands
    if operator in ("Blauwnet", "Arriva Nederland", "RRReis", "R-net"):
        return "ST"

    if operator in (
        "Schweizerische Bundesbahnen",
        "Schweizerische Bundesbahnen SBB",
        "Schweizerische Südostbahn (sob)",
        "BLS AG",
        "BLS AG (bls)",
    ):
        return "CH-FV"

    if operator in (
        "Transport publics de la Région Lausannoise",
        "Transports Publics de la Région Lausannoise sa",
    ):
        return "tl"

    if operator == "CTS":
        return "CTS"

    return ""


def get_display(bot, status):
    type = status["train"]["type"].strip()
    line = status["train"]["line"]
    all_types = [t.get("type") for t in train_types_config["train_types"]]

    type = blanket_replace_train_type.get(type, type)
    # account for "ME RE2" instead of "RE 2"
    if line and (type not in all_types or not type):
        if len(line) > 2 and line[0:2] in all_types:
            type = line[0:2]
            line = line[2:]
        if line[0] in all_types:
            type = line[0]
            line = line[1:]

    if not type and line == "BB":
        type = "WLB"
        line = ""
    if type == "RT":
        type = "STR"
        line = "RT" + line
    if type == "Bus" and get_network(status) == "WL":
        line = line.replace("A", "ᴀ").replace("B", "ʙ")
    if type == "ICB":
        type = "coach"
        line = "Intercitybus"
    if not type and get_network(status) == "RNV":
        type = "STR"

    if status["backend"]["name"] == "BLS":
        bls_replace_train_types = {"B": "Bus", "FUN": "SB", "M": "U", "T": "STR"}
        type = bls_replace_train_types.get(type, type)

    if status["backend"]["name"] in ("VBB", "NAHSH", "BVG", "AVV") and type in ("S", "U", "RB"):
        line = line.removeprefix("S").removeprefix("U").removeprefix("RB")

    for tt in train_types_config["train_types"]:
        # { type = "IC", line = "1",  line_startswith = "1", network = "SBB"}
        if (
            (not "type" in tt or tt["type"].casefold() == type.casefold())
            and (not "line" in tt or tt["line"] == line)
            and (
                not "line_startswith" in tt
                or (line and line.startswith(tt["line_startswith"]))
            )
            and (
                not "network" in tt
                or tt["network"].casefold() == get_network(status).casefold()
            )
        ):
            if "remove_line_startswith" in tt:
                line = line.removeprefix(tt["line_startswith"])
            if "fallback" in tt:
                line = f"{type}{(' '+ line) if line else ''}"

            # { emoji = "ica,ic1", color = "#ff0404", hide_line_number = true, always_show_train_number = true }
            return {
                "emoji": emoji(bot, tt),
                "color": tt.get("color", "#2e2e7d"),
                "type": type,
                "line": line if not tt.get("hide_line_number") else "",
                "number": status["train"]["no"],
                "always_show_train_number": tt.get("always_show_train_number", False),
            }


def emoji(bot, tt):
    global emoji_cache
    if not emoji_cache:
        for gid in train_types_config["emoji_server_ids"]:
            for emoji in bot.get_guild(gid).emojis:
                emoji_cache[emoji.name] = str(emoji)

    emoji = tt["emoji"].split("|")
    return "".join([emoji_cache.get(e, f"FIXME `{tt}`") for e in emoji])


def merge_names(from_name, to_name):
    "if we have equivalent stations like Hauptbahnhof, X and X Hbf, draw a single line change"

    def try_merge(a, b):
        if a.removesuffix("Hbf") == b.removesuffix("Hauptbahnhof"):
            return a

        if (
            (m := re_hbf.match(a))
            and (m2 := re_hauptbahnhof.match(b))
            and m["city"] == m2["city"]
        ):
            return f"{m['city']} Hbf"

        if (
            (m := re_station_city.match(a))
            and m["station"] == "Bahnhof"
            and m["city"] == b
        ):
            return a

        if (
            (m := re_station_city.match(a))
            and (m2 := re_station_city.match(b))
            and m["city"] == m2["city"]
            and m["station"].removesuffix(" (U)") == m2["station"].removesuffix(" (U)")
        ):
            return f"{m['station'].removesuffix(' (U)')}, {m['city']}"

        if (m := re_station_city.match(a)) and b in (
            f"{m['city']} {m['station']}",
            f"{m['city']}-{m['station']}",
        ):
            return b

        if (m := re_u_number.match(a)) and b == m["station"]:
            return m["station"]

        if (
            (m := re_u_number.match(a))
            and (m2 := re_u_number.match(b))
            and m["station"] == m2["station"]
        ):
            return m["station"]

        if a == b + " (S)" or a == b + " (tief)":
            return b

    return try_merge(from_name, to_name) or try_merge(to_name, from_name)


def is_one_line_change(from_station, to_station):
    "check if we should collapse a transfer into one line instead of two (if it's the same station)"
    return (
        (from_station["uic"] == to_station["uic"])
        or (from_station["name"] == to_station["name"])
        or merge_names(from_station["name"], to_station["name"])
    )


def shortened_name(previous_name, this_name):
    "if the last station follows the 'Stop , City' convention and we're still in the same city, drop that suffix"
    mprev = re_station_city.match(previous_name)
    mthis = re_station_city.match(this_name)
    if not mprev or not mthis:
        return this_name

    # special case almost exclusively for "Bahnhof (Bus), Grimma"
    # the (Bahnhof ) prefix in the station regex eats the thing that makes the name
    # make sense here. it would get shown as just (Bus), which is silly
    if mthis["station"] == "(Bus)":
        return this_name

    if mprev["city"] == mthis["city"] and DB.City.find(mprev["city"]):
        return mthis["station"]
    elif mprev["station"] == mthis["station"] and DB.City.find(mprev["station"]):
        return mthis["city"]

    return this_name


def format_travelynx(bot, userid, trips, continue_link=None):
    """the actual formatting function called by message sends and edits
    to render an embed describing the current journey"""
    user = bot.get_user(userid)
    timezone = DB.User.find(user.id).get_timezone()

    desc = ""
    color = None

    def _next(statuses, current_index):
        "in the format loop, get the train after the current one or None if we're at the last"
        if (current_index + 1) < len(statuses):
            return statuses[current_index + 1]
        return None

    def _prev(statuses, current_index):
        "in the format loop, get the train before the current one or None if we're at the first"
        if (current_index - 1) >= 0:
            return statuses[current_index - 1]
        return None

    for i, trip in enumerate(trips):
        train = trip.status
        departure = format_time(
            train["fromStation"]["scheduledTime"],
            train["fromStation"]["realTime"],
            timezone=timezone,
        )
        display = get_display(bot, train)
        # compact layout for completed trips
        if continue_link and _next(trips, i):
            if not _prev(trips, i):
                name = train["fromStation"]["name"]
                prefix_to_add = replace_city_suffix_with_prefix.get(
                    name.split(", ")[-1]
                )
                if prefix_to_add:
                    name = f"{prefix_to_add} {', '.join(name.split(', ')[0:-1])}"
                desc += f"{LineEmoji.COMPACT_JOURNEY_START}{departure} {name}\n"
                desc += f"{LineEmoji.COMPACT_JOURNEY}{LineEmoji.SPACER}"

            # draw only train type and line number in one line
            desc += display["emoji"]
            if display["line"]:
                desc += f" **{display['line']}**"
            # draw an arrow to the next trip in the compact section until the last one in the section
            if _next(trips, i + 1):
                desc += " → "
            else:
                desc += "\n"
            # ignore the rest of the format loop until we're at the last trip of the journey
            continue

        # regular layout for full journey display
        # if we're the first trip of the journey, draw a journey start icon
        if not _prev(trips, i):
            name = train["fromStation"]["name"]
            prefix_to_add = replace_city_suffix_with_prefix.get(name.split(", ")[-1])
            if prefix_to_add:
                name = f"{prefix_to_add} {', '.join(name.split(', ')[0:-1])}"
            desc += f"{LineEmoji.START}{departure} **{name}**\n"
        elif prev := _prev(trips, i):
            prev_train = prev.status
            # if we've just drawn the last compact mode entry, draw a station
            if continue_link and not _next(trips, i):
                desc += f"{LineEmoji.CHANGE_SAME_STOP}{departure} **{train['fromStation']['name']}**\n"
            # if our trip starts on a different station than the last ended, draw a new station icon
            elif not is_one_line_change(prev_train["toStation"], train["fromStation"]):
                station_name = (
                    merge_names(
                        prev_train["toStation"]["name"], train["fromStation"]["name"]
                    )
                    or train["fromStation"]["name"]
                )
                station_name = shortened_name(
                    prev_train["toStation"]["name"], station_name
                )
                desc += f"{LineEmoji.CHANGE_ENTER_STOP}{departure} {station_name}\n"
            # if our trip starts on the same station as the last ended, we've already drawn the change icon
            else:
                pass

        route_link = generate_train_link(train)
        headsign = shortened_name(train["fromStation"]["name"], trip.fetch_headsign())

        # all lines in vienna have overly long HAFAS destinations not consistent with the vehicle display
        # like "Wien Winckelmannstraße (Schwendergasse 61)" when it should just be Winckelmannstraße
        if match := re_remove_vienna_suffixes.match(headsign):
            headsign = match["name"]

        headsign = "» " + headsign

        desc += LineEmoji.RAIL + LineEmoji.SPACER + display["emoji"]
        if route_link:
            headsign = f"[{headsign}]({route_link})"

        if display["line"]:
            desc += f" **{display['line']}**"
        if display["number"] and (
            display["always_show_train_number"]
            or DB.User.find(userid).show_train_numbers
        ):
            desc += f" {display['number']}"
        desc += f" **{headsign}**"

        desc += " ●\n" if train["comment"] else "\n"
        arrival = format_time(
            train["toStation"]["scheduledTime"],
            train["toStation"]["realTime"],
            timezone=timezone,
        )
        station_name = shortened_name(
            train["fromStation"]["name"], train["toStation"]["name"]
        )
        # if we're on the last trip of the journey, draw an end icon
        if not _next(trips, i):
            desc += f"{LineEmoji.END}{arrival} **{station_name}**\n"

            if composition := trip.status.get("composition"):
                desc += f"{LineEmoji.COMPOSITION} {composition}\n"

            trip_time = timedelta(
                seconds=train["toStation"]["realTime"]
                - train["fromStation"]["realTime"]
            )
            if not trip_time:
                trip_time += timedelta(seconds=30)
            desc += f"{LineEmoji.TRIP_SPEED} {format_delta(trip_time)}"

            length = trip_length(trip)
            if length > 0:
                desc += (
                    f" · {length:.1f}{'km+' if trip.hafas_data.get('beeline', True) else 'km'} · "
                    f"{(length/(trip_time.total_seconds()/3600)):.0f}km/h"
                )
            desc += "\n"
            if hafas_data := trip.hafas_data:
                messages = hafas_data["messages"].copy()

                for stop, smessages in hafas_data["stop_messages"].items():
                    messages += smessages

                for message in messages:
                    if message["type"] == "D":
                        desc += f"{LineEmoji.WARN} {message['text']}\n"
                    elif message["type"] in ("Q", "L"):
                        if match := re_decompose_him.match(message["text"]):
                            if (
                                hafas_data["route"][0]["name"] == match["from"]
                                and hafas_data["route"][-1]["name"] == match["to"]
                            ):
                                desc += f"{LineEmoji.INFO} {match['msg']}\n"
                            else:
                                desc += f"{LineEmoji.INFO} {match['from']} – {match['to']}: {match['msg']}\n"
                        else:
                            desc += f"{LineEmoji.INFO} {message['text']}\n"
            if comment := trip.status["comment"]:
                if len(comment) >= 500:
                    comment = comment[0:500] + "…"
                desc += f"{LineEmoji.COMMENT} _{comment}_\n"

        # draw a transfer instead
        elif next := _next(trips, i):
            next_train = next.status
            # if we don't leave the station to change, draw a single change line
            if is_one_line_change(train["toStation"], next_train["fromStation"]):
                station_name = (
                    merge_names(
                        train["toStation"]["name"], next_train["fromStation"]["name"]
                    )
                    or train["toStation"]["name"]
                )
                station_name = shortened_name(
                    next_train["fromStation"]["name"], station_name
                )
                next_train_departure = format_time(
                    next_train["fromStation"]["scheduledTime"],
                    next_train["fromStation"]["realTime"],
                    timezone=timezone,
                )
                desc += f"{LineEmoji.CHANGE_SAME_STOP}{arrival} → {next_train_departure} {station_name}\n"
            else:
                # if we leave the station, draw the upper part of a two-line change
                desc += f"{LineEmoji.CHANGE_LEAVE_STOP}{arrival} " + f"{station_name}\n"
                train_end_location = (
                    train["toStation"]["latitude"],
                    train["toStation"]["longitude"],
                )
                next_train_start_location = (
                    next_train["fromStation"]["latitude"],
                    next_train["fromStation"]["longitude"],
                )
                change_meters = haversine(
                    train_end_location, next_train_start_location, unit="m"
                )
                if change_meters > 200.0 and not any(
                    lat == lon == 0.0
                    for (lat, lon) in [train_end_location, next_train_start_location]
                ):
                    desc += f"{LineEmoji.CHANGE_WALK}{LineEmoji.SPACER}*— {int(change_meters)} m —*\n"

        # overwrite last set embed color with the current color
        color = discord.Color.from_str(display["color"])

    # end of format loop, finish up embed

    if continue_link:
        desc += f"\n{LineEmoji.DESTINATION} {continue_link}\n"
    else:
        to_time = format_time(
            trips[-1].status["toStation"]["scheduledTime"],
            trips[-1].status["toStation"]["realTime"],
            True,
        )
        desc += f"\n{LineEmoji.DESTINATION} **{trips[-1].status['toStation']['name']} {to_time}**\n"

    total_time = timedelta(
        seconds=trips[-1].status["toStation"]["realTime"]
        - trips[0].status["fromStation"]["realTime"]
    )
    if not total_time:
        total_time += timedelta(seconds=30)
    journey_time = timedelta(
        seconds=sum(
            trip.status["toStation"]["realTime"]
            - trip.status["fromStation"]["realTime"]
            for trip in trips
        )
    )
    if not journey_time:
        journey_time += timedelta(seconds=30)
    lengths = [
        trip_length(DB.Trip.find(user.id, zugid(trip.get_unpatched_status())))
        for trip in trips
    ]
    includes_beelines = any(l == 0 for l in lengths) or any(
        DB.Trip.find(user.id, zugid(trip.get_unpatched_status())).hafas_data.get(
            "beeline", True
        )
        for trip in trips
    )
    desc += (
        f"{LineEmoji.TRIP_SUM} {len(trips)} {'trip' if len(trips) == 1 else 'trips'} · "
        f"{format_delta(total_time)} ({format_delta(journey_time)} in transit) · "
        f"{sum(lengths):.1f}km{'+' if includes_beelines else ''} · "
        f"{sum(lengths)/(total_time.total_seconds()/3600):.0f}km/h\n"
    )
    desc += (
        f"-# {format_timezone(timezone)} · "
        + f"{trip.status['backend']['name'] or 'DB'} {trip.status['backend']['type']}"
    )
    if trip.hafas_data:
        jid = urllib.parse.quote(trip.hafas_data["id"])
        from_station = urllib.parse.quote(trip.status["fromStation"]["name"])
        to_station = urllib.parse.quote(trip.status["toStation"]["name"])
        hafas = trip.status["backend"]["name"]
        if hafas is None or trip.status["backend"]["type"] == "travelcrab.friz64.de":
            hafas = "ÖBB"
        link = DB.Link.make(
            f"https://dbf.finalrewind.org/map/{jid}/0?hafas={hafas}"
            + f"&from={from_station}&to={to_station}"
        )
        desc += f" · [Map]({config['shortener_url']}/{link.short_id})"

    embed_title = f"{user.name} {'war' if not trips[-1].status['checkedIn'] else 'ist'}"
    embed_title += decline_operator_with_article(
        trips[-1].status.get("operator") or trips[-1].hafas_data.get("operator")
    )
    embed_title += " unterwegs"

    embed = discord.Embed(
        description=desc,
        color=color,
    ).set_author(
        name=embed_title,
        icon_url=user.avatar.url,
    )

    embed = sillies(bot, trips, embed)

    return embed


def sillies(bot, trips, embed):
    "do funny things with the embed once it's done"

    # sort by "S"+"31", ie train type and line
    # actually sort by emoji+line since the line field is empty on some supported
    # transit networks, so it would count combos for the same train type and ignore the lines
    sortkey = lambda d: f"{d['emoji']}{d['line']}"
    train_lines = sorted([get_display(bot, trip.status) for trip in trips], key=sortkey)
    grouped = []
    for _, group in groupby(train_lines, key=sortkey):
        grouped.append(list(group))
    # get the most used type+line combinations
    grouped = sorted(grouped, key=len, reverse=True)
    if len(grouped[0]) >= 3:
        display = grouped[0][0]
        embed.description += f"\n### {len(grouped[0])}× {display['emoji']} {display['line'] or ''} COMBO!"

    if (not trips[-1].hafas_data) and trips[-1].status["backend"]["id"] >= 0:
        embed = embed.set_thumbnail(url="https://i.imgur.com/6pB5Kc6.png")
        embed.description += "\n-# **» ?**: hafas broke, try to update"

    status = trips[-1].status
    stations = status["fromStation"]["name"] + status["toStation"]["name"]
    if "Durlacher Tor" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/6WhzdSp.png")
    if "Mühlburger Tor" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/jGATXUv.jpg")
    if (
        "Wien Floridsdorf" in status["fromStation"]["name"]
        and status["train"]["type"] + status["train"]["line"] == "U6"
    ):
        return embed.set_image(url="https://i.imgur.com/Gul73tp.png")
    if status["train"]["type"].strip() == "ICB":
        return embed.set_image(url="https://i.imgur.com/gH3PSqi.jpeg")
    if "Wien Floridsdorf" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/CSBTb0z.gif")
    if "Bopser, Stuttgart" in stations:
        return embed.set_thumbnail(url="https://i.imgur.com/ynda6jb.png")
    if "Wien Mitte" in status["toStation"]["name"]:
        return embed.set_image(url="https://i.imgur.com/f7dwfpt.gif")
    if "Gumpendorfer Straße" in stations:
        return embed.set_image(url="https://i.imgur.com/FVuvqBc.png")
    if "Ziegelstein" in stations:
        return embed.set_thumbnail(url="https://i.imgur.com/W3mPNEn.gif")
    if "Erlangen" in status["toStation"]["name"]:
        return embed.set_thumbnail(url="https://i.imgur.com/pHp8Sus.png")
    if (
        ("Weinweg, Karlsruhe" in status["toStation"]["name"])
        or ("Gewerbepark Kagran" in status["toStation"]["name"])
        or ("IKEA".casefold() in status["toStation"]["name"].casefold())
    ):
        return embed.set_thumbnail(url="https://i.imgur.com/9IAgPLd.png")
    if status.get("composition") and ("**612**" in status["composition"]):
        return embed.set_image(url="https://i.imgur.com/2LTmfiW.png")
    if status.get("composition") and (
        "**440**" in status["composition"] or "**441**" in status["composition"]
    ):
        return embed.set_thumbnail(url="https://i.imgur.com/FO6Q5sR.png")
    if status["train"]["type"] == "Schw-B":
        return embed.set_image(url="https://i.imgur.com/8deLTcU.png")
    if status["train"]["line"] == "4" and "uniwuni" in embed.author.name:
        return embed.set_image(url="https://i.imgur.com/zKzgXLp.png")
    if "Homme de Fer" in status["toStation"]["name"]:
        return embed.set_thumbnail(
            url="https://upload.wikimedia.org/wikipedia/commons/4/4c/Potato_heart_mutation.jpg"
        )

    return embed
