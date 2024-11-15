# pylint: disable=missing-function-docstring
"contains and encapsulates database accesses"
import asyncio
import collections
import json
import sqlite3
import shlex
import subprocess
import traceback
from dataclasses import dataclass, astuple
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from pyhafas.types.fptf import Stopover

from .helpers import (
    zugid,
    hafas,
    tz,
    random_id,
    replace_headsign,
    format_composition_element,
    db_replace_group_classes,
    describe_class,
)
from . import oebb_wr

DB = None


def connect(path):
    global DB
    DB = sqlite3.connect(path, isolation_level=None)
    DB.row_factory = sqlite3.Row


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
        we can fix that."""

        if self.status["toStation"]["realTime"] > 0:
            return

        if self.status["toStation"]["scheduledTime"] > 0:
            self.status["toStation"]["realTime"] = self.status["toStation"][
                "scheduledTime"
            ]
            self.upsert(self.user_id, self.status)
            return

        try:
            this_trip = hafas.trip(
                self.status["train"]["hafasId"] or self.status["train"]["id"]
            )
            stops = [
                Stopover(
                    stop=this_trip.destination,
                    arrival=this_trip.arrival,
                    arrival_delay=this_trip.arrivalDelay,
                )
            ]
            if this_trip.stopovers:
                stops += this_trip.stopovers

            for stopover in this_trip.stopovers:
                if stopover.stop.name == self.status["toStation"]["name"]:
                    sched = int(stopover.arrival.timestamp())
                    if (
                        not sched > self.status["fromStation"]["scheduledTime"]
                    ):  # might be a ring line too after all
                        continue

                    self.status["toStation"]["scheduledTime"] = sched
                    self.status["toStation"]["realTime"] = sched + int(
                        (stopover.departureDelay or timedelta()).total_seconds()
                    )
                    self.upsert(self.user_id, self.status)
                    return
        except:  # pylint: disable=bare-except
            print("error while running 1970 fixup:")
            traceback.print_exc()

    def maybe_fix_circle_line(self):
        """if we're on a line that visits the same stop more than once, we might be logged on
        the first time the stop is visited. if we can detect this, skip to the first stop that wouldn't
        make the journey have time skips in it."""

        trip = DB.execute(
            "SELECT json_patch(travelynx_status, status_patch) ->> '$.toStation.realTime' as arrival, "
            "json_patch(travelynx_status, status_patch) ->> '$.actionTime' as at "
            "FROM trips WHERE user_id = ? AND arrival > ? AND at < ? ORDER BY at DESC LIMIT 1",
            (
                self.user_id,
                self.status["fromStation"]["realTime"],
                self.status["actionTime"],
            ),
        ).fetchone()
        if not trip:
            return

        print("this sure smells like a erlangen type situation", dict(trip))

        try:
            this_trip = hafas.trip(
                self.status["train"]["hafasId"] or self.status["train"]["id"]
            )
            stops = []
            if this_trip.stopovers:
                stops += this_trip.stopovers

            stops = [
                stop
                for stop in stops
                if stop.stop.id == str(self.status["fromStation"]["uic"])
                and stop.departure
                and (stop.departure + (stop.departureDelay or timedelta()))
                >= datetime.fromtimestamp(trip["arrival"], tz=tz)
            ]
            if stops:
                print(
                    f"found some! original {self.status['fromStation']} my best guess {stops[0]}"
                )
                departure_ts = int(stops[0].departure.timestamp())
                first_station_patch = {
                    "fromStation": {
                        "scheduledTime": departure_ts,
                        "realTime": int(stops[0].departure.timestamp())
                        + int((stops[0].departureDelay or timedelta()).total_seconds()),
                    }
                }
                if (
                    stops[0].departure.timestamp()
                    > self.status["toStation"]["scheduledTime"]
                ):
                    destination = this_trip.stopovers + [
                        Stopover(
                            stop=this_trip.destination,
                            arrival=this_trip.arrival,
                            arrival_delay=this_trip.arrivalDelay,
                        )
                    ]
                    print(
                        [
                            d
                            for d in destination
                            if d.arrival and d.arrival > stops[0].departure
                        ]
                    )
                    destination = [
                        stop
                        for stop in destination
                        if stop.stop.id == str(self.status["toStation"]["uic"])
                        and stop.arrival
                        and stop.arrival > stops[0].departure
                    ]
                    if destination:
                        arrival_ts = int(destination[0].arrival.timestamp())
                        first_station_patch["toStation"] = {
                            "scheduledTime": arrival_ts,
                            "realTime": arrival_ts
                            + int(
                                (
                                    destination[0].arrivalDelay or timedelta()
                                ).total_seconds()
                            ),
                        }
                newpatch = DB.execute(
                    "SELECT json_patch(?,?) AS newpatch",
                    (
                        json.dumps(first_station_patch),
                        json.dumps(self.status_patch),
                    ),
                ).fetchone()["newpatch"]
                self.write_patch(json.loads(newpatch))
        except:  # pylint: disable=bare-except
            print("error while running circle line fixup:")
            traceback.print_exc()

    def fetch_hafas_data(self, force: bool = False):
        "perform arcane magick (perl 'FFI') to get hafas data for our trip"

        backend = self.status["backend"]["name"]
        if self.status["backend"]["type"] == "IRIS-TTS":
            backend = "DB"
        elif backend == "ÖBB":
            backend = bytes(
                [214, 66, 66]
            )  # i REALLY wish i knew what the fuck is wrong with perl
        elif backend == "manual":
            return

        def write_hafas_data(departureboard_entry):
            hafas = subprocess.run(
                ["json-hafas.pl", backend, departureboard_entry["id"]],
                capture_output=True,
            )
            status = {}
            try:
                status = json.loads(hafas.stdout)
            except:  # pylint: disable=bare-except
                print(f"hafas perl broke:\n{hafas.stdout} {hafas.stderr}")
                traceback.print_exc()

            if "error_code" in status:
                print(f"hafas perl broke:\n{status}")
            else:
                self.hafas_data = status
                headsign = departureboard_entry["direction"]
                if not headsign:
                    headsign = status["route"][-1]["name"]
                if hs := self.maybe_fix_rnv_5(headsign):
                    headsign = hs
                train_key = (
                    (
                        self.status["train"]["type"].strip()
                        + (
                            self.status["train"]["line"] or self.status["train"]["no"]
                        ).strip()
                    ),
                    headsign,
                )
                headsign = replace_headsign.get(train_key, headsign) or "?"
                DB.execute(
                    "UPDATE trips SET hafas_data=?, headsign=? WHERE user_id = ? AND journey_id = ?",
                    (
                        json.dumps(status),
                        headsign,
                        self.user_id,
                        self.journey_id,
                    ),
                )

        if "travelhookfaked" in self.status["train"]["id"] or (
            "id" in self.hafas_data and not force
        ):
            return

        jid = self.status["train"]["hafasId"]
        if not jid and "|" in self.status["train"]["id"]:
            jid = self.status["train"]["id"]

        hafas_sb = subprocess.run(
            [
                "json-hafas-stationboard.pl",
                backend,
                str(self.status["fromStation"]["uic"]),
                str(self.status["fromStation"]["scheduledTime"]),
            ],
            capture_output=True,
        )
        stationboard = {}
        try:
            stationboard = json.loads(hafas_sb.stdout)
        except:  # pylint: disable=bare-except
            print(f"hafas sb perl broke:\n{hafas_sb.stdout} {hafas_sb.stderr}")
            traceback.print_exc()
            return
        if "error_code" in stationboard:
            print(f"hafas sb perl broke:\n{stationboard}")
            return

        for train in stationboard["trains"]:
            if not train["scheduled"] == self.status["fromStation"]["scheduledTime"]:
                continue
            if jid == train["id"] or (train["number"] == self.status["train"]["no"]):
                write_hafas_data(train)
                break
        else:
            print("didn't find a match!")

    def fetch_headsign(self):
        if headsign := (self.headsign or self.status["train"].get("fakeheadsign")):
            return headsign

        if not self.hafas_data:
            self.fetch_hafas_data()
        return self.headsign or "?"

    def maybe_fix_rnv_5(self, headsign):
        "try to detect which way the line 5 in mannheim is going"
        if not (
            self.hafas_data["operator"]
            == "Rhein-Neckar-Verkehr GmbH (Oberrheinische Eisenbahn)"
            and self.status["train"]["line"] == "5"
        ):
            return
        stops = [stop["name"] for stop in self.hafas_data["route"]]

        def next_stop(a, b):
            if i := stops.index(a):
                return stops[i + 1] == b

        if (
            next_stop("Hauptbahnhof, Mannheim", "Kunsthalle, Mannheim")
            or next_stop("Hauptbahnhof, Weinheim", "Alter OEG-Bahnhof, Weinheim")
            or next_stop("Hauptbahnhof, Heidelberg", "Gneisenaustraße Süd, Heidelberg")
        ):
            # mannheim→weinheim
            return f"{headsign} ↻"
        elif (
            next_stop("Hauptbahnhof, Mannheim", "Universität, Mannheim")
            or next_stop("Hauptbahnhof, Weinheim", "Händelstraße, Weinheim")
            or next_stop("Hauptbahnhof, Heidelberg", "Stadtwerke, Heidelberg")
        ):
            # mannheim→heidelberg
            return f"{headsign} ↺"

    def get_db_composition(self):
        if "composition" in self.status:
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

        if "error_string" in status:
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
            newpatch = DB.execute(
                "SELECT json_patch(?,?) AS newpatch",
                (
                    json.dumps({"composition": composition_text}),
                    json.dumps(self.status_patch),
                ),
            ).fetchone()["newpatch"]
            self.write_patch(json.loads(newpatch))

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

            newpatch = DB.execute(
                "SELECT json_patch(?,?) AS newpatch",
                (
                    json.dumps({"composition": composition_text}),
                    json.dumps(self.status_patch),
                ),
            ).fetchone()["newpatch"]
            self.write_patch(json.loads(newpatch))


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
