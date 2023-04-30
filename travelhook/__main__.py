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

server = discord.Object(id=config["server"])
tz = ZoneInfo("Europe/Berlin")

def zugid(data):
    return str(data["fromStation"]["scheduledTime"]) + data["train"]["no"]

async def receive(bot):
    async def handler(req):
        userid = [
            int(uid)
            for uid, u in config.users.items()
            if u["bearer"] == req.headers["authorization"].removeprefix("Bearer ")
        ][0]
        data = await req.json()

        if (
            not data["reason"] in ("update", "checkin", "ping")
            or not data["status"]["toStation"]["name"]
        ):
            raise web.HTTPOk()

        await bot.get_channel(config["channel"]).send(
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


emoji = {
    "S": "<:SBahn:1102206882527060038>",
    "IC": "<:IC:1102209818648911872>",
    "EC": "<:EC:1102209838307627082>",
    "ICE": "<:ICELogo:1102210303518846976>",
}
color = {
    "S": "#008d4f",
    "RB": "#005fa3",
    "RE": "#e93c13",
    "IC": "#ff0404",
    "EC": "#ff0404",
    "ICE": "#ff0404",
}
color = {k: discord.Colour.from_str(v) for (k, v) in color.items()}

intents = discord.Intents.default() | discord.Intents(members=True)
bot = commands.Bot(command_prefix=" ", intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync(guild=server)
    bot.loop.create_task(receive(bot))
    print(f"logged in as {bot.user}")


@bot.tree.command(description="Get current travelynx status", guild=server)
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
                    if self.zugid == zugid(data):
                        await ia.response.edit_message(
                            embed=format_travelynx(bot, self.userid, data), view=self
                        )


def format_travelynx(bot, userid, data):
    user = bot.get_user(userid)
    if not data["checkedIn"]:
        return discord.Embed().set_author(
            name=f"{user.name} ist gerade nicht unterwegs",
            icon_url=user.avatar.url,
        )

    desc = f'**{emoji.get(data["train"]["type"], data["train"]["type"])}**'
    if l := data["train"]["line"]:
        desc += f" **{l}**"
    desc += f' [*{data["train"]["no"]}*](https://dbf.finalrewind.org/z/{data["train"]["type"]}%20{data["train"]["no"]}/{data["fromStation"]["ds100"]})\n'
    desc += f'Ankunft {format_time(0, data["toStation"]["realTime"], False)}'

    e = (
        discord.Embed(
            timestamp=datetime.fromtimestamp(data["actionTime"], tz=tz),
            description=desc,
            colour=color.get(data["train"]["type"]),
        )
        .set_author(
            name=f"{user.name} ist unterwegs",
            icon_url=user.avatar.url,
        )
        .add_field(
            name=data["fromStation"]["name"],
            value=format_time(
                data["fromStation"]["scheduledTime"], data["fromStation"]["realTime"]
            ),
        )
    )
    if data["toStation"]["name"]:
        e.add_field(
            name=data["toStation"]["name"],
            value=format_time(
                data["toStation"]["scheduledTime"], data["toStation"]["realTime"]
            ),
        )
    return e


def main():
    "the function."
    bot.run(config["token"])


if __name__ == "__main__":
    main()
