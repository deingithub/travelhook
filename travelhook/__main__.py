import json
import typing
import sqlite3

from aiohttp import ClientSession, web
import discord
from discord.ext import commands

from .format import format_travelynx

config = {}
with open("settings.json", "r", encoding="utf-8") as f:
    config = json.load(f)

servers = [discord.Object(id=i) for i in config["servers"]]



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


def main():
    "the function."
    bot.run(config["token"])


if __name__ == "__main__":
    main()
