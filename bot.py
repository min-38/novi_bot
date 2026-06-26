"""봇 진입점. 봇을 기동하고 슬래시 명령을 등록한다."""
from __future__ import annotations

import discord
from discord.ext import commands

import config
import db

intents = discord.Intents.default()
intents.message_content = False  # 슬래시 명령만 사용하므로 불필요


class NoviBot(commands.Bot):
    async def setup_hook(self):
        await db.init()  # 실패해도 평가 기능만 비활성화되고 봇은 동작한다.
        await self.load_extension("cogs.music")
        await self.load_extension("cogs.rating")
        synced = await self.tree.sync()
        print(f"[novi_bot] 슬래시 명령 {len(synced)}개 등록 완료")

    async def close(self):
        await db.close()
        await super().close()


bot = NoviBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"[novi_bot] {bot.user} (id={bot.user.id}) 준비 완료")


def main():
    token = config.require_token()
    bot.run(token)


if __name__ == "__main__":
    main()
