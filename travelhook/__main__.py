"contains our bot commands and the incoming webhook handler"
import asyncio
import base64
import itertools
import json
import secrets
import re
import shlex
import subprocess
import traceback
import typing
import urllib
from copy import deepcopy
from datetime import datetime, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, web
import discord
from discord.ext import commands
from haversine import haversine
import tomli
import tomli_w

from . import database as DB
from . import oebb_wr
from .format import (
    blanket_replace_train_type,
    emoji,
    format_travelynx,
    get_display,
    train_types_config,
    get_network,
)
from .helpers import (
    available_tzs,
    format_composition_element,
    format_time,
    generate_train_link,
    is_token_valid,
    is_import_token_valid,
    LineEmoji,
    not_registered_embed,
    train_type_color,
    trip_length,
    zugid,
    tz,
    random_id,
    parse_manual_time,
    fetch_headsign,
)

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)

if config["cts_token"]:
    config["cts_token"] = "Basic " + base64.b64encode(
        config["cts_token"].encode() + b":"
    ).decode("utf-8")

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


async def handle_status_update(userid, reason, status):
    """update trip data in the database, also starting a new journey if the last data
    we have is too old or distant for this to be a changeover"""

    user = DB.User.find(discord_id=userid)

    def is_new_journey(old, new):
        "determine if the user has merely changed into a new transport or if they have started another journey altogether"

        # don't drop the journey in case we receive a checkout after the new checkin
        if reason == "checkout" and status["train"]["id"] in [
            trip.status["train"]["id"]
            for trip in DB.Trip.find_current_trips_for(user.discord_id)
        ]:
            return False

        if old["train"]["id"] == new["train"]["id"]:
            return False

        if user.break_journey == DB.BreakMode.FORCE_BREAK:
            user.set_break_mode(DB.BreakMode.NATURAL)
            return True

        if user.break_journey == DB.BreakMode.FORCE_GLUE:
            user.set_break_mode(DB.BreakMode.NATURAL)
            return False

        if user.break_journey == DB.BreakMode.FORCE_GLUE_LATCH:
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

        return (
            change_distance > 2.0
            and not "travelhookfaked" in (new["train"]["id"] + old["train"]["id"])
        ) or change_duration > timedelta(hours=2)

    if (last_trip := DB.Trip.find_last_trip_for(userid)) and is_new_journey(
        last_trip.status, status
    ):
        user.do_break_journey()

    DB.Trip.upsert(userid, status)
    trip = DB.Trip.find(userid, zugid(status))
    trip.fetch_headsign()  # also runs fetch_hafas_data in the background
    trip.maybe_fix_1970()
    await trip.get_oebb_composition()
    trip.get_db_composition()
    await trip.get_ns_composition()
    await trip.get_vagonweb_composition()
    await trip.get_rtt_composition()


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

        async with user.get_lock():
            userid = user.discord_id
            data = await req.json()

            if data["reason"] == "ping" and not data["status"]["checkedIn"]:
                return web.Response(text="travelynx relay bot successfully connected!")

            if (
                not data["reason"] in ("update", "checkin", "ping", "checkout", "undo")
                or not data["status"]["toStation"]["name"]
            ):
                raise web.HTTPNoContent()

            # hopefully debug this mess eventually
            print(
                userid,
                data["reason"],
                get_display(bot, data["status"]),
                generate_train_link(data["status"]),
            )

            # when checkin is undone, delete its message
            if data["reason"] == "undo" and not data["status"]["checkedIn"]:
                last_trip = DB.Trip.find_last_trip_for(user.discord_id)
                if not last_trip.status["checkedIn"]:
                    print("sussy")
                    return web.Response(
                        text="Not unpublishing last checkin — you're already checked out. "
                        "In case this is intentional and you want to force deletion, undo your checkout, "
                        "save the journey comment once, and then finally undo your checkin. Sorry for the hassle."
                    )

                messages_to_delete = DB.Message.find_all(
                    user.discord_id, last_trip.journey_id
                )
                for message in messages_to_delete:
                    await message.delete(bot)
                last_trip.delete()

                if current_trips := DB.Trip.find_current_trips_for(user.discord_id):
                    for message in DB.Message.find_all(
                        user.discord_id, current_trips[-1].journey_id
                    ):
                        msg = await message.fetch(bot)
                        await msg.edit(
                            embed=format_travelynx(bot, userid, current_trips),
                            view=None,
                        )

                return web.Response(
                    text=f"Unpublished last checkin for {len(messages_to_delete)} channels"
                )

            # don't share completely private checkins, only unlisted and upwards
            if data["status"]["visibility"]["desc"] == "private":
                # just to make sure we don't have it lying around for some reason anyway
                if trip := DB.Trip.find(user.discord_id, zugid(data["status"])):
                    trip.delete()
                return web.Response(
                    text=f'Not publishing private {data["reason"]} in {data["status"]["train"]["type"]} {data["status"]["train"]["no"]}'
                )

            # update database to maintain trip data
            await handle_status_update(userid, data["reason"], data["status"])

            current_trips = DB.Trip.find_current_trips_for(user.discord_id)

            # get all channels that live updates get pushed to for this user
            channels = [bot.get_channel(cid) for cid in user.find_live_channel_ids()]
            for channel in channels:
                member = channel.guild.get_member(user.discord_id)
                # don't post if the user has left or can't see the live channel
                if not member or not channel.permissions_for(member).read_messages:
                    continue

                # check if we already have a message for this particular trip
                # edit it if it exists, otherwise create a new one and submit it into the database
                if message := DB.Message.find(
                    userid, zugid(data["status"]), channel.id
                ):
                    # if we get a checkout after another checkin has already been posted (manually)
                    # stop pretending we're at the end of the journey and link to the new ones
                    continue_link = None
                    if newer_message := DB.Message.find_newer_than(
                        userid, channel.id, message.message_id
                    ):
                        continue_link = (await newer_message.fetch(bot)).jump_url
                        current_trip_index = [
                            trip.journey_id for trip in current_trips
                        ].index(zugid(data["status"]))
                        current_trips = current_trips[0 : current_trip_index + 1]

                    msg = await message.fetch(bot)
                    await msg.edit(
                        embed=format_travelynx(
                            bot,
                            userid,
                            current_trips,
                            continue_link=continue_link,
                        ),
                        view=TripActionsView(current_trips[-1]),
                    )
                else:
                    embed = format_travelynx(bot, userid, current_trips)
                    if len(embed) > 4096:
                        # too long! oops! break the journey and readd our last checkin.
                        DB.User.find(discord_id=userid).do_break_journey()
                        await handle_status_update(
                            userid, data["reason"], data["status"]
                        )
                        current_trips = DB.Trip.find_current_trips_for(user.discord_id)
                        embed = format_travelynx(bot, userid, current_trips)

                    message = await channel.send(
                        embed=embed,
                        view=TripActionsView(current_trips[-1]),
                    )
                    DB.Message(
                        zugid(data["status"]), user.discord_id, channel.id, message.id
                    ).write()
                    # shrink previous message to prevent clutter
                    if len(current_trips) > 1 and (
                        prev_message := DB.Message.find(
                            user.discord_id, current_trips[-2].journey_id, channel.id
                        )
                    ):
                        prev_msg = await prev_message.fetch(bot)
                        await prev_msg.edit(
                            embed=format_travelynx(
                                bot,
                                userid,
                                current_trips[0:-1],
                                continue_link=message.jump_url,
                            ),
                            view=None,
                        )
            return web.Response(
                text=f'Successfully published {data["status"]["train"]["type"]} {data["status"]["train"]["no"]} {data["reason"]} to {len(channels)} channels'
            )

    async def unshortener(req):
        link = DB.Link.find_by_short(short_id=req.match_info["randid"])

        if not link:
            raise web.HTTPNotFound()

        raise web.HTTPFound(link.long_url)

    app = web.Application()
    app.router.add_post("/travelynx", handler)
    app.router.add_get("/s/{randid}", unshortener)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 6005)
    await site.start()


@bot.tree.command(guilds=servers)
@discord.app_commands.describe(
    member="the member whose status to query, defaults to current user"
)
async def zug(ia, member: typing.Optional[discord.Member]):
    "Get current travelynx status for yourself and others."
    if not member:
        member = ia.user

    user = DB.User.find(discord_id=member.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    if user.find_privacy_for(ia.guild.id) == DB.Privacy.ME and not member == ia.user:
        await ia.response.send_message(
            embed=discord.Embed().set_author(
                name=f"{member.name} ist gerade nicht unterwegs",
                icon_url=member.avatar.url,
            )
        )
        return

    await ia.response.defer()
    async with ClientSession() as session:
        async with session.get(
            f"{config['travelynx_instance']}/api/v1/status/{user.token_status}"
        ) as r:
            if r.status == 200:
                status = await r.json()
                if status["checkedIn"] and (status["visibility"]["desc"] != "private"):
                    await handle_status_update(member.id, "update", status)

            current_trips = DB.Trip.find_current_trips_for(member.id)
            if current_trips and (
                current_trips[-1].status["checkedIn"]
                or current_trips[-1].status["toStation"]["realTime"]
                > datetime.utcnow().timestamp()
            ):
                await ia.edit_original_response(
                    embed=format_travelynx(bot, member.id, current_trips),
                    view=TripActionsView(current_trips[-1]),
                )
            else:
                await ia.edit_original_response(
                    embed=discord.Embed().set_author(
                        name=f"{member.name} ist gerade nicht unterwegs",
                        icon_url=member.avatar.url,
                    )
                )


class TripActionsView(discord.ui.View):
    """is attached to embeds, allows users to manually update trip infos
    (for real trips) and copy the checkin"""

    disabled_refresh_button = discord.ui.Button(
        label="Update", style=discord.ButtonStyle.secondary, disabled=True
    )

    def __init__(self, trip):
        super().__init__()
        self.timeout = None
        self.trip = trip
        self.clear_items()

        if "travelhookfaked" in trip.journey_id:
            self.add_item(self.disabled_refresh_button)
            self.add_item(self.manualcopy)
        else:
            status = trip.get_unpatched_status()
            if status["checkedIn"]:
                self.add_item(self.refresh)
            else:
                self.add_item(self.disabled_refresh_button)

            url = f"{config['travelynx_instance']}/s/{status['fromStation']['uic']}?"
            if trip.status["backend"]["type"] == "IRIS-TTS":
                train = urllib.parse.quote(
                    f"{status['train']['type']} {status['train']['no']}"
                )
                url += f"train={train}"
            else:
                jid = urllib.parse.quote(
                    trip.status["train"]["hafasId"] or trip.status["train"]["id"]
                )
                url += (
                    f"hafas={trip.status['backend']['name']}&trip_id={jid}"
                    + f"&timestamp={trip.status['fromStation']['scheduledTime']}"
                )
            self.add_item(discord.ui.Button(label="Copy", url=url))

    @discord.ui.button(label="Update", style=discord.ButtonStyle.secondary)
    async def refresh(self, ia, _):
        """refresh real trips from travelynx api. this button is deleted from the view
        and replaced with a disabled button for fake checkins"""
        user = DB.User.find(discord_id=self.trip.user_id)
        await ia.response.defer()
        async with ClientSession() as session:
            async with session.get(
                f"{config['travelynx_instance']}/api/v1/status/{user.token_status}"
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data["checkedIn"] and self.trip.journey_id == zugid(data):
                        await handle_status_update(self.trip.user_id, "update", data)
                        self.trip.fetch_hafas_data(force=True)
                        await ia.edit_original_response(
                            embed=format_travelynx(
                                bot,
                                self.trip.user_id,
                                DB.Trip.find_current_trips_for(self.trip.user_id),
                            ),
                            view=self,
                        )
                    else:
                        await ia.followup.send(
                            "Die Fahrt ist bereits zu Ende.", ephemeral=True
                        )

    @discord.ui.button(label="Copy", style=discord.ButtonStyle.secondary)
    async def manualcopy(self, ia, _):
        """copy fake trips for yourself. this button is deleted from the view
        and replaced with a link to travelynx for real checkins."""
        user = DB.User.find(discord_id=ia.user.id)
        if not user:
            await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
            return

        # update, just in case we missed some edits maybe
        self.trip = DB.Trip.find(self.trip.user_id, self.trip.journey_id)
        departure = self.trip.status["fromStation"]["scheduledTime"]
        departure_delay = (
            departure - self.trip.status["fromStation"]["scheduledTime"]
        ) // 60
        arrival = self.trip.status["toStation"]["scheduledTime"]
        arrival_delay = (arrival - self.trip.status["toStation"]["scheduledTime"]) // 60
        await manualtrip.callback(
            ia,
            self.trip.status["fromStation"]["name"],
            f"{datetime.fromtimestamp(departure, tz=user.get_timezone()):%H:%M}",
            self.trip.status["toStation"]["name"],
            f"{datetime.fromtimestamp(arrival, tz=user.get_timezone()):%H:%M}",
            f"{self.trip.status['train']['type']} {self.trip.status['train']['line']}",
            self.trip.status["train"]["fakeheadsign"],
            departure_delay,
            arrival_delay,
            "",
            trip_length(self.trip),
            self.trip.status.get("composition"),
            True,
        )
        if original_patch := self.trip.status_patch:
            newpatch = original_patch.copy()
            if "comment" in newpatch:
                del newpatch["comment"]
                if not newpatch:
                    return
            try:
                await EditTripView(
                    DB.Trip.find_last_trip_for(ia.user.id), newpatch, quiet=True
                ).commit.callback(ia)
            except discord.errors.InteractionResponded:
                pass


configure = discord.app_commands.Group(
    name="configure", description="edit your settings with the relay bot"
)


@configure.command()
@discord.app_commands.describe(
    level="leave empty to query current level. set to ME to only allow you to use /zug, set to EVERYONE to allow everyone to use /zug and set to LIVE to activate the live feed.",
    quiet="(default) don't announce your privacy level to everyone in the channel",
)
async def privacy(ia, level: typing.Optional[DB.Privacy], quiet: bool = True):
    "Query or change your current privacy settings on this server."

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
                    if (
                        not ia.guild.get_channel(live_channel)
                        .permissions_for(ia.user)
                        .read_messages
                    ):
                        desc += (
                            "- This server has a live feed channel set up, but you can't see it. "
                            "The bot will not post live updates with your entire journey there."
                        )
                    else:
                        desc += f"- Live updates will posted into {bot.get_channel(live_channel).mention} with your entire journey."

                else:
                    desc += (
                        "- Live updates with your entire journey can be posted into a dedicated channel.\n"
                        "- Note: This server has not set up a live channel. No live updates will be posted until it is set up."
                    )
        desc += "\n- Note: If your checkin is set to **private visibility** on travelynx, this bot will not post it anywhere."
        return desc

    if user := DB.User.find(discord_id=ia.user.id):
        if level is None:
            level = user.find_privacy_for(ia.guild.id)
            await ia.response.send_message(
                f"Your privacy level is set to **{level.name}**. {explain(level)}",
                ephemeral=quiet,
            )
        else:
            user.set_privacy_for(ia.guild_id, level)
            await ia.response.send_message(
                f"Your privacy level has been set to **{level.name}**. {explain(level)}",
                ephemeral=quiet,
            )
    else:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)


@configure.command()
async def showtrainnumbers(ia, toggle: bool):
    "Configure whether you want your journeys to include train numbers"

    if user := DB.User.find(discord_id=ia.user.id):
        user.set_show_train_numbers(toggle)
        await ia.response.send_message(
            (
                "The relay bot will now show train numbers on all your journeys."
                if toggle
                else "The bot will no longer show train numbers on your journeys, except for long-distance trains with a line number."
            ),
            ephemeral=True,
        )
    else:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)


@configure.command()
@discord.app_commands.describe(
    token='the import token. create one on your travelynx user site under "API" in the row "Import"',
    disable="set to true if you don't want to upload your manual checkins anymore",
)
async def import_to_travelynx(
    ia, token: typing.Optional[str], disable: typing.Optional[bool] = False
):
    "Configure if the bot should import manual checkins (only with /checkin) to travelynx."
    if user := DB.User.find(discord_id=ia.user.id):
        if disable:
            user.set_import_token(None)
            await ia.response.send_message(
                "Deleted your import token. The **/checkin** command will no longer upload your trips to travelynx.",
                ephemeral=True,
            )
            return
        token = token.strip()
        if await is_import_token_valid(token):
            user.set_import_token(token)
            await ia.response.send_message(
                "Updated your import token. The **/checkin** command will now upload your trips to travelynx.",
                ephemeral=True,
            )
        else:
            await ia.response.send_message(
                "Could not update your import token because travelynx reports an error. Check if it's valid.",
                ephemeral=True,
            )
    else:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)


async def timezone_autocomplete(ia, current):
    return [
        Choice(name=s, value=s)
        for s in available_tzs
        if current.casefold() in s.casefold()
    ][:25]


@configure.command()
@discord.app_commands.autocomplete(tz=timezone_autocomplete)
async def timezone(ia, tz: str):
    "Configure the timezone your date inputs are interpreted as"

    if user := DB.User.find(discord_id=ia.user.id):
        if not tz in available_tzs:
            await ia.response.send_message(f"I don't know {tz}.", ephemeral=True)
            return
        user.write_timezone(tz)
        await ia.response.send_message(
            f"Your date and time inputs will now be interpreted as {tz}.",
            ephemeral=True,
        )
    else:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)


@configure.command()
async def suggestions(ia):
    "Edit autocomplete suggestions for your manual checkins."

    class EnterAutocompleteModal(
        discord.ui.Modal, title="Manual trip station autocompletes"
    ):
        suggestions_input = discord.ui.TextInput(
            label="One station per line, please",
            style=discord.TextStyle.paragraph,
            required=False,
        )

        def __init__(self, user):
            self.user = DB.User.find(user.id)
            self.suggestions_input.default = self.user.suggestions
            super().__init__()

        async def on_submit(self, ia):
            self.user.write_suggestions(self.suggestions_input.value)
            await ia.response.send_message(
                "Successfully updated your autocomplete suggestions!", ephemeral=True
            )

    await ia.response.send_modal(EnterAutocompleteModal(ia.user))


journey = discord.app_commands.Group(
    name="journey", description="edit and fix the journeys tracked by the relay bot."
)

Choice = discord.app_commands.Choice


@journey.command(name="break")
@discord.app_commands.choices(
    break_mode=[
        Choice(
            name="Natural — Transfer between nearby stops with less than two hours of waiting.",
            value=int(DB.BreakMode.NATURAL),
        ),
        Choice(
            name="Force Break — Never transfer. New checkins start a new journey.",
            value=int(DB.BreakMode.FORCE_BREAK),
        ),
        Choice(
            name="Force Glue — Always transfer. New checkins never start a new journey.",
            value=int(DB.BreakMode.FORCE_GLUE),
        ),
        Choice(
            name="Force Glue Until I Turn It Off — Always transfer. New checkins never start a new journey.",
            value=int(DB.BreakMode.FORCE_GLUE_LATCH),
        ),
    ]
)
async def _break(ia, break_mode: Choice[int]):
    'Control whether your next checkin should start a new journey ("break") or if it\'s just a transfer ("glue").'
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    break_mode = DB.BreakMode(break_mode.value)
    user.set_break_mode(break_mode)
    match break_mode:
        case DB.BreakMode.NATURAL:
            await ia.response.send_message(
                "Your next checkin will start a new journey if its and your last checkin's stations are more than "
                "two kilometers apart. It will also start a new journey if you wait more than two hours after "
                "your last checkin.",
                ephemeral=True,
            )
        case DB.BreakMode.FORCE_BREAK:
            await ia.response.send_message(
                "Your next checkin will start a new journey. "
                "After your next checkin, this setting will revert to *Natural*.",
                ephemeral=True,
            )
        case DB.BreakMode.FORCE_GLUE:
            await ia.response.send_message(
                "Your next checkin will **not** start a new journey. "
                "After your next checkin, this setting will revert to *Natural*.",
                ephemeral=True,
            )
        case DB.BreakMode.FORCE_GLUE_LATCH:
            await ia.response.send_message(
                "Your next checkin will **not** start a new journey. "
                "This setting will **not** revert to *Natural* with your next checkin.\n"
                f"> {LineEmoji.WARN} Even a new checkin in two weeks on the other side of the "
                "planet will still be added to your current journey. You will need to manually "
                "reset this setting to *Natural* using this command to bring the normal behavior back.",
                ephemeral=True,
            )


async def manual_station_autocomplete(ia, current):
    suggestions = []
    if user := DB.User.find(ia.user.id):
        trips = DB.Trip.find_current_trips_for(user.discord_id)
        for trip in trips:
            suggestions += [
                trip.status["toStation"]["name"],
                trip.status["fromStation"]["name"],
            ]
        suggestions += user.suggestions.split("\n")
        suggestions = [s for s in suggestions if current.casefold() in s.casefold()]

    return [Choice(name=s, value=s) for s in set(suggestions)]


async def train_types_autocomplete(ia, current):
    train_types = train_types_config["train_types"]
    train_types = set([tt.get("type") for tt in train_types if tt.get("type")])
    suggestions = sorted([s for s in train_types if current.casefold() in s.casefold()])

    return [Choice(name=s, value=s) for s in suggestions[:25]]


re_walk_distance = re.compile(
    r"(?P<type>walk |bike )(?P<number>\d+(?:.\d+)?)(?P<unit>k?m)"
)


@journey.command()
@discord.app_commands.describe(
    from_station="the name of the station you're departing from",
    departure="HH:MM departure according to the timetable",
    departure_delay="minutes of delay",
    to_station="the name of the station you will arrive at",
    arrival="HH:MM arrival according to the timetable",
    arrival_delay="minutes of delay",
    train="train type, line & number, like 'S 42', 'walk', 'plane LH3999', 'REX 3 #123'. see: /explain train_types",
)
@discord.app_commands.autocomplete(
    from_station=manual_station_autocomplete,
    to_station=manual_station_autocomplete,
    headsign=manual_station_autocomplete,
    train=train_types_autocomplete,
)
async def manualtrip(
    ia,
    from_station: str,
    departure: str,
    to_station: str,
    arrival: str,
    train: str,
    headsign: str,
    departure_delay: typing.Optional[int] = 0,
    arrival_delay: typing.Optional[int] = 0,
    comment: typing.Optional[str] = "",
    distance: typing.Optional[float] = None,
    composition: typing.Optional[str] = None,
    do_not_format_composition: bool = False,
    network: typing.Optional[str] = None,
):
    "Manually add a check-in not available on HAFAS/IRIS to your journey."
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    try:
        # if we call this from another command this would fail with
        # "interaction already responded to"
        await ia.response.defer(ephemeral=True)
    except:
        pass

    # transform pre-distance style usage into new format
    # by extracting the distance and setting it into the proper field
    if match := re_walk_distance.match(train):
        try:
            distance = float(match["number"])
            if match["unit"] == "m":
                distance /= 1000
            train = match["type"]
        except:
            pass

    train_type = train.split(" ")[0]
    train_line = train.split(" ")[1:]
    train_no = ""
    # if the last element in train_line starts with #, treat that as the train number
    if train_line and train_line[-1].startswith("#"):
        train_no = train_line[-1][1:]
        train_line = train_line[0:-1]
    train_line = " ".join(train_line)

    departure = parse_manual_time(departure, user.get_timezone())
    if (last_trip := DB.Trip.find_last_trip_for(user.discord_id)) and last_trip.status[
        "toStation"
    ]["realTime"] > int(departure.timestamp() + departure_delay * 60):
        last_arrival = format_time(
            last_trip.status["toStation"]["scheduledTime"],
            last_trip.status["toStation"]["realTime"],
            timezone=user.get_timezone(),
        )
        await ia.edit_original_response(
            content=f"At your last checkin, you arrived at {last_arrival}. "
            "Your journey will get messed up if you add check-ins out of chronological order. "
            "Please edit or undo your previous checkin first."
        )
        return

    arrival = parse_manual_time(arrival, user.get_timezone())
    if arrival < departure:
        arrival += timedelta(days=1)
    status = {
        "checkedIn": False,
        "backend": {"name": "manual", "type": "", "id": -1},
        "comment": comment or "",
        "actionTime": int(datetime.now(tz=tz).timestamp()),
        "fromStation": {
            "uic": 42,
            "ds100": None,
            "name": from_station,
            "latitude": 0.0,
            "longitude": 0.0,
            "scheduledTime": int(departure.timestamp()),
            "realTime": int(departure.timestamp()) + (departure_delay * 60),
        },
        "toStation": {
            "uic": 69,
            "ds100": None,
            "name": to_station,
            "latitude": 0.0,
            "longitude": 0.0,
            "scheduledTime": int(arrival.timestamp()),
            "realTime": int(arrival.timestamp()) + (arrival_delay * 60),
        },
        "intermediateStops": [],
        "train": {
            "fakeheadsign": headsign,
            "type": train_type,
            "line": train_line,
            "no": train_no,
            "id": "travelhookfaked" + random_id(),
            "hafasId": None,
        },
        "distance": distance,
        "visibility": {"desc": "public", "level": 100},
    }
    if do_not_format_composition:
        status["composition"] = composition
    elif composition:
        status["composition"] = ""
        composition = composition.split("+")
        status["composition"] = " + ".join(
            [format_composition_element(unit.strip()) for unit in composition]
        )
    if network:
        status["network"] = network
    webhook = {"reason": "checkout", "status": status}
    async with ClientSession() as session:
        async with session.post(
            "http://localhost:6005/travelynx",
            json=webhook,
            headers={"Authorization": f"Bearer {user.token_webhook}"},
        ) as r:
            await ia.edit_original_response(content=f"{r.status} {await r.text()}")


def render_patched_train(trip, patch):
    "helper method to render a preview of how a train will look with a different patch applied"
    status = DB.json_patch_dicts(patch, trip.get_unpatched_status())
    user_tz = DB.User.find(trip.user_id).get_timezone()
    display = get_display(bot, status)
    link = generate_train_link(status)
    departure = format_time(
        status["fromStation"]["scheduledTime"],
        status["fromStation"]["realTime"],
        timezone=user_tz,
    )
    arrival = format_time(
        status["toStation"]["scheduledTime"],
        status["toStation"]["realTime"],
        timezone=user_tz,
    )
    headsign = fetch_headsign(status)
    train_line = f"**{display['line']}**" if display["line"] else ""
    stations = f"\n{status['fromStation']['name']} {departure} → {status['toStation']['name']} {arrival}\n"
    if link:
        return f"{display['emoji']} {train_line} [» {headsign}]({link})" + stations
    else:
        return f"{display['emoji']} {train_line} » {headsign}" + stations


@journey.command()
async def undo(ia):
    "undo your last checkin in the bot's database. you must be checked out to do this. you will be asked to confirm the undo action."
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    trip = DB.Trip.find_last_trip_for(user.discord_id)
    if trip.status["checkedIn"]:
        await ia.response.send_message(
            "You're still checked in. Please undo this checkin on travelynx to avoid inconsistent data.",
            ephemeral=True,
        )
        return

    await ia.response.send_message(
        embed=discord.Embed(
            description=f"### You are about to undo the following checkin from {format_time(None, trip.from_time, True)}\n"
            f"{render_patched_train(trip, {})}\n"
            "The checkin will only be deleted from the bot's database. Please confirm deletion by clicking below.",
            color=train_type_color["SB"],
        ),
        ephemeral=True,
        view=UndoView(user, trip),
    )
    return


class UndoView(discord.ui.View):
    "confirmation button for the journey undo command"

    def __init__(self, user, trip):
        "we store the trip and user objects relevant for our undo process"
        super().__init__()
        self.user = user
        self.trip = trip

    @discord.ui.button(label="Yes, undo this trip.", style=discord.ButtonStyle.danger)
    async def doit(self, ia, _):
        "once clicked, send a mocked undo checkin request to the webhook"
        status = self.trip.get_unpatched_status()
        status["checkedIn"] = True
        DB.Trip.upsert(self.user.discord_id, status)
        async with ClientSession() as session:
            status["checkedIn"] = False
            async with session.post(
                "http://localhost:6005/travelynx",
                json={"reason": "undo", "status": status},
                headers={"Authorization": f"Bearer {self.user.token_webhook}"},
            ) as r:
                await ia.response.edit_message(
                    content=f"{r.status} {await r.text()}", embed=None, view=None
                )


@journey.command()
async def delay(ia, departure: typing.Optional[int], arrival: typing.Optional[int]):
    "quickly add a delay not reflected in HAFAS to your journey"
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    trip = DB.Trip.find_last_trip_for(user.discord_id)
    if not trip:
        await ia.response.send_message(
            "Sorry, but the bot doesn't have a trip saved for you currently.",
            ephemeral=True,
        )
        return

    await ia.response.defer()

    prepare_patch = {}
    if departure is not None:
        prepare_patch["fromStation"] = {
            "realTime": trip.status["fromStation"]["scheduledTime"] + departure * 60
        }

    if arrival is not None:
        prepare_patch["toStation"] = {
            "realTime": trip.status["toStation"]["scheduledTime"] + arrival * 60
        }
    trip.patch_patch(prepare_patch)

    trip = DB.Trip.find(trip.user_id, trip.journey_id)
    reason = "update" if trip.status["checkedIn"] else "checkout"
    async with ClientSession() as session:
        async with session.post(
            "http://localhost:6005/travelynx",
            json={"reason": reason, "status": trip.get_unpatched_status()},
            headers={"Authorization": f"Bearer {user.token_webhook}"},
        ) as r:
            if r.status == 200:
                display = get_display(bot, trip.status)
                link = generate_train_link(trip.status)
                headsign = trip.fetch_headsign()
                train_line = f"**{display['line']}**" if display["line"] else ""
                dep_delay = format_time(
                    trip.status["fromStation"]["scheduledTime"],
                    trip.status["fromStation"]["realTime"],
                    timezone=user.get_timezone(),
                )[8:-2]
                arr_delay = format_time(
                    trip.status["toStation"]["scheduledTime"],
                    trip.status["toStation"]["realTime"],
                    timezone=user.get_timezone(),
                )[8:-2]

                embed = discord.Embed(
                    description=f"{display['emoji']} {train_line} **» {headsign}** "
                    f"is delayed by **{dep_delay or '+0′'}/{arr_delay or '+0′'}**.",
                    color=train_type_color["SB"],
                ).set_author(
                    name=f"{ia.user.name} ist {'nicht ' if len(dep_delay+arr_delay) == 0 else ''}verspätet",
                    icon_url=ia.user.avatar.url,
                )

                server = DB.Server.find(ia.guild.id)
                if server.live_channel and (
                    msg := DB.Message.find(
                        trip.user_id, trip.journey_id, server.live_channel
                    )
                ):
                    embed.description += (
                        f"\n**current journey:** {(await msg.fetch(bot)).jump_url}"
                    )

                await ia.edit_original_response(content=None, embed=embed)
            else:
                await ia.edit_original_response(
                    content=f"{r.status} {await r.text()}",
                )


async def composition_autocomplete(ia, current):
    if (
        (user := DB.User.find(ia.user.id))
        and (trip := DB.Trip.find_last_trip_for(user.discord_id))
        and (network := get_network(trip.status))
    ):
        numbers = [int(s.strip()) for s in current.split("+") if s]
        composition_enriched = " + ".join(
            [f"{number} {DB.Tram.find(network, number) or ''}" for number in numbers]
        )
        return [
            Choice(name=current, value=current),
            Choice(name=composition_enriched, value=composition_enriched),
        ]

    return []


@journey.command()
@discord.app_commands.autocomplete(composition=composition_autocomplete)
async def composition(ia, composition: str, do_not_format: bool = False):
    "quickly add the rolling stock of your journey if it wasn't fetched automatically"
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    trip = DB.Trip.find_last_trip_for(user.discord_id)
    if not trip:
        await ia.response.send_message(
            "Sorry, but the bot doesn't have a trip saved for you currently.",
            ephemeral=True,
        )
        return

    await ia.response.defer(ephemeral=True)

    prepare_patch = {}
    if do_not_format:
        prepare_patch["composition"] = composition
    else:
        composition = composition.split("+")
        prepare_patch["composition"] = " + ".join(
            [format_composition_element(unit.strip()) for unit in composition]
        )

    newpatch = DB.json_patch_dicts(prepare_patch, trip.status_patch)
    await EditTripView(trip, newpatch).commit.callback(ia)


async def journey_autocomplete(ia, current):
    def train_name(trip, user):
        status = trip.status
        time = format_time(
            status["fromStation"]["scheduledTime"],
            status["fromStation"]["realTime"],
            timezone=user.get_timezone(),
        )[2:-2]
        headsign = trip.fetch_headsign()
        return f"{time} {status['train']['type']} {status['train']['line'] or ''} » {headsign}"

    if user := DB.User.find(ia.user.id):
        return [
            Choice(name=train_name(trip, user), value=trip.journey_id[-100:])
            for trip in DB.Trip.find_current_trips_for(user.discord_id)
        ][:24]


async def network_autocomplete(ia, current):
    networks = set(
        [tt["network"] for tt in train_types_config["train_types"] if "network" in tt]
    )
    networks = [
        Choice(
            name=f"[{network}] " + train_types_config["network_descriptions"][network],
            value=network,
        )
        for network in networks
        if current.casefold() in network.casefold()
        or current.casefold() in train_types_config["network_descriptions"][network]
    ]
    return sorted(networks, key=lambda c: c.name)[:24]


@journey.command()
@discord.app_commands.autocomplete(
    journey=journey_autocomplete,
    network=network_autocomplete,
    train=train_types_autocomplete,
)
async def edit(
    ia,
    journey: typing.Optional[str],
    from_station: typing.Optional[str],
    departure: typing.Optional[str],
    departure_delay: typing.Optional[int],
    to_station: typing.Optional[str],
    arrival: typing.Optional[str],
    arrival_delay: typing.Optional[int],
    train: typing.Optional[str],
    headsign: typing.Optional[str],
    comment: typing.Optional[str],
    distance: typing.Optional[float],
    composition: typing.Optional[str],
    do_not_format_composition: typing.Optional[bool],
    network: typing.Optional[str],
    operator: typing.Optional[str],
):
    "manually overwrite some data of a trip. you will be asked to confirm your changes."
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return

    trip = DB.Trip.find_last_trip_for(user.discord_id)
    if journey:
        trips = DB.Trip.find_current_trips_for(user.discord_id)
        trip = [trip for trip in trips if trip.journey_id.endswith(journey)][0]

    if not trip:
        await ia.response.send_message(
            "Sorry, but the bot doesn't have a trip saved for you currently.",
            ephemeral=True,
        )
        return

    await ia.response.defer(ephemeral=True)
    prepare_patch = {}

    if from_station or departure or departure_delay:
        prepare_patch["fromStation"] = {"name": from_station}
        if departure:
            departure = parse_manual_time(departure, user.get_timezone())
            prepare_patch["fromStation"]["scheduledTime"] = int(departure.timestamp())
            departure_delay = departure_delay or 0
        else:
            departure = datetime.fromtimestamp(
                trip.status["fromStation"]["scheduledTime"], tz=user.get_timezone()
            )

        if departure_delay is not None:
            prepare_patch["fromStation"]["realTime"] = int(departure.timestamp()) + (
                (departure_delay or 0) * 60
            )

    if to_station or arrival or arrival_delay:
        prepare_patch["toStation"] = {"name": to_station}
        if arrival:
            arrival = parse_manual_time(arrival, user.get_timezone())
            prepare_patch["toStation"]["scheduledTime"] = int(arrival.timestamp())
            arrival_delay = arrival_delay or 0
        else:
            arrival = datetime.fromtimestamp(
                trip.status["toStation"]["scheduledTime"], tz=user.get_timezone()
            )

        if arrival_delay is not None:
            prepare_patch["toStation"]["realTime"] = int(arrival.timestamp()) + (
                (arrival_delay or 0) * 60
            )

    if train or headsign:
        prepare_patch["train"] = {
            "fakeheadsign": headsign,
        }
        if train:
            train_type = train.split(" ")[0]
            train_line = train.split(" ")[1:]
            train_no = ""
            # if the last element in train_line starts with #, treat that as the train number
            if train_line and train_line[-1].startswith("#"):
                train_no = train_line[-1][1:]
                train_line = train_line[0:-1]
            train_line = " ".join(train_line)

            prepare_patch["train"]["type"] = train_type
            prepare_patch["train"]["line"] = train_line
            if train_no:
                prepare_patch["train"]["no"] = train_no

    if comment:
        prepare_patch["comment"] = comment
    if distance:
        prepare_patch["distance"] = distance
    if network:
        prepare_patch["network"] = network
    if operator:
        prepare_patch["operator"] = operator

    if do_not_format_composition:
        prepare_patch["composition"] = composition
    elif composition:
        prepare_patch["composition"] = ""
        composition = composition.split("+")
        prepare_patch["composition"] = " + ".join(
            [format_composition_element(unit.strip()) for unit in composition]
        )

    newpatch = DB.json_patch_dicts(prepare_patch, trip.status_patch)
    newpatched_status = DB.json_patch_dicts(newpatch, trip.travelynx_status)

    await ia.edit_original_response(
        embed=discord.Embed(
            description=f"### You are about to edit the following checkin from {format_time(None, trip.from_time, True)}\n"
            "Current state:\n"
            f"{render_patched_train(trip, trip.status_patch)}\n"
            "With your changes:\n"
            f"{render_patched_train(trip, newpatch)}\n"
            "You can immediately apply these changes or double-check and make further edits with the manual editor "
            "using [TOML](https://toml.io), e.g.:"
            '```toml\nfromStation.name = "Nürnberg Ziegelstein"\ntrain = { type = "U", line = "11" }\n```\n'
            "For available fields, see [travelynx's API documentation]("
            + config["travelynx_instance"]
            + "/api).",
            color=train_type_color["SB"],
        ),
        view=EditTripView(trip, newpatch),
    )


class EditTripView(discord.ui.View):
    "provide a button to edit the trip status patch"

    def __init__(self, trip, newpatch, quiet=False):
        self.trip = trip
        self.newpatch = newpatch
        self.quiet = quiet
        self.modal = self.EnterStatusPatchModal(self, self.trip, self.newpatch)
        super().__init__()

    def attachnewmodal(self, newpatch):
        """so for some reason we can't reuse the editor modal, so we create a new
        one with the same data every time the editor is closed"""
        self.newpatch = newpatch
        self.modal = self.EnterStatusPatchModal(self, self.trip, self.newpatch)

    @discord.ui.button(label="Commit my edits now.", style=discord.ButtonStyle.green)
    async def commit(self, ia, _):
        "write newpatch into the database and issue a mocked update webhook"
        self.trip.write_patch(self.newpatch)
        self.trip = DB.Trip.find(
            self.trip.user_id, self.trip.journey_id
        )  # update, just in case
        reason = "update" if self.trip.status["checkedIn"] else "checkout"
        async with ClientSession() as session:
            async with session.post(
                "http://localhost:6005/travelynx",
                json={"reason": reason, "status": self.trip.get_unpatched_status()},
                headers={
                    "Authorization": f"Bearer {DB.User.find(self.trip.user_id).token_webhook}"
                },
            ) as r:
                if self.quiet:
                    return
                if ia.response.is_done():
                    await ia.edit_original_response(
                        content=f"{r.status} {await r.text()}", embed=None, view=None
                    )
                else:
                    await ia.response.edit_message(
                        content=f"{r.status} {await r.text()}", embed=None, view=None
                    )

    @discord.ui.button(
        label="Open the manual editor instead.", style=discord.ButtonStyle.grey
    )
    async def edit(self, ia, _):
        "open the editor, reshow the changes and wait for confirmation"
        await ia.response.send_modal(self.modal)

    class EnterStatusPatchModal(
        discord.ui.Modal, title="Dingenskirchen® Advanced Train Editor™"
    ):
        patch_input = discord.ui.TextInput(
            label="Status edits (TOML)",
            style=discord.TextStyle.paragraph,
            required=False,
        )

        def __init__(self, parent, trip, newpatch):
            self.parent = parent
            self.trip = trip
            self.newpatch = newpatch
            self.patch_input.default = tomli_w.dumps(newpatch)  # wow much efficiency
            super().__init__()

        async def on_submit(self, ia):
            self.newpatch = tomli.loads(self.patch_input.value)
            self.patch_input.default = tomli_w.dumps(self.newpatch)
            self.parent.attachnewmodal(self.newpatch)
            await ia.response.edit_message(
                embed=discord.Embed(
                    description="Current state:\n"
                    f"{render_patched_train(self.trip, self.trip.status_patch)}\n"
                    "With your changes:\n"
                    f"{render_patched_train(self.trip, self.newpatch)}\n"
                    "Click commit to confirm or edit again.",
                    color=train_type_color["SB"],
                )
            )


bot.tree.add_command(configure, guilds=servers)
bot.tree.add_command(journey, guilds=servers)


@bot.tree.command(guilds=servers)
@discord.app_commands.rename(from_station="from", to_station="to")
@discord.app_commands.autocomplete(
    from_station=manual_station_autocomplete, to_station=manual_station_autocomplete
)
async def walk(
    ia,
    from_station: str,
    to_station: str,
    departure: str,
    arrival: str,
    name: typing.Optional[str],
    actually_bike_instead: typing.Optional[bool],
    comment: typing.Optional[str],
    distance: typing.Optional[float],
):
    "do a manual trip walking, see /journey manualtrip"
    train = f"walk {name or ''}"
    if actually_bike_instead:
        train = f"bike {name or ''}"
    await manualtrip.callback(
        ia,
        from_station,
        departure,
        to_station,
        arrival,
        train,
        to_station,
        0,
        0,
        comment,
        distance,
    )


manual = discord.app_commands.Group(
    name="explain", description="the relay bot's manual pages"
)


def explain_display(bot, tt, for_variants=False):
    def has_variants(type):
        return any(
            "network" in tt and tt.get("type") == type
            for tt in train_types_config["train_types"]
        )

    type = tt.get("type", "…")
    line = tt.get("line", "")
    line_startswith = tt.get("line_startswith", "")
    if line:
        type += f" {line}"
    elif line_startswith:
        type += f" {line_startswith}…"

    variant_indicator = ""
    if has_variants(tt.get("type", "")) and not (line or line_startswith):
        variant_indicator = " ✱"

    if for_variants:
        return f"`{type or '…'}` {emoji(bot, tt)}"
    else:
        return f"`{type:>6}` {emoji(bot, tt)}{variant_indicator}"


@manual.command()
async def train_types(ia):
    "list the train types the relay bot knows about"
    train_types = train_types_config["train_types"]
    embed = discord.Embed(
        color=discord.Color.from_str("#2e2e7d"),
        title="manual: train types",
        description=f"the relay bot currently knows **{len(set([tt.get('type') for tt in train_types]))} "
        "train types**. when you use a supported type of transport, the bot will display a hand-crafted special icon for it!\n"
        "train types marked with ✱ have additional **display variants** depending on the transit network your journey "
        "is in. you can find out more about the supported networks by using **/explain train_variants**.",
    ).add_field(
        name="type aliases",
        value="\n".join(
            [f"`{k:>6}` **→** `{v:<6}`" for k, v in blanket_replace_train_type.items()]
        ),
    )
    sort_by_class = lambda tt: tt.get("class", "other")
    networkless_train_types = sorted(
        [tt for tt in train_types if "type" in tt and not "network" in tt],
        key=sort_by_class,
    )
    for key, tts in itertools.groupby(networkless_train_types, sort_by_class):
        fallback_description = f"\n`     …` {emoji(bot, {'emoji':'sbbzug'})}"
        embed = embed.add_field(
            name=key,
            value="\n".join([explain_display(bot, tt) for tt in tts])
            + (fallback_description if key == "special" else ""),
        )

    await ia.response.send_message(embed=embed)


@manual.command()
async def train_variants(ia):
    "list the train display variants for transit networks the bot knows about"

    embeds = [
        discord.Embed(
            color=discord.Color.from_str("#2e2e7d"),
            title="manual: train display variants",
            description="the relay bot supports 'native' display variants for a number of transit "
            "networks. when you check in with travelynx or **/cts**, the bot will automatically "
            "try to guess the correct network. if you're checking in manually or the bot makes a "
            "mistake, you can correct it with **/journey edit network:**",
        ),
        discord.Embed(color=discord.Color.from_str("#2e2e7d"), description=""),
    ]
    sortkey = lambda tt: tt.get("network", "")
    train_types = sorted(train_types_config["train_types"], key=sortkey)
    for network, types in itertools.groupby(train_types, sortkey):
        description = ""
        if not network:
            continue
        types = list(types)
        if len(types) > 1 and all(tt.get("type") == "U" for tt in types):
            description = (
                f"\n**`{network}` {train_types_config['network_descriptions'][network]}**\n> "
                f"`U {types[0]['line']}-{types[-1]['line']}` "
                + (" | ".join([emoji(bot, tt) for tt in types]))
            )
        elif network in ("CTS", "RNV", "KVV") and len(types) > 1:
            description = f"\n**`{network}` {train_types_config['network_descriptions'][network]}**\n"
            if buses := [type for type in types if type.get("type") == "Bus"]:
                emojis = [
                    emoji(bot, tt) if i == 0 else "<" + (emoji(bot, tt).split("><")[1])
                    for i, tt in enumerate(buses)
                ]
                description += f"> `Bus {buses[0]['line']}-{buses[-1]['line']}` " + (
                    " | ".join(emojis)
                )
                if len(types) != len(buses):
                    description += "\n"
            if trams := [
                type
                for type in types
                if type.get("type") == "STR"
                and not type.get("line", "").startswith("NL")
            ]:
                emojis = [
                    emoji(bot, tt) if i == 0 else "<" + (emoji(bot, tt).split("><")[1])
                    for i, tt in enumerate(trams)
                ]
                description += f"> `STR {trams[0]['line']}-{trams[-1]['line']}` " + (
                    " | ".join(emojis)
                )
            if tramtrains := [type for type in types if type.get("type") == "S"]:
                emojis = [
                    emoji(bot, tt) if i == 0 else "<" + (emoji(bot, tt).split("><")[1])
                    for i, tt in enumerate(tramtrains)
                ]
                description += (
                    f"\n> `S {tramtrains[0]['line']}-{tramtrains[-1]['line']}` "
                    + (" | ".join(emojis))
                )
        elif network == "UK":
            description = f"\n**`{network}` {train_types_config['network_descriptions'][network]}**\n> `Underground` "
            tube = [tt for tt in types if not (tt.get("type") or tt.get("fallback"))]
            description += " | ".join(emoji(bot, tt) for tt in tube)
            description += f"\n> " + " | ".join(
                [
                    explain_display(bot, tt, for_variants=True)
                    for tt in types
                    if tt.get("type") or tt.get("fallback")
                ]
            )
        else:
            description = (
                f"\n**`{network}` {train_types_config['network_descriptions'][network]}**\n> "
                + " | ".join(
                    [explain_display(bot, tt, for_variants=True) for tt in types]
                )
            )
        if len(embeds[-1]) + len(description) > 4096:
            embeds.append(
                discord.Embed(color=discord.Color.from_str("#2e2e7d"), description="")
            )
        embeds[-1].description += description
    await ia.response.send_message(embeds=embeds)


bot.tree.add_command(manual, guilds=servers)


@bot.tree.command(guilds=servers)
async def register(ia):
    "Register with the travelynx relay bot and share your journeys today!"
    await ia.response.send_message(
        embed=discord.Embed(
            title="Registering with the travelynx relay bot",
            color=train_type_color["SB"],
            description="Thanks for your interest! Using this bot, you can share your public transport journeys "
            "in and around Germany (or in fact, any journey around the world, using the bot's manual checkin feature) "
            "with your friends and enemies on Discord.\nTo use it, you first need to sign up for **[travelynx]("
            + config["travelynx_instance"]
            + ")**"
            " to be able to check in into trains, trams, buses and so on. Then you can connect this bot to "
            "your travelynx account.\nFinally, for every server you can decide if *only you* want to share "
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
        custom_id=config["register_button_id"],
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
                "To do this, head over to the [**travelynx Account page**]("
                + config["travelynx_instance"]
                + "/account) "
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
                    break_journey=DB.BreakMode.NATURAL,
                    suggestions="",
                    show_train_numbers=False,
                    timezone="Europe/Berlin",
                ).write()
                await ia.response.edit_message(
                    embed=discord.Embed(
                        title="Step 2/3: Connect Live Feed (optional)",
                        color=train_type_color["SB"],
                        description="Great! You've successfully connected your status token to the relay bot. "
                        "You now use **/zug** for yourself and configure if others can use it with **/configure privacy**.\n"
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
                        "To do this, head over to the [**Account page**]("
                        + config["travelynx_instance"]
                        + "/account) "
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
                description="Congratulations! You can now use **/zug** and **/configure privacy** to share your logged "
                "journeys on Discord.\n\nWith the live feed enabled on a server, once your server admins have set up a "
                "live channel  *that you can see yourself*, the relay bot will automatically post non-private "
                "checkins and try to keep your journey up to date. To connect travelynx's update webhook "
                "with the relay bot, you need to head to the [**Account » Webhook page**]("
                + config["travelynx_instance"]
                + "/account/hooks), "
                "check «Aktiv» and enter the following values: \n\n"
                f"**URL**\n```{config['webhook_url']}```\n"
                f"**Token**\n```{token}```\n\n"
                "Once you've done that, save the webhook settings, and you should be able to read "
                "«travelynx relay bot successfully connected!» in the server response. If that doesn't happen, "
                "bother the bot operator about it.\nIf you changed your mind and don't want to connect right now, "
                "bother the bot operator about it once you've decided otherwise again. Until you copy in the settings, "
                "no live connection will be made.\n\n"
                "**Note:** Once you've set up the live feed with this, you also **need to enable it** for every server. "
                "To do this, run **/configure privacy LIVE** on the server you want to enable it for. To enable it on this server, "
                "you can also click the button below now.",
            ).set_image(url="https://i.imgur.com/LhsH8Nt.png"),
            view=RegisterTravelynxEnableLiveFeed(),
        )

    @discord.ui.button(label="No, I don't want that.", style=discord.ButtonStyle.grey)
    async def dontit(self, ia, _):
        "just wish them a nice day"
        await ia.response.edit_message(
            embed=discord.Embed(
                title="Step 3/3: Done!",
                color=train_type_color["S"],
                description="Congratulations! You can now use **/zug** and **/configure privacy** to share your logged journeys on Discord.",
            ),
            view=None,
        )


class RegisterTravelynxEnableLiveFeed(discord.ui.View):
    "after registration, offer to change the privacy settings for the current server"

    @discord.ui.button(
        label="Enable live feed for this server", style=discord.ButtonStyle.red
    )
    async def doit(self, ia, _):
        await privacy.callback(ia, DB.Privacy.LIVE, True)


class CTSView(discord.ui.View):
    """attached to the /cts response, select transport then target,
    then fire off a manual checkin
    """

    @discord.ui.select(placeholder="select transport to check into")
    async def select_transport(self, ia, select):
        await ia.response.defer()
        self.select_transport.placeholder = [
            option.label
            for option in self.select_transport.options
            if str(option.value) == select.values[0]
        ][0]
        self.selected_transport = self.transports[int(select.values[0])]
        self.remove_item(self.select_destination)
        await self.add_select_destination()
        await ia.edit_original_response(view=self)

    async def add_select_transport(self):
        self.transports = await cts_stationboard(
            self.logicalstopcode, self.request_time
        )
        if self.transports is None:
            # reply 503 -- timeout. let's try again
            await asyncio.sleep(5)
            self.transports = await cts_stationboard(
                self.logicalstopcode, self.request_time
            )
        if not self.transports:
            print(f"cts: no transports at {self.logicalstopcode} {self.request_time}")
            self.select_transport.placeholder = "no transports found"
            self.select_transport.options = [discord.SelectOption(label="-", value="0")]
            self.select_transport.disabled = True
        else:
            self.select_transport.options = [
                discord.SelectOption(
                    label=(
                        f"{format_time(trans['dep'], trans['dep'])} {trans['type']} "
                        f"{trans['line']} » {trans['headsign']}"
                    ).replace("**", ""),
                    value=i,
                )
                for (i, trans) in enumerate(self.transports)
            ][:25]
        self.add_item(self.select_transport)

    @discord.ui.select(placeholder="select destination")
    async def select_destination(self, ia, select):
        await ia.response.defer()
        destination_index = int(select.values[0][1:])
        self.selected_destination = self.stops_after[destination_index]
        self.select_destination.placeholder = [
            option.label
            for option in self.select_destination.options
            if str(option.value) == select.values[0]
        ][0]
        departure = datetime.fromtimestamp(self.selected_transport["dep"], tz=self.tz)
        arrival = self.selected_destination["ExpectedArrivalTime"]
        self.select_transport.disabled = True
        self.select_destination.disabled = True
        await ia.edit_original_response(view=self)
        await manualtrip.callback(
            ia,
            self.selected_transport["stop_name"],
            departure.isoformat(),
            self.selected_destination["StopPointName"],
            arrival.isoformat(),
            f"{self.selected_transport['type']} {self.selected_transport['line']}",
            self.selected_transport["headsign"],
            0,
            0,
            "",
            0,
        )
        distance = 0
        if self.stop_geo:
            coords = (self.stop_geo.get("latitude"), self.stop_geo.get("longitude"))
            for i, stop in enumerate(self.stops_after):
                if not stop.get("latitude"):
                    distance = None
                    break
                if i > destination_index:
                    break
                newcoords = (stop["latitude"], stop["longitude"])
                distance += haversine(coords, newcoords)
                coords = newcoords
        else:
            distance = None
        try:
            await EditTripView(
                DB.Trip.find_last_trip_for(ia.user.id),
                {
                    "operator": "CTS",
                    "distance": distance,
                    "fromStation": {
                        "latitude": self.stop_geo.get("latitude"),
                        "longitude": self.stop_geo.get("longitude"),
                    },
                    "toStation": {
                        "latitude": self.selected_destination.get("latitude"),
                        "longitude": self.selected_destination.get("longitude"),
                    },
                },
                quiet=True,
            ).commit.callback(ia)
        except discord.errors.InteractionResponded:
            pass

    async def add_select_destination(self):
        self.stops_after = await cts_journey(self.selected_transport)
        if self.stops_after is None:
            # reply 503 -- temporary timeout, let's try again
            await asyncio.sleep(5)
            self.stops_after = await cts_journey(self.selected_transport)

        if not self.stops_after:
            print(f"cts: no route found for {self.selected_transport}")
            self.select_destination.placeholder = "no route found"
            self.select_destination.options = [
                discord.SelectOption(label="-", value="0")
            ]
            self.select_destination.disabled = True
        else:
            # TODO add a second selector for trips with more stops
            for i, stop in enumerate(self.stops_after[:25]):
                if i > 24:
                    break
                timestamp = stop["ExpectedArrivalTime"].timestamp()
                self.select_destination.options.append(
                    discord.SelectOption(
                        label=f"({format_time(timestamp, timestamp)[2:-2]}) {stop['StopPointName']}",
                        value=f"d{i}",
                    )
                )
        self.add_item(self.select_destination)

    def __init__(self, ia, stop, request_time, timezone):
        super().__init__()
        self.remove_item(self.select_transport)
        self.remove_item(self.select_destination)
        self.logicalstopcode = stop
        self.stop_geo = {}
        if db_stop := DB.CTSStop.find_by_logicalstopcode(stop):
            self.stop_geo = {
                "latitude": db_stop.latitude,
                "longitude": db_stop.longitude,
            }
        self.request_time = parse_manual_time(request_time, timezone)
        self.tz = timezone


shitty_cts_lock = asyncio.Lock()
shitty_cts_cache = {}


def cleanup_cache():
    global shitty_cts_cache
    now = datetime.now(dt_tz.utc)
    to_delete = []
    for k, v in shitty_cts_cache.items():
        if v[0] < now:
            to_delete.append(k)
    for k in to_delete:
        del shitty_cts_cache[k]


async def cts_stationboard(logicalstopcode, request_time):
    global shitty_cts_lock, shitty_cts_cache
    transports = []
    sb_params = {
        "MonitoringRef": logicalstopcode,
        "VehicleMode": "undefined",
        "PreviewInterval": "PT60M",
        "StartTime": request_time.isoformat(),
        "MaximumStopVisits": "5",
    }
    sb_headers = {"Authorization": config["cts_token"]}
    async with shitty_cts_lock as lock:
        cleanup_cache()
        resp = {}
        if str(sb_params) in shitty_cts_cache:
            resp = deepcopy(shitty_cts_cache[str(sb_params)][1])
        else:
            async with ClientSession() as session:
                async with session.get(
                    "https://api.cts-strasbourg.eu/v1/siri/2.0/stop-monitoring",
                    params=sb_params,
                    headers=sb_headers,
                ) as r:
                    if r.status == 503:
                        return None
                    elif r.status != 200:
                        print(f"cts stationboard returned {r.status}: {await r.text()}")
                        return []
                    try:
                        resp = await r.json()
                        resp_validuntil = datetime.fromisoformat(
                            resp["ServiceDelivery"]["StopMonitoringDelivery"][0][
                                "ValidUntil"
                            ]
                        )
                        shitty_cts_cache[str(sb_params)] = (
                            resp_validuntil,
                            deepcopy(resp),
                        )
                    except:  # pylint: disable=bare-except
                        print("error while decoding:")
                        traceback.print_exc()
                        print(await r.text())

        if (
            not "MonitoredStopVisit"
            in resp["ServiceDelivery"]["StopMonitoringDelivery"][0]
        ):
            return []
        for stop_visit in resp["ServiceDelivery"]["StopMonitoringDelivery"][0][
            "MonitoredStopVisit"
        ]:
            mvj = stop_visit["MonitoredVehicleJourney"]
            dep = datetime.fromisoformat(mvj["MonitoredCall"]["ExpectedDepartureTime"])
            dep = dep - timedelta(seconds=dep.second, microseconds=dep.microsecond)
            trans = {
                "line": mvj["PublishedLineName"],
                "line_ref": mvj["LineRef"],
                "headsign": mvj["DestinationName"],
                "direction_ref": mvj["DirectionRef"],
                "stop_name": mvj["MonitoredCall"]["StopPointName"],
                "dep": dep.timestamp(),
                "journey_ref": mvj["FramedVehicleJourneyRef"][
                    "DatedVehicleJourneySAERef"
                ],
                "stop_comparison": (
                    stop_visit["StopCode"],
                    mvj["MonitoredCall"]["ExpectedDepartureTime"],
                ),
            }
            if trans["line"] in ("A", "B", "C", "D", "E", "F"):
                trans["type"] = "Tram"
            else:
                trans["type"] = "Bus"
            transports.append(trans)

        return transports


async def cts_journey(selected_transport):
    global shitty_cts_cache, shitty_cts_lock
    j_params = {
        "LineRef": selected_transport["line_ref"],
        "DirectionRef": selected_transport["direction_ref"],
    }
    j_headers = {"Authorization": config["cts_token"]}
    async with shitty_cts_lock as lock:
        cleanup_cache()
        resp = {}
        if str(j_params) in shitty_cts_cache:
            resp = deepcopy(shitty_cts_cache[str(j_params)][1])
        else:
            async with ClientSession() as session:
                async with session.get(
                    "https://api.cts-strasbourg.eu/v1/siri/2.0/estimated-timetable",
                    params=j_params,
                    headers=j_headers,
                ) as r:
                    if r.status == 503:
                        return None
                    elif r.status != 200:
                        print(f"cts timetable returned {r.status}: {await r.text()}")
                        return []
                    try:
                        resp = await r.json()
                        resp_validuntil = datetime.fromisoformat(
                            resp["ServiceDelivery"]["EstimatedTimetableDelivery"][0][
                                "ValidUntil"
                            ]
                        )
                        shitty_cts_cache[str(j_params)] = (
                            resp_validuntil,
                            deepcopy(resp),
                        )
                    except:  # pylint: disable=bare-except
                        print("error while decoding:")
                        traceback.print_exc()
                        print(await r.text())

        journeys = resp["ServiceDelivery"]["EstimatedTimetableDelivery"][0][
            "EstimatedJourneyVersionFrame"
        ][0]["EstimatedVehicleJourney"]
        journey = [
            journey
            for journey in journeys
            if journey["FramedVehicleJourneyRef"]["DatedVehicleJourneySAERef"]
            == selected_transport["journey_ref"]
        ]
        if not journey:
            print(f"cts: didn't find {selected_transport}")
            return None
        else:
            journey = journey[0]
        calls = journey["EstimatedCalls"]
        calls_after = []
        after = False
        for call in calls:
            if call["StopPointRef"] == selected_transport["stop_comparison"][0]:
                after = True
                continue
            if after:
                call["ExpectedArrivalTime"] = datetime.fromisoformat(
                    call["ExpectedArrivalTime"]
                )
                call["ExpectedArrivalTime"] = call["ExpectedArrivalTime"] - timedelta(
                    seconds=call["ExpectedArrivalTime"].second,
                    microseconds=call["ExpectedArrivalTime"].microsecond,
                )
                # logical stop code: stopref without the last letter (the "platform identifier")
                call["LogicalStopCode"] = int(call["StopPointRef"][:-1])
                db_stop = DB.CTSStop.find_by_logicalstopcode(call["LogicalStopCode"])
                if db_stop:
                    call["latitude"] = db_stop.latitude
                    call["longitude"] = db_stop.longitude
                calls_after.append(call)

        return calls_after


async def cts_station_autocomplete(ia, current):
    all_stops = DB.CTSStop.find_all()
    suggestions = [s for s in all_stops if current.casefold() in s.name.casefold()]

    return [Choice(name=s.name, value=str(s.logicalstopcode)) for s in suggestions][:25]


@bot.tree.command(guilds=servers)
@discord.app_commands.autocomplete(stop=cts_station_autocomplete)
async def cts(
    ia,
    stop: str,
    request_time: typing.Optional[str],
):
    "check into a transit trip in strasbourg"
    user = DB.User.find(discord_id=ia.user.id)
    if not user:
        await ia.response.send_message(embed=not_registered_embed, ephemeral=True)
        return
    if not request_time:
        request_time = datetime.now(tz=tz)
        request_time = request_time - timedelta(
            minutes=5,
            seconds=request_time.second,
            microseconds=request_time.microsecond,
        )
        request_time = request_time.isoformat()
    await ia.response.defer(ephemeral=True)
    view = CTSView(
        ia,
        stop,
        request_time,
        user.get_timezone(),
    )
    await view.add_select_transport()
    cts_name = DB.CTSStop.find_by_logicalstopcode(stop)
    if cts_name:
        cts_name = cts_name.name
    await ia.edit_original_response(
        content=f"### CTS manual check-in at _{cts_name or '?'}_",
        view=view,
    )


def main():
    "the function."
    bot.run(config["token"])


if __name__ == "__main__":
    main()
