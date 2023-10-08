"contains our bot commands and the incoming webhook handler"
import json
import secrets
import typing
from datetime import datetime, timedelta

from aiohttp import ClientSession, web
import discord
from discord.ext import commands
from haversine import haversine

from . import database as DB
from .format import format_travelynx
from .helpers import is_token_valid, train_type_color, zugid, tz

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)

DB.connect(config["database"])

servers = [server.as_discord_obj() for server in DB.Server.find_all()]
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

    def is_new_journey(old, new):
        "determine if the user has merely changed into a new transport or if they have started another journey altogether"

        if old["train"]["id"] == new["train"]["id"]:
            return False

        change_from = old["toStation"]
        change_to = new["fromStation"]
        change_distance = haversine(
            (change_from["latitude"], change_from["longitude"]),
            (change_to["latitude"], change_to["longitude"]),
        )
        change_duration = datetime.fromtimestamp(
            change_to["realTime"], tz=tz
        ) - datetime.fromtimestamp(change_from["realTime"], tz=tz)

        return (change_distance > 2.0) or change_duration > timedelta(hours=2)

    if (last_trip := DB.Trip.find_last_trip_for(userid)) and is_new_journey(
        last_trip.status, status
    ):
        DB.User.find(discord_id=userid).break_journey()

    DB.Trip.upsert(userid, status)


async def receive(bot):
    """our own little web server that receives incoming webhooks from
    travelynx and runs the live feed for the users that have enabled it"""

    async def handler(req):
        user = DB.User.find(
            token_webhook=req.headers["authorization"].removeprefix("Bearer ")
        )
        if not user:
            print(f"unknown user {req.headers['authorization']}")
            return

        userid = user.discord_id
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
            last_trip = DB.Trip.find_last_trip_for(user.discord_id)
            messages_to_delete = DB.Message.find_all(
                user.discord_id, zugid(last_trip.status)
            )
            for message in messages_to_delete:
                await message.delete(bot)
            DB.Trip.find(user.discord_id, zugid(last_trip.status)).delete()

            if current_trips := [
                trip.status for trip in DB.Trip.find_current_trips_for(user.discord_id)
            ]:
                for message in DB.Message.find_all(
                    user.discord_id, zugid(current_trips[-1])
                ):
                    msg = await message.fetch(bot)
                    await msg.edit(
                        embeds=format_travelynx(bot, DB.DB, userid, current_trips),
                        view=None,
                    )

            return web.Response(
                text=f"Unpublished last checkin for {len(messages_to_delete)} channels"
            )

        # don't share completely private checkins, only unlisted and upwards
        if data["status"]["visibility"]["desc"] == "private":
            # just to make sure we don't have it lying around for some reason anyway
            DB.Trip.find(user.discord_id, zugid(data["status"])).delete()
            return web.Response(
                text=f'Not publishing private {data["reason"]} in {data["status"]["train"]["type"]} {data["status"]["train"]["no"]}'
            )

        # update database to maintain trip data
        handle_status_update(userid, data["reason"], data["status"])

        current_trips = [
            trip.status for trip in DB.Trip.find_current_trips_for(user.discord_id)
        ]

        # get all channels that live updates get pushed to for this user
        channels = [bot.get_channel(cid) for cid in user.find_live_channel_ids()]
        for channel in channels:
            member = channel.guild.get_member(user.discord_id)
            # don't post if the user has left or can't see the live channel
            if not member or not channel.permissions_for(member).read_messages:
                continue

            view = (
                RefreshTravelynx(user.discord_id, current_trips[-1])
                if data["reason"] != "checkout"
                else None
            )

            # check if we already have a message for this particular trip
            # edit it if it exists, otherwise create a new one and submit it into the database
            if message := DB.Message.find(zugid(data["status"]), userid, channel.id):
                msg = await message.fetch(bot)

                await msg.edit(
                    embeds=format_travelynx(bot, DB.DB, userid, current_trips),
                    view=view,
                )
            else:
                message = await channel.send(
                    embeds=format_travelynx(bot, DB.DB, userid, current_trips),
                    view=view,
                )
                DB.Message.write(user.discord_id, zugid(data["status"]), message)
                # shrink previous message to prevent clutter
                if len(current_trips) > 1 and (
                    prev_message := DB.Message.find(
                        user.discord_id, zugid(current_trips[-2]), channel.id
                    )
                ):
                    prev_msg = await prev_message.fetch(bot)
                    await prev_msg.edit(
                        embeds=format_travelynx(
                            bot,
                            DB.DB,
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
async def privacy(ia, level: typing.Optional[DB.Privacy]):
    "Query or change your current privacy settings on this server"

    def explain(level: typing.Optional[DB.Privacy]):
        desc = "This means that, on this server,\n"
        match level:
            case DB.Privacy.ME:
                desc += "- Only you can use the **/zug** command to share your current journey."
            case DB.Privacy.EVERYONE:
                desc += "- Everyone can use the **/zug** command to see your current journey."
            case DB.Privacy.LIVE:
                desc += "- Everyone can use the **/zug** command to see your current journey.\n"
                if live_channel := DB.Server.find(ia.guild.id).live_channel:
                    desc += f"- Live updates will posted into {bot.get_channel(live_channel).mention} with your entire journey."
                else:
                    desc += (
                        "- Live updates with your entire journey can be posted into a dedicated channel.\n"
                        "- Note: This server has not set up a live channel. No live updates will be posted until it is set up."
                    )
        desc += "\n- Note: If your checkin is set to **private visibility** on travelynx, this bot will not post it anywhere."
        return desc

    if level is None:
        level = DB.User.find(discord_id=ia.user.id).find_privacy_for(ia.guild.id)
        await ia.response.send_message(
            f"Your privacy level is set to **{level.name}**. {explain(level)}"
        )

    else:
        DB.User.find(discord_id=ia.user.id).set_privacy_for(ia.guild_id, level)
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

    user = DB.User.find(discord_id=member.id)
    if not user:
        await ia.response.send_message(
            embed=discord.Embed(
                title="Oops!",
                color=train_type_color["U1"],
                description=f"It looks like {member.mention} is not registered with the travelynx relay bot yet.\n"
                "If you want to fix this minor oversight, use **/register** today!",
            )
        )
        return

    if user.find_privacy_for(ia.guild.id) == DB.Privacy.ME and not member == ia.user:
        await ia.response.send_message(
            embed=discord.Embed().set_author(
                name=f"{member.name} ist gerade nicht unterwegs",
                icon_url=member.avatar.url,
            )
        )
        return

    async with ClientSession() as session:
        async with session.get(
            f"https://travelynx.de/api/v1/status/{user.token_status}"
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
                current_trips = [
                    trip.status for trip in DB.Trip.find_current_trips_for(member.id)
                ]

                await ia.response.send_message(
                    embeds=format_travelynx(bot, DB.DB, member.id, current_trips),
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
    first we check that we aren't already registered, then offer to proceed to step 1 with token modal
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Connect travelynx account",
        style=discord.ButtonStyle.green,
        custom_id="register_button:a",
    )
    async def doit(self, ia, _):
        "button to proceed to step 1"
        if DB.User.find(discord_id=ia.user.id):
            await ia.response.send_message(
                embed=discord.Embed(
                    title="Oops!",
                    color=train_type_color["U1"],
                    description="It looks like you're already registered. If you want to reset your tokens or need "
                    "any other assistance, please ask the bot operator.",
                ),
                ephemeral=True,
            )
            return

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
    register the user, then offer to proceed to step 2 to copy live feed/webhook credentials.
    """

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
            token = self.token.value.strip()
            if await is_token_valid(token):
                DB.User(
                    discord_id=ia.user.id,
                    token_status=token,
                    token_webhook=secrets.token_urlsafe(),
                    token_travel=None,
                ).write()
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
        token = DB.User.find(ia.user.id).token_webhook
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
        user = DB.User.find(discord_id=self.userid)
        async with ClientSession() as session:
            async with session.get(
                f"https://travelynx.de/api/v1/status/{user.token_status}"
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data["checkedIn"] and self.zugid == zugid(data):
                        handle_status_update(self.userid, "update", data)
                        current_trips = [
                            trip.status
                            for trip in DB.Trip.find_current_trips_for(self.userid)
                        ]
                        await ia.response.edit_message(
                            embeds=format_travelynx(
                                bot, DB.DB, self.userid, current_trips
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
