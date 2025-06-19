# pylint: disable=missing-function-docstring
"contains and encapsulates database accesses"
import asyncio
import aiohttp
import collections
import json
import sqlite3
import shlex
import subprocess
import traceback
from dataclasses import dataclass, astuple
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from haversine import haversine

from .helpers import (
    config,
    zugid,
    tz,
    random_id,
    replace_headsign,
    format_composition_element,
    db_replace_group_classes,
    describe_class,
)
from .format import get_network
from . import oebb_wr

from bs4 import BeautifulSoup
import re

DB = None


def connect(path):
    global DB
    DB = sqlite3.connect(path, isolation_level=None)
    DB.row_factory = sqlite3.Row


def json_patch_dicts(patch, old_dict):
    return json.loads(
        DB.execute(
            "SELECT json_patch(?,?) AS newpatch",
            (
                json.dumps(old_dict),
                json.dumps(patch),
            ),
        ).fetchone()["newpatch"]
    )


re_british_train_no = re.compile(r"[A-Z]\d{5}$")
re_british_class_numbers = re.compile(r"(\d{3})(\d{3})")


@dataclass
class Server:
    "servers the bot is enabled on"
    server_id: int
    live_channel: int

    @classmethod
    def find_all(cls):
        rows = DB.execute("SELECT * FROM servers").fetchall()
        return [cls(**row) for row in rows]

    @classmethod
    def find(cls, server_id):
        row = DB.execute(
            "SELECT * FROM servers WHERE server_id = ?", (server_id,)
        ).fetchone()
        return cls(**row)

    def as_discord_obj(self):
        return discord.Object(id=self.server_id)


class Privacy(IntEnum):
    "users' per-server privacy setting for /zug. LIVE enables the webhook for that server."
    ME = 0
    EVERYONE = 5
    LIVE = 10


class BreakMode(IntEnum):
    "users' setting how to handle the next checkin in this journey"
    NATURAL = 0
    FORCE_BREAK = -10
    FORCE_GLUE = 10
    FORCE_GLUE_LATCH = 20


@dataclass
class User:
    "users that have registered for the bot"
    discord_id: int
    token_status: str
    token_webhook: Optional[str]
    token_travel: Optional[str]
    break_journey: BreakMode
    suggestions: str
    show_train_numbers: bool
    timezone: str

    Locks = collections.defaultdict(asyncio.Lock)

    @classmethod
    def find(cls, discord_id=None, token_webhook=None):
        row = None
        if discord_id:
            row = DB.execute(
                "SELECT * FROM users WHERE discord_id = ?", (discord_id,)
            ).fetchone()
        elif token_webhook:
            row = DB.execute(
                "SELECT * FROM users WHERE token_webhook = ?", (token_webhook,)
            ).fetchone()
        else:
            raise ValueError()

        if row:
            return cls(**row)
        return None

    def write(self):
        "insert the manually created user object into the database as a fresh registration"
        DB.execute(
            "INSERT INTO users (discord_id, token_status, token_webhook, token_travel, break_journey, suggestions, show_train_numbers, timezone) VALUES(?,?,?,?,?,?,?,?)",
            astuple(self),
        )

    def find_privacy_for(self, server_id):
        if row := DB.execute(
            "SELECT privacy_level FROM privacy WHERE user_id = ? AND server_id = ?",
            (self.discord_id, server_id),
        ).fetchone():
            return Privacy(row["privacy_level"])
        return Privacy.ME

    def set_privacy_for(self, server_id, level):
        DB.execute(
            "INSERT INTO privacy(user_id, server_id, privacy_level) VALUES(?,?,?) "
            "ON CONFLICT DO UPDATE SET privacy_level=excluded.privacy_level",
            (self.discord_id, server_id, int(level)),
        )

    def set_break_mode(self, break_mode: BreakMode):
        DB.execute(
            "UPDATE users SET break_journey = ? WHERE discord_id = ?",
            (break_mode, self.discord_id),
        )

    def do_break_journey(self):
        "Break a journey, deleting stored trips and messages up to this point."
        DB.execute("DELETE FROM trips WHERE user_id = ?", (self.discord_id,))
        DB.execute("DELETE FROM messages WHERE user_id = ?", (self.discord_id,))

    def set_show_train_numbers(self, show_train_numbers: bool):
        DB.execute(
            "UPDATE users SET show_train_numbers = ? WHERE discord_id = ?",
            (show_train_numbers, self.discord_id),
        )

    def set_import_token(self, token: Optional[str]):
        DB.execute(
            "UPDATE users SET token_travel = ? WHERE discord_id = ?",
            (token, self.discord_id),
        )

    def find_live_channel_ids(self):
        rows = DB.execute(
            "SELECT servers.live_channel FROM servers JOIN privacy on servers.server_id = privacy.server_id "
            "WHERE privacy.user_id = ? AND privacy.privacy_level = ?;",
            (self.discord_id, Privacy.LIVE),
        ).fetchall()
        return [row["live_channel"] for row in rows]

    def get_lock(self):
        return self.Locks[self.discord_id]

    def write_suggestions(self, suggestions):
        self.suggestions = suggestions
        DB.execute(
            "UPDATE users SET suggestions = ? WHERE discord_id = ?",
            (self.suggestions, self.discord_id),
        )

    def get_timezone(self):
        return ZoneInfo(self.timezone)

    def write_timezone(self, timezone):
        self.timezone = timezone
        DB.execute(
            "UPDATE users SET timezone = ? WHERE discord_id = ?",
            (self.timezone, self.discord_id),
        )


@dataclass
class City:
    "city names for use with format.shortened_name()"
    name: str

    @classmethod
    def find(cls, name):
        row = DB.execute(
            "SELECT name FROM cities WHERE name = ?",
            (name,),
        ).fetchone()
        if row:
            return cls(**row)
        return None


@dataclass
class CTSStop:
    "cts stops"
    name: str
    logicalstopcode: int
    latitude: int
    longitude: int

    @classmethod
    def find_all(cls):
        rows = DB.execute("SELECT * FROM cts_stops").fetchall()
        return [cls(**row) for row in rows]

    @classmethod
    def find_by_logicalstopcode(cls, logicalstopcode):
        row = DB.execute(
            "SELECT * FROM cts_stops WHERE logicalstopcode = ?", (logicalstopcode,)
        ).fetchone()
        if row:
            return cls(**row)


@dataclass
class Tram:
    "trams in selected networks, vehicle number associated with type"
    network: str
    individual_number: Optional[int]
    number_from: Optional[int]
    number_to: Optional[int]
    description: str

    @classmethod
    def find(cls, network, number):
        row = DB.execute(
            "SELECT * FROM trams WHERE network = ? COLLATE NOCASE "
            "AND (individual_number = ? OR (number_from <= ? AND number_to >= ?)) "
            "ORDER BY individual_number DESC LIMIT 1",
            (network, number, number, number),
        ).fetchone()
        if row:
            return row["description"]


@dataclass
class Trip:
    "user-trips the bot knows about"
    journey_id: str
    user_id: int
    travelynx_status: str
    from_time: int
    from_station: str
    from_lat: float
    from_lon: float
    to_time: int
    to_station: str
    to_lat: float
    to_lon: float
    headsign: str
    status_patch: str
    hafas_data: str

    def __post_init__(self):
        self.status = json.loads(self.travelynx_status)
        self.status_patch = json.loads(self.status_patch)
        self.hafas_data = json.loads(self.hafas_data)
        if (not self.status["train"]["line"]) and (line := self.hafas_data.get("line")):
            self.status["train"]["line"] = line

    @classmethod
    def find(cls, user_id, journey_id):
        row = DB.execute(
            "SELECT journey_id, user_id, json_patch(travelynx_status, status_patch) as travelynx_status, "
            "from_time, from_station, from_lat, from_lon, to_time, to_station, to_lat, to_lon, headsign, status_patch, hafas_data "
            "FROM trips WHERE user_id = ? AND journey_id = ?",
            (user_id, journey_id),
        ).fetchone()
        if row:
            return cls(**row)
        return None

    @classmethod
    def find_current_trips_for(cls, user_id):
        rows = DB.execute(
            "SELECT journey_id, user_id, json_patch(travelynx_status, status_patch) as travelynx_status, "
            "from_time, from_station, from_lat, from_lon, to_time, to_station, to_lat, to_lon, headsign, status_patch, hafas_data "
            "FROM trips WHERE user_id = ? ORDER BY json_patch(travelynx_status, status_patch) ->> '$.fromStation.realTime' ASC",
            (user_id,),
        ).fetchall()
        return [cls(**row) for row in rows]

    @classmethod
    def find_last_trip_for(cls, user_id):
        if current_trips := cls.find_current_trips_for(user_id):
            return current_trips[-1]
        return None

    @classmethod
    def upsert(cls, userid, status):
        DB.execute(
            "INSERT INTO trips(journey_id, user_id, travelynx_status, from_time, from_station, from_lat, from_lon, to_time, to_station, to_lat, to_lon) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET travelynx_status=excluded.travelynx_status, "
            "from_time = excluded.from_time, from_station=excluded.from_station, from_lat=excluded.from_lat, from_lon=excluded.from_lon, "
            "to_time = excluded.to_time, to_station=excluded.to_station, to_lat=excluded.to_lat, to_lon=excluded.to_lon",
            (
                zugid(status),
                userid,
                json.dumps(status),
                status["fromStation"]["realTime"],
                status["fromStation"]["name"],
                status["fromStation"]["latitude"],
                status["fromStation"]["longitude"],
                status["toStation"]["realTime"],
                status["toStation"]["name"],
                status["toStation"]["latitude"],
                status["toStation"]["longitude"],
            ),
        )

    def delete(self):
        DB.execute(
            "DELETE FROM trips WHERE user_id = ? AND journey_id = ?",
            (self.user_id, zugid(self.status)),
        )

    def write_patch(self, status_patch):
        "write the status patch field to the database"
        DB.execute(
            "UPDATE trips SET status_patch=? WHERE user_id = ? AND journey_id = ?",
            (json.dumps(status_patch), self.user_id, self.journey_id),
        )
        self.status_patch = status_patch

    def patch_patch(self, patch):
        "directly patch our status patch with a new patch"
        self.write_patch(json_patch_dicts(patch, self.status_patch))

    def get_unpatched_status(self):
        """get the unpatched status, for mocking webhooks. this way we don't
        accidentally destructively commit the user's edits as the actual status."""
        return json.loads(
            DB.execute(
                "SELECT travelynx_status FROM trips WHERE user_id = ? AND journey_id = ?",
                (self.user_id, self.journey_id),
            ).fetchone()["travelynx_status"]
        )

    def maybe_fix_1970(self):
        """sometimes the toStation times wind up being unix time 0 instead of the actual time,
        we can fix that. call only after fetch_hafas_data()"""

        if self.status["toStation"]["realTime"] > 0:
            return

        if route := self.hafas_data.get("route"):
            for stop in route:
                if (
                    stop["eva"] == self.status["toStation"]["uic"]
                    and (stop["sched_arr"] or stop["sched_dep"] or 0)
                    >= self.status["fromStation"]["scheduledTime"]
                ):
                    self.status["toStation"]["scheduledTime"] = stop["sched_arr"]
                    self.status["toStation"]["realTime"] = (
                        stop["rt_arr"] or stop["sched_arr"]
                    )
                    self.upsert(self.user_id, self.status)
                    return

    def fetch_hafas_data(self, force: bool = False):
        "perform arcane magick (perl 'FFI') to get hafas data for our trip"

        def save_hafas_data(data):
            self.hafas_data = data
            DB.execute(
                "UPDATE trips SET hafas_data=? WHERE user_id = ? AND journey_id = ?",
                (
                    json.dumps(data),
                    self.user_id,
                    self.journey_id,
                ),
            )

        def get_stationboard(backend_name, station_id):
            if backend_name == "ÖBB":
                # wonky perl unicode handling that i do not understand
                backend_name = bytes([214, 66, 66])
            sb = subprocess.run(
                [
                    "json-hafas-stationboard.pl",
                    backend_name,
                    str(station_id),
                    str(self.status["fromStation"]["scheduledTime"]),
                ],
                capture_output=True,
            )
            stationboard = {}
            try:
                stationboard = json.loads(sb.stdout)
            except:  # pylint: disable=bare-except
                print(
                    f"{backend_name} stationboard perl broke:\n{sb.stdout} {sb.stderr}"
                )
                traceback.print_exc()
                return None
            if "error_code" in stationboard:
                print(f"{backend_name} stationboard perl broke:\n{stationboard}")
            return stationboard

        def öbb_stopfinder():
            hafas_stations = subprocess.run(
                [
                    "hafas-m",
                    "-s",
                    "ÖBB",
                    f"?{self.status['fromStation']['name']}",
                    "--json",
                ],
                capture_output=True,
            )
            stations = None
            try:
                stations = json.loads(hafas_stations.stdout)
            except:  # pylint: disable=bare-except
                print(
                    f"alternative ÖBB station search perl broke:\n{hafas_stations.stdout} {hafas_stations.stderr}"
                )
                traceback.print_exc()
                return
            if not stations or "error_code" in stations:
                print(f"alternative ÖBB station search broke:\n{stations}")
                return
            return stations[0]

        def get_trip(backend_name, trip_id):
            if backend_name == "ÖBB":
                # wonky perl unicode handling that i do not understand
                backend_name = bytes([214, 66, 66])

            hafas = subprocess.run(
                ["json-hafas.pl", backend_name, trip_id],
                capture_output=True,
            )
            status = {}
            try:
                status = json.loads(hafas.stdout)
                if "error_string" in status:
                    print(f"{backend_name} trip perl broke:\n{status}")
                    return None
            except:  # pylint: disable=bare-except
                print(f"{backend_name} trip perl broke:\n{hafas.stdout} {hafas.stderr}")
                traceback.print_exc()
                return None

            return status

        if ("id" in self.hafas_data or "failedhafas" in self.hafas_data) and not force:
            return

        german_local_transit_not_in_oebb_hafas = (
            "AST",
            "Bus",
            "Fähre",
            "Ruf",
            "RNV",
            "SB",
            "Schw-B",
            "STB",
            "STR",
            "U",
            "ZahnR",
        )

        station_id = self.status["fromStation"]["uic"]
        mode = self.status["backend"]["type"]
        backend = self.status["backend"]["name"]
        if mode == "IRIS-TTS":
            # iris-tts: only german trains, should all be in ÖBB hafas
            mode = "HAFAS"
            backend = "ÖBB"
        elif (
            mode in ("DBRIS", "travelcrab.friz64.de")
            and self.status["train"]["type"]
            not in german_local_transit_not_in_oebb_hafas
            and not (
                f"{self.status['train']['type']}{self.status['train']['line']}".strip()
                == "S2"
                and haversine(
                    (
                        self.status["fromStation"]["latitude"],
                        self.status["fromStation"]["longitude"],
                    ),
                    (49.009, 8.417),
                )
                < 15.0
            )
        ):
            # DBRIS or travelcrab (relayed transitous) checkins for non-local transit, i.e. mainline trains
            # should all be in ÖBB hafas
            # EXCEPT line S2 in karlsruhe. grrr
            mode = "HAFAS"
            backend = "ÖBB"
        elif mode == "travelcrab.friz64.de":
            mode = "MOTIS"
            backend = "transitous"

        # actually go ahead and fetch the data…
        if mode == "HAFAS":
            # 1. fetch stationboard
            # 2. find train there, pick out ID, headsign and line
            # 3. fetch train
            jid = self.status["train"]["hafasId"]
            if not jid and "|" in self.status["train"]["id"]:
                jid = self.status["train"]["id"]

            stationboard = {}
            if station_id == 0:
                # skip guaranteed failed request and run stopfinder later
                stationboard = {"error_string": "svcResL[0].err is LOCATION"}
            elif station_id > 0:
                stationboard = get_stationboard(backend, station_id)

            if (
                backend == "ÖBB"
                and stationboard.get("error_string") == "svcResL[0].err is LOCATION"
            ):
                # if we got here via DBRIS/travelcrab mainline trains we might have run
                # into a station that has a different ID in the ÖBB hafas
                # run a stop finder request to try and find a stop with the same name
                station = öbb_stopfinder()
                if station.get("eva"):
                    print(
                        f"trying to fix missing station {self.status['fromStation']}, found {station} instead"
                    )
                    stationboard = get_stationboard(backend, station["eva"])
                else:
                    print(f"failed to fix missing station {self.status['fromStation']}")

            if not stationboard or not "trains" in stationboard:
                save_hafas_data({"failedhafas": True})
                return

            for train in stationboard["trains"]:
                if (
                    not train["scheduled"]
                    == self.status["fromStation"]["scheduledTime"]
                ):
                    continue

                if (
                    jid == train["id"]
                    or (train["number"] == self.status["train"]["no"])
                    or (
                        f"{train['type']}{train['line']}"
                        == f"{self.status['train']['type']}{self.status['train']['line'] or self.status['train']['no']}"
                    )
                    or (
                        self.status["backend"]["type"]
                        in ("MOTIS", "travelcrab.friz64.de")
                        and f"{train['type']}{train['line']}".endswith(
                            self.status["train"]["line"]
                        )
                    )
                ):
                    trip = get_trip(backend, train["id"])
                    if trip:
                        headsign = train["direction"]
                        if (not headsign) and (route := trip.get("route")):
                            headsign = route[-1]["name"]

                        trip.update(headsign=headsign, line=train["line"])
                        save_hafas_data(trip)
                        return
            else:
                print(f"did not find a match for {self.status['train']}!")
                save_hafas_data({"failedhafas": True})
                return

        elif mode == "DBRIS":
            # 1. fetch stationboard, pick out headsign
            # 2. we got ip banned :( only stationboard access for us
            jid = self.status["train"]["hafasId"]
            if not jid and "|" in self.status["train"]["id"]:
                jid = self.status["train"]["id"]

            stationboard = get_stationboard("DBRIS", station_id)

            if not stationboard or not "trains" in stationboard:
                save_hafas_data({"failedhafas": True})
                return

            for train in stationboard["trains"]:
                if (
                    not train["scheduled"]
                    == self.status["fromStation"]["scheduledTime"]
                ):
                    continue

                if (
                    jid == train["id"]
                    or (train["number"] == self.status["train"]["no"])
                    or (
                        f"{train['type']}{train['line']}"
                        == f"{self.status['train']['type']}{self.status['train']['line'] or self.status['train']['no']}"
                    )
                ):
                    save_hafas_data(
                        {"headsign": train["direction"], "line": train["line"]}
                    )
                    return
            else:
                print(f"did not find a match for {self.status['train']}!")
                save_hafas_data({"failedhafas": True})
                return
        elif mode == "MOTIS":
            # 1. fetch train
            # 2. find current stop in route
            # 3. fetch stationboard, find train there and pick out correct headsign
            trip = get_trip(f"MOTIS-{backend}", self.status["train"]["hafasId"])
            if not trip:
                save_hafas_data({"failedhafas": True})
                return

            station = None
            if (route := trip.get("route")) and (
                stations := [
                    s for s in route if s["name"] == self.status["fromStation"]["name"]
                ]
            ):
                stationboard = get_stationboard(f"MOTIS-{backend}", stations[0]["eva"])
                if stationboard and "trains" in stationboard:
                    for train in stationboard["trains"]:
                        if (
                            not train["scheduled"]
                            == self.status["fromStation"]["scheduledTime"]
                        ):
                            continue

                        if self.status["train"]["hafasId"] == train["id"]:
                            headsign = train["direction"]
                            if (not headsign) and (route := trip.get("route")):
                                headsign = route[-1]["name"]
                            trip.update(headsign=headsign, line=train["line"])
                            break
                    else:
                        print(
                            f"did not find a match at {stations[0]} for {self.status['train']}!"
                        )

                save_hafas_data(trip)
        else:
            # manual trips and uhhhh EFA? not handled yet. later tm
            return

    def fetch_headsign(self):
        if not self.hafas_data:
            self.fetch_hafas_data()

        if headsign := self.status["train"].get(
            "fakeheadsign", self.hafas_data.get("headsign")
        ):
            replace_key = (
                f"{self.status['train']['type']}{self.status['train']['line']}".replace(
                    " ", ""
                ),
                headsign,
            )
            return replace_headsign.get(
                replace_key,
                headsign,
            )
        return "?"

    def get_db_composition(self):
        if "composition" in self.status or "failedcomposition-db" in self.status:
            return

        if not self.status["train"]["no"]:
            return
        if not self.status["fromStation"]["uic"] or not (
            8000000 < self.status["fromStation"]["uic"] < 8100000
        ):
            return

        db_wr = subprocess.run(
            [
                "json-db-composition.pl",
                str(self.status["fromStation"]["scheduledTime"]),
                str(self.status["fromStation"]["uic"]),
                self.status["train"]["type"],
                self.status["train"]["no"],
            ],
            capture_output=True,
        )
        status = {}
        try:
            status = json.loads(db_wr.stdout)
        except:  # pylint: disable=bare-except
            print(f"db_wr perl broke:\n{db_wr.stdout} {db_wr.stderr}")
            traceback.print_exc()

        if status.get("error_string") == "404 Not Found":
            self.patch_patch({"failedcomposition-db": True})
            return
        elif "error_string" in status:
            print(f"db_wr perl broke:\n{status}")
            return

        composition = []
        for group in status["groups"]:
            wagons = group["carriages"]
            # multiple units - all uic ids start with 9…
            if all(wagon["uic_id"] and wagon["uic_id"][0] == "9" for wagon in wagons):
                # class number of leading wagon
                group_class = wagons[0]["uic_id"][5:8]
                # replace "wrong" class numbers with commonly used ones, eg 812→412
                group_class = db_replace_group_classes.get(group_class, group_class)
                # find the lowest wagon number of that class in the whole trainset
                # this is the number we display after the class number, since the other numbers
                # in the trainset are usually based on that lowest number +50, +500 etc.
                group_number = sorted(
                    [
                        int(wagon["uic_id"][8:11])
                        for wagon in wagons
                        if wagon["uic_id"][5:8] == group_class
                    ]
                )[0]
                # optionally get a name for the class, eg 412→ICE 4
                trainset_name = describe_class(wagons[0]["uic_id"]) or ""
                if trainset_name in ("ICE 4", "ICE-T") or trainset_name.startswith(
                    "FLIRT"
                ):
                    trainset_name += f" ({len(wagons)} Wagen)"
                # optionally get a name for the trainset, eg ICE1101→Neustadt an der Weinstraße
                if taufname := group.get("designation"):
                    trainset_name += f" {taufname}"
                composition.append(f"{group_class} {group_number:03} {trainset_name}")

            else:
                same_type_counter = [0, ""]
                for wagon in wagons:
                    if wagon["uic_id"] and wagon["uic_id"][0] in ("9", "L"):
                        if len(wagon["uic_id"]) == 12:
                            wagon[
                                "type"
                            ] = f"{wagon['uic_id'][4:8]} {wagon['uic_id'][8:11]}-{wagon['uic_id'][11]}"
                        else:
                            wagon["type"] = wagon["uic_id"]

                    if same_type_counter[1] == wagon["type"]:
                        same_type_counter[0] += 1
                    else:
                        if same_type_counter[0] == 1:
                            composition.append(same_type_counter[1])
                        elif same_type_counter[0]:
                            composition.append(
                                f"{same_type_counter[0]}x {same_type_counter[1]}"
                            )
                        same_type_counter = [1, wagon["type"]]
                if same_type_counter[0] == 1:
                    composition.append(same_type_counter[1])
                elif same_type_counter[0]:
                    composition.append(
                        f"{same_type_counter[0]}x {same_type_counter[1]}"
                    )

            composition_text = " + ".join(
                [format_composition_element(unit) for unit in composition]
            )
            departure = (
                datetime.fromtimestamp(
                    self.status["fromStation"]["scheduledTime"], tz=tz
                )
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
            link = Link.make(
                f"https://dbf.finalrewind.org/carriage-formation?number={self.status['train']['no']}"
                f"&category={self.status['train']['type']}&administrationId=80"
                f"&evaNumber={self.status['fromStation']['uic']}&date={departure:%Y-%m-%d}"
                f"&time={departure.isoformat()}Z"
            )
            self.patch_patch(
                {
                    "composition": f"[{composition_text}]({config['shortener_url']}/{link.short_id})"
                }
            )

    async def get_rtt_composition(self):
        if "composition" in self.status or "failedcomposition-rtt" in self.status:
            return

        if not (7000000 < (self.status["fromStation"]["uic"] or 0) < 7100000):
            return
        if not re_british_train_no.match(self.status["train"]["line"] or ""):
            return

        now = datetime.now(tz=User.find(discord_id=self.user_id).get_timezone())
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.realtimetrains.co.uk/service/gb-nr:"
                    f"{self.status['train']['line']}/{now:%Y-%m-%d}/detailed"
                ) as response:
                    apply_patch = {"network": "UK"}
                    soup = BeautifulSoup(await response.text(), "html.parser")
                    try:
                        plan_nodes = soup.select_one("div.allocation").getText().strip()
                        plan_nodes = re_british_class_numbers.sub(r"\1 \2", plan_nodes)
                        plan_nodes = plan_nodes.split("+")
                        plan_nodes = " + ".join(
                            format_composition_element(node) for node in plan_nodes
                        )
                        apply_patch["composition"] = plan_nodes
                    except:
                        print("rtt: no nodes found")
                        traceback.print_exc()
                        apply_patch["failedcomposition-rtt"] = True
                    operatorheader = soup.select_one("#servicetitle .header")
                    destination_text = " ".join(operatorheader.stripped_strings)
                    if "to" in destination_text:
                        destination = destination_text.split("to")[-1].strip()
                        apply_patch["train"] = {"fakeheadsign": destination}
                    apply_patch["operator"] = soup.select_one(
                        "#servicetitle .toc > div"
                    ).getText()
                    self.patch_patch(apply_patch)
        except:
            print(f"rtt request broke")
            traceback.print_exc()
            self.patch_patch({"failedcomposition-rtt": True})
            return

    async def get_vagonweb_composition(self):
        if "composition" in self.status or "failedcomposition-vagonweb" in self.status:
            return
        if not self.status["train"]["no"] or not "operator" in self.hafas_data:
            return

        vagonweb_operatorcodes = {
            "ARRIVA vlaky": "ARV",
            "Regiojet a.s.": "RJ",
            "GW Train Regio": "GWTR",
            "Leo Express Tenders s.r.o": "LE",
            "GySEV": "GySEV",
            "Bulgarische Staatsbahnen Balgarski Darzavni Zeleznici": "BDŽ",
            "Dänische Staatsbahnen": "DSB",
            "SJ": "SJ",
            "VR": "VR",
            "Koleje Mazowieckie": "KM",
            "Koleje Slaskie": "KŚ",
            "SKPL Cargo Sp. z o. o.": "SKPL",
            "Polregio": "PREG",
            "Schweizerische Bundesbahnen": "SBB",
            "SNCB": "SNCB",
        }
        vagonweb_operatorcode = vagonweb_operatorcodes.get(self.hafas_data["operator"])
        if not vagonweb_operatorcode and self.hafas_data["operator"] == "Nahreisezug":
            if 5100000 < self.status["fromStation"]["uic"] < 5200000:
                vagonweb_operatorcode = "PKPIC"
            elif 5300000 < self.status["fromStation"]["uic"] < 5400000:
                vagonweb_operatorcode = "CFR"
            elif 5400000 < self.status["fromStation"]["uic"] < 5500000:
                vagonweb_operatorcode = "CD"
            elif 5500000 < self.status["fromStation"]["uic"] < 5600000:
                vagonweb_operatorcode = "MÁV"
            elif 5600000 < self.status["fromStation"]["uic"] < 5700000:
                vagonweb_operatorcode = "ZSSK"
            elif 7900000 < self.status["fromStation"]["uic"] < 8000000:
                vagonweb_operatorcode = "SŽ"

        if not vagonweb_operatorcode:
            return

        nr = self.status["train"]["no"]
        year = datetime.now().year
        url = f"https://www.vagonweb.cz/razeni/vlak.php?zeme={vagonweb_operatorcode}&cislo={nr}&rok={year}&lang=de"

        # Vagonweb / vaz hosting blocks python-requests user agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36",
            "Referer": url,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    soup = BeautifulSoup(await response.text(), "html.parser")
            plan_nodes = soup.select("#planovane_razeni table")
        except:
            print(f"vagonweb request broke")
            traceback.print_exc()
            self.patch_patch({"failedcomposition-vagonweb": True})
            return
        if plan_nodes:
            try:
                zugname = None
                try:
                    zugname = soup.find("div", id="cesta3").find("i").text
                except:
                    pass
                carriage_nodes = plan_nodes[0].select(
                    "td.bunka_vozu a", title=re.compile(r"^Züge mit Wagen:")
                )
                if carriage_nodes:
                    carriages = []
                    composition = []
                    same_type_counter = [0, ""]
                    for node in carriage_nodes:
                        if "Züge mit Wagen:" in node["title"]:
                            wagentyp = node["title"].replace("Züge mit Wagen: ", "")
                            carriages.append(wagentyp)
                            if same_type_counter[1] == wagentyp:
                                same_type_counter[0] += 1
                            else:
                                if same_type_counter[0] == 1:
                                    composition.append(same_type_counter[1])
                                elif same_type_counter[0]:
                                    composition.append(
                                        f"{same_type_counter[0]}x {same_type_counter[1]}"
                                    )
                                same_type_counter = [1, wagentyp]
                    if same_type_counter[0] == 1:
                        composition.append(same_type_counter[1])
                    elif same_type_counter[0]:
                        composition.append(
                            f"{same_type_counter[0]}x {same_type_counter[1]}"
                        )
                    composition_text = " + ".join(
                        [format_composition_element(unit) for unit in composition]
                    )
                link = Link.make(url)
                self.patch_patch(
                    {
                        "composition": f"[{composition_text}]({config['shortener_url']}/{link.short_id})"
                    }
                )
                if zugname:
                    if "messages" not in self.hafas_data:
                        self.hafas_data["messages"] = []
                    self.hafas_data["messages"].append(
                        {
                            "code": "ZN",
                            "short": None,
                            "text": zugname,
                            "type": "I",
                        }
                    )
                    DB.execute(
                        "UPDATE trips SET hafas_data=? WHERE user_id = ? AND journey_id = ?",
                        (
                            json.dumps(self.hafas_data),
                            self.user_id,
                            self.journey_id,
                        ),
                    )
            except:
                print("vagonweb parsing went wrong")
                traceback.print_exc()
                self.patch_patch({"failedcomposition-vagonweb": True})

    async def get_oebb_composition(self):
        if "composition" in self.status:
            return
        if not self.status["train"]["no"]:
            return

        composition_text = None
        if (
            station_no := oebb_wr.get_station_no(self.status["fromStation"]["name"])
        ) and (
            oebb_composition := await oebb_wr.get_composition(
                self.status["train"]["no"],
                station_no,
                datetime.fromtimestamp(
                    self.status["fromStation"]["scheduledTime"], tz=tz
                ),
            )
        ):
            composition = []
            same_type_counter = [0, ""]
            for wagon in oebb_composition:
                if wagon["class_name"].startswith("7x"):
                    composition.append(wagon["class_name"])
                elif same_type_counter[1] == wagon["class_name"]:
                    same_type_counter[0] += 1
                else:
                    if same_type_counter[0] == 1:
                        composition.append(same_type_counter[1])
                    elif same_type_counter[0]:
                        composition.append(
                            f"{same_type_counter[0]}x {same_type_counter[1]}"
                        )
                    same_type_counter = [1, wagon["class_name"]]
            if same_type_counter[0] == 1:
                composition.append(same_type_counter[1])
            elif same_type_counter[0]:
                composition.append(f"{same_type_counter[0]}x {same_type_counter[1]}")

            composition_text = " + ".join(
                [format_composition_element(unit) for unit in composition]
            )
            departure = datetime.fromtimestamp(
                self.status["fromStation"]["scheduledTime"], tz=tz
            )
            link = Link.make(
                f"https://live.oebb.at/train-info?trainNr={self.status['train']['no']}"
                f"&date={departure:%Y-%m-%d}&station={self.status['fromStation']['uic']}"
                f"&time={departure:%H%%3A%M}"
            )
            self.patch_patch(
                {
                    "composition": f"[{composition_text}]({config['shortener_url']}/{link.short_id})"
                }
            )

    async def get_ns_composition(self):
        if "composition" in self.status or "failedcomposition-ns" in self.status:
            return
        if not self.status["train"]["no"]:
            return
        if not (8400000 < (self.status["fromStation"]["uic"] or 0) < 8500000):
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://vt.ns-mlab.nl/api/v1/trein?ids="
                    f"{self.status['train']['no']}"
                ) as response:
                    parsed = await response.json()
                    material = parsed[0]["materieeldelen"]
                    composition_text = " + ".join(
                        [
                            f"**{deel['type'] or 'Trein'}** {deel.get('materieelnummer') or ''}"
                            for deel in material
                        ]
                    )
                    self.patch_patch({"composition": composition_text})
        except:
            print(f"ns request broke")
            traceback.print_exc()
            self.patch_patch({"failedcomposition-ns": True})
            return


@dataclass
class Message:
    "messages created by the live feed function"
    journey_id: str
    user_id: int
    channel_id: int
    message_id: int

    async def fetch(self, bot):
        channel = bot.get_channel(self.channel_id)
        return await channel.fetch_message(self.message_id)

    async def delete(self, bot):
        await (await self.fetch(bot)).delete()
        DB.execute("DELETE FROM messages WHERE message_id = ?", (self.message_id,))

    @classmethod
    def find_all(cls, user_id, journey_id):
        rows = DB.execute(
            "SELECT * FROM messages WHERE user_id = ? AND journey_id = ?",
            (user_id, journey_id),
        ).fetchall()
        return [cls(**row) for row in rows]

    @classmethod
    def find(cls, user_id, journey_id, channel_id):
        if row := DB.execute(
            "SELECT * FROM messages WHERE user_id = ? AND journey_id = ? AND channel_id = ?",
            (user_id, journey_id, channel_id),
        ).fetchone():
            return cls(**row)
        return None

    @classmethod
    def find_newer_than(cls, user_id, channel_id, message_id):
        if row := DB.execute(
            "SELECT * FROM messages WHERE message_id > ? AND user_id = ? AND channel_id = ? ORDER BY message_id LIMIT 1;",
            (message_id, user_id, channel_id),
        ).fetchone():
            return cls(**row)
        return None

    def write(self):
        DB.execute(
            "INSERT INTO messages(journey_id, user_id, channel_id, message_id) VALUES(?,?,?,?)",
            (self.journey_id, self.user_id, self.channel_id, self.message_id),
        )


@dataclass
class Link:
    "shortened URLs generated by the bot"
    short_id: str
    long_url: str

    @classmethod
    def find_by_short(cls, short_id):
        if row := DB.execute(
            "SELECT * FROM links WHERE short_id = ?",
            (short_id,),
        ).fetchone():
            return cls(**row)
        return None

    @classmethod
    def find_by_long(cls, long_url):
        if row := DB.execute(
            "SELECT * FROM links WHERE long_url = ?",
            (long_url,),
        ).fetchone():
            return cls(**row)
        return None

    def write(self):
        DB.execute(
            "INSERT INTO links(short_id, long_url) VALUES(?,?)",
            (self.short_id, self.long_url),
        )

    @classmethod
    def make(cls, long_url: str):
        if exists := cls.find_by_long(long_url):
            return exists
        while True:
            randid = random_id()
            if cls.find_by_short(randid):
                continue
            link = cls(randid, long_url)
            link.write()
            return link
