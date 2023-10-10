# pylint: disable=missing-function-docstring
"contains and encapsulates database accesses"
import json
import sqlite3
from dataclasses import dataclass, astuple
from enum import IntEnum
from typing import Optional

import discord

from .helpers import zugid

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
            "INSERT INTO users (discord_id, token_status, token_webhook, token_travel) VALUES(?,?,?,?)",
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

    def find_live_channel_ids(self):
        rows = DB.execute(
            "SELECT servers.live_channel FROM servers JOIN privacy on servers.server_id = privacy.server_id "
            "WHERE privacy.user_id = ? AND privacy.privacy_level = ?;",
            (self.discord_id, Privacy.LIVE),
        ).fetchall()
        return [row["live_channel"] for row in rows]


@dataclass
class Trip:
    "user-trips the bot knows about"
    journey_id: int
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

    def __post_init__(self):
        self.status = json.loads(self.travelynx_status)

    @classmethod
    def find(cls, user_id, journey_id):
        row = DB.execute(
            "SELECT * FROM trips WHERE user_id = ? AND journey_id = ?",
            (user_id, journey_id),
        ).fetchone()
        return cls(**row)

    @classmethod
    def find_current_trips_for(cls, user_id):
        rows = DB.execute(
            "SELECT * FROM trips WHERE user_id = ? ORDER BY from_time ASC", (user_id,)
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
            "to_time = excluded.to_time, to_station=excluded.to_station, to_lat=excluded.to_lat, to_lon=excluded.to_lon ",
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

    def write(self):
        DB.execute(
            "INSERT INTO messages(journey_id, user_id, channel_id, message_id) VALUES(?,?,?,?)",
            (self.journey_id, self.user_id, self.channel_id, self.message_id),
        )
