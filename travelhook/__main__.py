import json
import typing
import sqlite3

from aiohttp import ClientSession, web
import discord
from discord.ext import commands

from .format import format_travelynx
from .helpers import is_new_journey, Privacy, zugid

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)

database = sqlite3.connect(config["database"], isolation_level=None)
database.row_factory = sqlite3.Row

servers = [
    discord.Object(id=row["server_id"])
    for row in database.execute("SELECT server_id FROM servers").fetchall()
]


def handle_status_update(userid, reason, status):
    if last_trip := database.execute(
        "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time DESC LIMIT 1;",
        (userid,),
    ).fetchone():
        last_trip = json.loads(last_trip["travelynx_status"])
        if not zugid(status) == zugid(last_trip) and is_new_journey(
            database, status, userid
        ):
            database.execute("DELETE FROM trips WHERE user_id = ?", (userid,))

    database.execute(
        "INSERT INTO trips(journey_id, user_id, travelynx_status, from_time, from_station, from_lat, from_lon, to_time, to_station, to_lat, to_lon) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET travelynx_status=excluded.travelynx_status, "
        "from_time = excluded.from_time, from_station=excluded.from_station, from_lat=excluded.from_lat, from_lon=excluded.from_lon, "
        "to_time = excluded.to_time, to_station=excluded.to_station, to_lat=excluded.to_lat, to_lon=excluded.to_lon ",
        (
            status["train"]["id"],
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


async def receive(bot):
    async def handler(req):
        user = database.execute(
            "SELECT * FROM users WHERE token_webhook = ?",
            (req.headers["authorization"].removeprefix("Bearer "),)
        ).fetchone()
        userid = user["discord_id"]
        data = await req.json()

        if (
            not data["reason"] in ("update", "checkin", "ping")
            or not data["status"]["toStation"]["name"]
            or not data["status"]["checkedIn"]
        ):
            raise web.HTTPOk()

        # don't share completely private checkins, only unlisted and upwards
        if data["status"]["visibility"]["desc"] == "private":
            # just to make sure we don't have it lying around for some reason anyway
            database.execute(
                "DELETE FROM trips WHERE user_id = ? AND journey_id = ?",
                (userid, data["status"]["train"]["id"]),
            )
            return web.Response(
                text=f'Not publishing private checkin in {data["status"]["train"]["type"]} {data["status"]["train"]["no"]}'
            )

        # update database to maintain trip data
        handle_status_update(userid, data["reason"], data["status"])

        current_trips = database.execute(
            "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time ASC",
            (userid,),
        ).fetchall()
        current_trips = [json.loads(row["travelynx_status"]) for row in current_trips]

        # get all channels that live updates get pushed to for this user
        channels = database.execute(
            "SELECT servers.live_channel FROM servers JOIN privacy on servers.server_id = privacy.server_id "
            "WHERE privacy.user_id = ? AND privacy.privacy_level = ?;",
            (userid, Privacy.LIVE),
        ).fetchall()
        channels = [bot.get_channel(c["live_channel"]) for c in channels]

        for channel in channels:
            # check if we already have a message for this particular trip
            # edit it if it exists, otherwise create a new one and submit it into the database
            if message := database.execute(
                "SELECT * FROM messages WHERE journey_id = ? AND user_id = ? AND channel_id = ?",
                (data["status"]["train"]["id"], userid, channel.id),
            ).fetchone():
                message = await channel.fetch_message(
                    message["message_id"]
                )
                await message.edit(
                    embed=format_travelynx(bot, userid, current_trips),
                    view=RefreshTravelynx(userid, current_trips[-1]),
                )
            else:
                message = await channel.send(
                    embed=format_travelynx(bot, userid, current_trips),
                    view=RefreshTravelynx(userid, current_trips[-1]),
                )
                database.execute(
                    "INSERT INTO messages(journey_id, user_id, channel_id, message_id) VALUES(?,?,?,?)",
                    (data["status"]["train"]["id"], userid, channel.id, message.id),
                )
                # shrink previous message to prevent clutter
                if len(current_trips) > 1:
                    prev_message = database.execute(
                        "SELECT message_id, channel_id FROM messages JOIN trips ON messages.journey_id = trips.journey_id "
                        "WHERE messages.channel_id = ? AND messages.user_id = ? AND messages.journey_id = ?",
                        (channel.id, userid, current_trips[-2]["train"]["id"]),
                    ).fetchone()
                    prev_message = await bot.get_channel(
                        prev_message["channel_id"]
                    ).fetch_message(prev_message["message_id"])
                    await prev_message.edit(
                        embed=format_travelynx(
                            bot,
                            userid,
                            [current_trips[-2]],
                            continue_link=message.jump_url,
                        ),
                        view=None,
                    )

        return web.Response(
            text=f'Successfully published {data["status"]["train"]["type"]} {data["status"]["train"]["no"]} to {len(channels)} channels'
        )

    app = web.Application()
    app.router.add_post("/travelynx", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 6005)
    await site.start()


intents = discord.Intents.default() | discord.Intents(members=True)
bot = commands.Bot(command_prefix=" ", intents=intents)


@bot.event
async def on_ready():
    for server in servers:
        await bot.tree.sync(guild=server)
    bot.loop.create_task(receive(bot))
    print(f"logged in as {bot.user}")


@bot.tree.command(description="Get current travelynx status", guilds=servers)
@discord.app_commands.describe(
    member="the member whose status to query, defaults to current user"
)
async def zug(ia, member: typing.Optional[discord.Member]):
    if not member:
        member = ia.user

    user = database.execute(
        "SELECT * FROM users LEFT JOIN privacy ON privacy.user_id = users.discord_id AND server_id = ? WHERE users.discord_id = ?",
        (
            ia.guild.id,
            member.id,
        ),
    ).fetchone()

    if (
        member.id != user["discord_id"]
        and Privacy(user["privacy_level"] or 0) == Privacy.ME
    ):
        await ia.response.send_message(
            embed=discord.Embed().set_author(
                name=f"{member.name} ist gerade nicht unterwegs",
                icon_url=member.avatar.url,
            )
        )
        return

    async with ClientSession() as session:
        async with session.get(
            f'https://travelynx.de/api/v1/status/{user["token_status"]}'
        ) as r:
            if r.status == 200:
                status = await r.json()

                if not status["checkedIn"]:
                    await ia.response.send_message(
                        embed=discord.Embed().set_author(
                            name=f"{member.name} ist gerade nicht unterwegs",
                            icon_url=member.avatar.url,
                        )
                    )
                    return

                handle_status_update(member.id, "update", status)
                current_trips = database.execute(
                    "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time ASC",
                    (member.id,),
                ).fetchall()
                current_trips = [
                    json.loads(row["travelynx_status"]) for row in current_trips
                ]

                await ia.response.send_message(
                    embed=format_travelynx(bot, member.id, current_trips),
                    view=RefreshTravelynx(member.id, current_trips[-1]),
                )

# TODO privacy adjust command

# TODO register command

class RefreshTravelynx(discord.ui.View):
    def __init__(self, userid, data):
        super().__init__()
        self.timeout = None
        self.userid = userid
        self.zugid = zugid(data)

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.grey)
    async def refresh(self, ia, button):
        user = database.execute(
            "SELECT token_status FROM users WHERE discord_id = ?", (self.userid,)
        ).fetchone()
        async with ClientSession() as session:
            async with session.get(
                f'https://travelynx.de/api/v1/status/{user["token_status"]}'
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data["checkedIn"] and self.zugid == zugid(data):
                        handle_status_update(self.userid, "update", data)
                        current_trips = database.execute(
                            "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time ASC", (self.userid,)
                        ).fetchall()
                        current_trips = [
                            json.loads(row["travelynx_status"]) for row in current_trips
                        ]
                        await ia.response.edit_message(
                            embed=format_travelynx(bot, self.userid, current_trips),
                            view=self,
                        )
                    else:
                        await ia.response.send_message(
                            "Die Fahrt ist bereits zu Ende.", ephemeral=True
                        )


def main():
    "the function."
    bot.run(config["token"])


if __name__ == "__main__":
    main()
