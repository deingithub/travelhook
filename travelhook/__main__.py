"this contains our bot commands and the incoming webhook handler"
import json
import secrets
import sqlite3
import typing

from aiohttp import ClientSession, web
import discord
from discord.ext import commands

from .format import format_travelynx
from .helpers import is_new_journey, is_token_valid, Privacy, train_type_color, zugid

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)

database = sqlite3.connect(config["database"], isolation_level=None)
database.row_factory = sqlite3.Row

servers = [
    discord.Object(id=row["server_id"])
    for row in database.execute("SELECT server_id FROM servers").fetchall()
]
intents = discord.Intents.default() | discord.Intents(members=True)
bot = commands.Bot(command_prefix=" ", intents=intents)


async def setup_hook():
    "enable restart persistence for the register button by adding the view on start"
    bot.add_view(RegisterTravelynxStepZero())


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    "once we're logged in, set up commands and start the web server"
    for server in servers:
        await bot.tree.sync(guild=server)
    bot.loop.create_task(receive(bot))
    print(f"logged in as {bot.user}")


def handle_status_update(userid, _, status):
    """update trip data in the database, also starting a new journey if the last data
    we have is too old or distant for this to be a changeover"""
    if last_trip := database.execute(
        "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time DESC LIMIT 1;",
        (userid,),
    ).fetchone():
        last_trip = json.loads(last_trip["travelynx_status"])
        if not zugid(status) == zugid(last_trip) and is_new_journey(
            database, status, userid
        ):
            database.execute("DELETE FROM trips WHERE user_id = ?", (userid,))
            database.execute("DELETE FROM messages WHERE user_id = ?", (userid,))

    database.execute(
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


async def receive(bot):
    """our own little web server that receives incoming webhooks from
    travelynx and runs the live feed for the users that have enabled it"""

    async def handler(req):
        user = database.execute(
            "SELECT * FROM users WHERE token_webhook = ?",
            (req.headers["authorization"].removeprefix("Bearer "),),
        ).fetchone()
        if not user:
            print(f"unknown user {req.headers['authorization']}")
            return

        userid = user["discord_id"]
        data = await req.json()

        if data["reason"] == "ping" and not data["status"]["checkedIn"]:
            return web.Response(text="travelynx relay bot successfully connected!")

        if (
            not data["reason"] in ("update", "checkin", "ping", "checkout", "undo")
            or not data["status"]["toStation"]["name"]
        ):
            raise web.HTTPNoContent()

        # when checkin is undone, delete its message
        if data["reason"] == "undo" and not data["status"]["checkedIn"]:
            current_trips = database.execute(
                "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time ASC",
                (userid,),
            ).fetchall()
            current_trips = [
                json.loads(row["travelynx_status"]) for row in current_trips
            ]
            database.execute(
                "DELETE FROM trips WHERE user_id = ? AND journey_id = ?",
                (userid, zugid(data["status"])),
            )

            messages_to_delete = database.execute(
                "SELECT * FROM messages WHERE user_id = ? AND journey_id = ?",
                (userid, zugid(current_trips[-1])),
            ).fetchall()
            for message in messages_to_delete:
                channel = bot.get_channel(message["channel_id"])
                msg = await channel.fetch_message(message["message_id"])
                await msg.delete()
            database.execute(
                "DELETE FROM messages WHERE user_id = ? AND journey_id = ?",
                (userid, zugid(current_trips[-1])),
            )

            if len(current_trips) > 1:
                messages_to_edit = database.execute(
                    "SELECT * FROM messages WHERE user_id = ? AND journey_id = ?",
                    (userid, zugid(current_trips[-2])),
                ).fetchall()
                for message in messages_to_edit:
                    channel = bot.get_channel(message["channel_id"])
                    msg = await channel.fetch_message(message["message_id"])
                    await msg.edit(
                        embeds=format_travelynx(
                            bot, database, userid, current_trips[0:-1]
                        ),
                        view=None,
                    )

            return web.Response(
                text=f'Unpublished checkin to {current_trips[-1]["train"]["type"]} {current_trips[-1]["train"]["no"]} for {len(messages_to_delete)} channels'
            )

        # don't share completely private checkins, only unlisted and upwards
        if data["status"]["visibility"]["desc"] == "private":
            # just to make sure we don't have it lying around for some reason anyway
            database.execute(
                "DELETE FROM trips WHERE user_id = ? AND journey_id = ?",
                (userid, zugid(data["status"])),
            )
            return web.Response(
                text=f'Not publishing private {data["reason"]} in {data["status"]["train"]["type"]} {data["status"]["train"]["no"]}'
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
            if (
                not channel.guild.get_member(userid)
                or not channel.permissions_for(
                    channel.guild.get_member(userid)
                ).read_messages
            ):
                continue
            # check if we already have a message for this particular trip
            # edit it if it exists, otherwise create a new one and submit it into the database
            if message := database.execute(
                "SELECT * FROM messages WHERE journey_id = ? AND user_id = ? AND channel_id = ?",
                (zugid(data["status"]), userid, channel.id),
            ).fetchone():
                message = await channel.fetch_message(message["message_id"])
                await message.edit(
                    embeds=format_travelynx(bot, database, userid, current_trips),
                    view=(
                        RefreshTravelynx(userid, current_trips[-1])
                        if not data["reason"] == "checkout"
                        else None
                    ),
                )
            else:
                message = await channel.send(
                    embeds=format_travelynx(bot, database, userid, current_trips),
                    view=(
                        RefreshTravelynx(userid, current_trips[-1])
                        if not data["reason"] == "checkout"
                        else None
                    ),
                )
                database.execute(
                    "INSERT INTO messages(journey_id, user_id, channel_id, message_id) VALUES(?,?,?,?)",
                    (zugid(data["status"]), userid, channel.id, message.id),
                )
                # shrink previous message to prevent clutter
                if len(current_trips) > 1:
                    prev_message = database.execute(
                        "SELECT message_id, channel_id FROM messages JOIN trips ON messages.journey_id = trips.journey_id "
                        "WHERE messages.channel_id = ? AND messages.user_id = ? AND messages.journey_id = ?",
                        (channel.id, userid, zugid(current_trips[-2])),
                    ).fetchone()
                    prev_message = await bot.get_channel(
                        prev_message["channel_id"]
                    ).fetch_message(prev_message["message_id"])
                    await prev_message.edit(
                        embeds=format_travelynx(
                            bot,
                            database,
                            userid,
                            current_trips[0:-1],
                            continue_link=message.jump_url,
                        ),
                        view=None,
                    )
        return web.Response(
            text=f'Successfully published {data["status"]["train"]["type"]} {data["status"]["train"]["no"]} {data["reason"]} to {len(channels)} channels'
        )

    app = web.Application()
    app.router.add_post("/travelynx", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 6005)
    await site.start()


@bot.tree.command(guilds=servers)
@discord.app_commands.describe(
    level="leave empty to query current level. set to ME to only allow you to use /zug, set to EVERYONE to allow everyone to use /zug and set to LIVE to activate the live feed."
)
async def privacy(ia, level: typing.Optional[Privacy]):
    "Query or change your current privacy settings on this server"

    def explain(level: typing.Optional[Privacy]):
        desc = "This means that, on this server,\n"
        match level:
            case Privacy.ME:
                desc += "- Only you can use the **/zug** command to share your current journey."
            case Privacy.EVERYONE:
                desc += "- Everyone can use the **/zug** command to see your current journey."
            case Privacy.LIVE:
                desc += "- Everyone can use the **/zug** command to see your current journey.\n"
                if live_channel := database.execute(
                    "SELECT live_channel FROM servers WHERE server_id = ?",
                    (ia.guild.id,),
                ).fetchone()["live_channel"]:
                    desc += f"- Live updates will posted into {bot.get_channel(live_channel).mention} with your entire journey."
                else:
                    desc += (
                        "- Live updates with your entire journey can be posted into a dedicated channel.\n"
                        "- Note: This server has not set up a live channel. No live updates will be posted until it is set up."
                    )
        desc += "\n- Note: If your checkin is set to **private visibility** on travelynx, this bot will not post it anywhere."
        return desc

    if level is None:
        user = database.execute(
            "SELECT * FROM users LEFT JOIN privacy ON privacy.user_id = users.discord_id AND server_id = ? WHERE users.discord_id = ?",
            (
                ia.guild.id,
                ia.user.id,
            ),
        ).fetchone()
        priv = Privacy(user["privacy_level"] or 0)

        await ia.response.send_message(
            f"Your privacy level is set to **{priv.name}**. {explain(priv)}"
        )

    else:
        database.execute(
            "INSERT INTO privacy(user_id, server_id, privacy_level) VALUES(?,?,?) "
            "ON CONFLICT DO UPDATE SET privacy_level=excluded.privacy_level",
            (
                ia.user.id,
                ia.guild.id,
                int(level),
            ),
        )
        await ia.response.send_message(
            f"Your privacy level has been set to **{level.name}**. {explain(level)}"
        )


@bot.tree.command(guilds=servers)
@discord.app_commands.describe(
    member="the member whose status to query, defaults to current user"
)
async def zug(ia, member: typing.Optional[discord.Member]):
    "Get current travelynx status"
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

                if not status["checkedIn"] or (
                    status["visibility"]["desc"] == "private"
                ):
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
                    embeds=format_travelynx(bot, database, member.id, current_trips),
                    view=RefreshTravelynx(member.id, current_trips[-1]),
                )


@bot.tree.command(guilds=servers)
async def register(ia):
    "Register with the travelynx relay bot and share your journeys today!"
    await ia.response.send_message(
        embed=discord.Embed(
            title="Registering with the travelynx relay bot",
            color=train_type_color["SB"],
            description="Thanks for your interest! Using this bot, you can share your public transport journeys "
            "in and around Germany with your friends and enemies on Discord.\nTo use it, you first need to sign up for "
            "**[travelynx](https://travelynx.de)** to be able to check in into trains, trams, buses and so on. Then you "
            "can connect this bot to your travelynx account.\nFinally, for every server you can decide if *only you* want to share "
            "some of our journeys using the **/zug** command (this is the default), or if you want to let *everyone* "
            "use the command for you. You can even enable a **live feed** for a specific channel, keeping everyone "
            "up to date as you check in into new transports. This is fully optional.",
        ).set_thumbnail(
            url="https://cdn.discordapp.com/emojis/1160275971266576494.webp"
        ),
        view=RegisterTravelynxStepZero(),
    )


class RegisterTravelynxStepZero(discord.ui.View):
    """view attached to the /register initial response, is persistent over restarts.
    first we check that we aren't already registered, then offer to proceed to step 1 with token modal"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Connect travelynx account",
        style=discord.ButtonStyle.green,
        custom_id="register_button",
    )
    async def doit(self, ia, _):
        "button to proceed to step 1"
        if database.execute(
            "SELECT * FROM users WHERE discord_id = ?", (ia.user.id,)
        ).fetchone():
            await ia.response.send_message(
                embed=discord.Embed(
                    title="Oops!",
                    color=train_type_color["U1"],
                    description="It looks like you're already registered. If you want to reset your tokens or need "
                    "any other assistance, please ask the bot operator.",
                ),
                ephemeral=True,
            )
        await ia.response.send_message(
            embed=discord.Embed(
                title="Step 1/3: Connect Status API",
                color=train_type_color["SB"],
                description="For the first step, you'll need to give the bot read access to your travelynx account. "
                "To do this, head over to the [**travelynx Account page**](https://travelynx.de/account) "
                "while signed in, scroll down to «API», and click **Generate** in the table row with «Status».\n"
                " Copy the token you just generated from the row. Return here, click «I have my token ready.» "
                "below and enter the token into the pop-up.",
            ).set_image(url="https://i.imgur.com/Tu2Zm6C.png"),
            view=RegisterTravelynxStepOne(),
            ephemeral=True,
        )


class RegisterTravelynxStepOne(discord.ui.View):
    """view attached to the step 1 ephemeral response. ask for and verify the status token,
    register the user, then offer to proceed to step 2 to copy live feed/webhook credentials."""
    @discord.ui.button(label="I have my token ready.", style=discord.ButtonStyle.green)
    async def doit(self, ia, _):
        "just send the modal when the user has the token ready"
        await ia.response.send_modal(self.EnterTokenModal())

    class EnterTokenModal(discord.ui.Modal, title="Please enter your travelynx token"):
        "this contains the actual verification and registration code."
        token = discord.ui.TextInput(label="Status token")

        async def on_submit(self, ia):
            """triggered on modal submit, if everything is fine, register the user and
            edit ephemeral response to proceed to step 2, else ask them to try again"""
            if await is_token_valid(self.token.value.strip()):
                database.execute(
                    "INSERT INTO users (discord_id, token_status, token_webhook) VALUES(?,?,?)",
                    (ia.user.id, self.token.value.strip(), secrets.token_urlsafe()),
                )
                await ia.response.edit_message(
                    embed=discord.Embed(
                        title="Step 2/3: Connect Live Feed (optional)",
                        color=train_type_color["SB"],
                        description="Great! You've successfully connected your status token to the relay bot. "
                        "You now use **/zug** for yourself and configure if others can use it with **/privacy**.\n"
                        "Optionally, you can now also sign up for the live feed by connecting travelynx's webhook "
                        "to the relay bot's live feed feature. You can also skip this if you're not interested in the live "
                        "feed. Should you change your mind later, you can bother the bot operator about it.",
                    ),
                    view=RegisterTravelynxStepTwo(),
                )
            else:
                await ia.response.edit_message(
                    embed=discord.Embed(
                        title="Step 1/3: Connect Status API",
                        color=train_type_color["U1"],
                        description="### ❗ The token doesn't seem to be valid, please check it and try again.\n"
                        "For the first step, you'll need to give the bot read access to your travelynx account. "
                        "To do this, head over to the [**Account page**](https://travelynx.de/account) "
                        "while signed in, scroll down to «API», and click **Generate** in the table row with «Status».\n"
                        " Copy the token you just generated from the row. Return here, click «I have my token ready.» "
                        "below and enter the token into the pop-up.",
                    ).set_image(url="https://i.imgur.com/Tu2Zm6C.png")
                )


class RegisterTravelynxStepTwo(discord.ui.View):
    "view triggered by successful registration in step 1, show credentials for live feed if asked"
    @discord.ui.button(label="Connect live feed", style=discord.ButtonStyle.green)
    async def doit(self, ia, _):
        "offer the live feed webhook credentials for copying"
        token = database.execute(
            "SELECT token_webhook FROM users WHERE discord_id = ?", (ia.user.id,)
        ).fetchone()["token_webhook"]
        await ia.response.edit_message(
            embed=discord.Embed(
                title="Step 3/3: Connect live feed (optional)",
                color=train_type_color["S"],
                description="Congratulations! You can now use **/zug** and **/privacy** to share your logged "
                "journeys on Discord.\n\nWith the live feed enabled on a server, once your server admins have set up a "
                "live channel  *that you can see yourself*, the relay bot will automatically post non-private "
                "checkins and try to keep your journey up to date. To connect travelynx's update webhook "
                "with the relay bot, you need to head to the [**Account » Webhook page**](https://travelynx.de/account/hooks), "
                "check «Aktiv» and enter the following values: \n\n"
                f"**URL**\n```{config['webhook_url']}```\n"
                f"**Token**\n```{token}```\n\n"
                "Once you've done that, save the webhook settings, and you should be able to read "
                "«travelynx relay bot successfully connected!» in the server response. If that doesn't happen, "
                "bother the bot operator about it.\nIf you changed your mind and don't want to connect right now, "
                "bother the bot operator about it once you've decided otherwise again. Until you copy in the settings, "
                "no live connection will be made.",
            ).set_image(url="https://i.imgur.com/LhsH8Nt.png"),
            view=None,
        )

    @discord.ui.button(label="No, I don't want that.", style=discord.ButtonStyle.grey)
    async def dontit(self, ia, _):
        "just wish them a nice day"
        await ia.response.edit_message(
            embed=discord.Embed(
                title="Step 3/3: Done!",
                color=train_type_color["S"],
                description="Congratulations! You can now use **/zug** and **/privacy** to share your logged journeys on Discord.",
            ),
            view=None,
        )


class RefreshTravelynx(discord.ui.View):
    """fetches the current trip rendered in the embed this view's attached to
    and updates the message accordingly"""

    def __init__(self, userid, data):
        """we store the primary key of the trips table (user id and user-trip zugid)
        in the view to fetch the correct trip again"""
        super().__init__()
        self.timeout = None
        self.userid = userid
        self.zugid = zugid(data)

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.grey)
    async def refresh(self, ia, _):
        "the refresh button"
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
                            "SELECT travelynx_status FROM trips WHERE user_id = ? ORDER BY from_time ASC",
                            (self.userid,),
                        ).fetchall()
                        current_trips = [
                            json.loads(row["travelynx_status"]) for row in current_trips
                        ]
                        await ia.response.edit_message(
                            embeds=format_travelynx(
                                bot, database, self.userid, current_trips
                            ),
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
