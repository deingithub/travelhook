from datetime import datetime
import json
import typing
import sqlite3

from aiohttp import ClientSession, web
import discord
from discord.ext import commands
from zoneinfo import ZoneInfo

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)

servers = [discord.Object(id=i) for i in config["servers"]]
tz = ZoneInfo("Europe/Berlin")


def zugid(data):
    return str(data["fromStation"]["scheduledTime"]) + data["train"]["no"]


async def receive(bot):
    async def handler(req):
        userid = [
            int(uid)
            for uid, u in config["users"].items()
            if u["bearer"] == req.headers["authorization"].removeprefix("Bearer ")
        ][0]
        data = await req.json()

        if (
            not data["reason"] in ("update", "checkin", "ping")
            or not data["status"]["toStation"]["name"]
        ):
            raise web.HTTPOk()

        channels = [config["channel"]]
        if c := config["users"][str(userid)].get("channel"):
            channels.append(c)

        for channel in channels:
            await bot.get_channel(channel).send(
                embed=format_travelynx(bot, userid, data["status"]),
                view=RefreshTravelynx(userid, data["status"]),
            )

        return web.Response(text="")

    app = web.Application()
    app.router.add_post("/travelynx", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 6005)
    await site.start()


train_type_emoji = {
    "Bus": "<:Bus:1143105600121741462>",
    "EC": "<:EC:1102209838307627082>",
    "Fähre": "<:Faehre:1143105659827658783>",
    "IC": "<:IC:1102209818648911872>",
    "ICE": "<:ICE:1102210303518846976>",
    "IR": "<:IR:1143119119080767649>",
    "RB": "<:RB:1143231656895971349>",
    "RE": "<:RE:1143231659941056512>",
    "RJ": "<:RJ:1143109130270281758>",
    "RJX": "<:RJX:1143109133256642590>",
    "S": "<:SBahn:1102206882527060038>",
    "Schw-B": "<:Schwebebahn:1143108575770726510>",
    "STB": "<:UBahn:1143105924421132441>",
    "STR": "<:Tram:1143105662549766188>",
    "U": "<:UBahn:1143105924421132441>",
    "U1": "<:UWien:1143235532571291859>",
    "U2": "<:UWien:1143235532571291859>",
    "U3": "<:UWien:1143235532571291859>",
    "U4": "<:UWien:1143235532571291859>",
    "U5": "<:UWien:1143235532571291859>",
    "U6": "<:UWien:1143235532571291859>",
    "Ü": "<:uestra:1143092880089550928>",
}
color = {
    "Bus": "#a3167e",
    "EC": "#ff0404",
    "Fähre": "#00a4db",
    "IC": "#ff0404",
    "ICE": "#ff0404",
    "IR": "#ff0404",
    "NJ": "#282559",
    "RB": "#005fa3",
    "RE": "#e93c13",
    "RJ": "#c63131",
    "RJX": "#c63131",
    "S": "#008d4f",
    "Schw-B": "#4896d2",
    "STB": "#014e8d",
    "STR": "#da0031",
    "U": "#014e8d",
    "U1": "#ff2e17",
    "U2": "#9864b2",
    "U3": "#ff7d24",
    "U4": "#19a669",
    "U5": "#2e8e95",
    "U6": "#9a6736",
    "Ü": "#78b41d",
}
color = {k: discord.Colour.from_str(v) for (k, v) in color.items()}

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

    user = config["users"][str(member.id)]

    async with ClientSession() as session:
        async with session.get(
            f'https://travelynx.de/api/v1/status/{user["api"]}'
        ) as r:
            if r.status == 200:
                data = await r.json()
                await ia.response.send_message(
                    embed=format_travelynx(bot, member.id, data),
                    view=RefreshTravelynx(member.id, data),
                )


def format_time(sched, actual, relative=True):
    time = datetime.fromtimestamp(actual, tz=tz)
    diff = ""
    if not relative:
        return f"<t:{int(time.timestamp())}:R>"

    if actual > sched:
        diff = (actual - sched) // 60
        diff = f" **+{diff}′**"

    return f"<t:{int(time.timestamp())}:t>{diff}"


class RefreshTravelynx(discord.ui.View):
    def __init__(self, userid, data):
        super().__init__()
        self.timeout = None
        self.userid = userid
        self.zugid = zugid(data)

    @discord.ui.button(emoji="🔄", style=discord.ButtonStyle.grey)
    async def refresh(self, ia, button):
        async with ClientSession() as session:
            async with session.get(
                f'https://travelynx.de/api/v1/status/{config["users"][str(self.userid)]["api"]}'
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data["checkedIn"] and self.zugid == zugid(data):
                        await ia.response.edit_message(
                            embed=format_travelynx(bot, self.userid, data), view=self
                        )
                    else:
                        await ia.response.send_message(
                            "Die Fahrt ist bereits zu Ende.", ephemeral=True
                        )


def format_travelynx(bot, userid, data):
    user = bot.get_user(userid)
    if not data["checkedIn"]:
        return discord.Embed().set_author(
            name=f"{user.name} ist gerade nicht unterwegs",
            icon_url=user.avatar.url,
        )

    is_hafas = "|" in data["train"]["id"]

    # chop off long city names in station name
    short_from_name = data["fromStation"]["name"]
    if is_hafas:
        short_from_name = short_from_name.split(", ")[0]
    short_to_name = data["toStation"]["name"]
    if is_hafas:
        short_to_name = short_to_name.split(", ")[0]

    desc = ""
    # TODO multi trip
    # desc += f'### {format_time(data["fromStation"]["scheduledTime"], data["fromStation"]["realTime"])} {data["fromStation"]["name"]}\n'

    # account for "ME RE2" instead of "RE 2"
    train_type = data["train"]["type"]
    train_line = data["train"]["line"]
    if train_type not in train_type_emoji.keys():
        if (
            train_line
            and len(train_line) > 2
            and train_line[0:2] in train_type_emoji.keys()
        ):
            train_type = train_line[0:2]
            train_line = train_line[2:]

    if not train_line:
        train_line = data["train"]["no"]

    # the funky
    is_in_hannover = lambda lat, lon: (lat > 52.2047 and lat < 52.4543) and (
        lon > 9.5684 and lon < 9.9996
    )
    if train_type == "STR" and is_in_hannover(
        data["fromStation"]["latitude"], data["fromStation"]["longitude"]
    ):
        train_type = "Ü"

    if train_type == "U" and short_from_name.startswith("Wien "):
        train_type = short_from_name[-3:-1]

    desc += f'**{train_type_emoji.get(train_type, train_type)} [{train_line} ➤ ({data["toStation"]["name"]})]('

    link = (
        f'https://bahn.expert/details/{data["train"]["type"]}%20{data["train"]["no"]}/'
        + datetime.fromtimestamp(
            data["fromStation"]["scheduledTime"], tz=tz
        ).isoformat()
        + f'/?station={data["fromStation"]["uic"]}'
    )
    # if HAFAS, add journeyid to link to make sure it gets the right one
    if is_hafas:
        link += "&jid=" + data["train"]["id"]

    desc += link + ")**\n"
    desc += (
        f'{short_from_name} {format_time(data["fromStation"]["scheduledTime"], data["fromStation"]["realTime"])}'
        " – "
        f'{short_to_name} {format_time(data["toStation"]["scheduledTime"], data["toStation"]["realTime"])}\n'
    )
    if comment := data["comment"]:
        desc += f"> {comment}\n"

    # TODO multi trip
    # desc += f'### {format_time(data["toStation"]["scheduledTime"], data["toStation"]["realTime"])} {data["toStation"]["name"]}'

    e = discord.Embed(
        description=desc,
        colour=color.get(train_type),
    ).set_author(
        name=f"{user.name} ist unterwegs",
        icon_url=user.avatar.url,
    )
    return e


def main():
    "the function."
    bot.run(config["token"])


if __name__ == "__main__":
    main()
