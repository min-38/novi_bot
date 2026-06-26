"""곡 평가(F~S 티어) 슬래시 명령 cog. 응답 메시지만 노비 말투를 쓴다."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import db

# 티어별 표시 색 (티어표 임베드용)
_TIER_COLOR = {
    "S": 0xFF7F7F,
    "A": 0xFFBF7F,
    "B": 0xFFFF7F,
    "C": 0x7FFF7F,
    "D": 0x7FBFFF,
    "F": 0xBFBFBF,
}


class Rating(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _current_track(self, interaction: discord.Interaction):
        """음악 cog 에서 현재 재생 중인 곡을 가져온다."""
        music = self.bot.get_cog("Music")
        if not music:
            return None
        player = music.players.get(interaction.guild_id)
        return player.current if player else None

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not db.enabled():
            await interaction.response.send_message(
                "송구하오나 평가를 적어 둘 장부(데이터베이스)가 닫혀 있사옵니다, 나으리.",
                ephemeral=True,
            )
            return False
        return True

    # 곡 평가는 재생 메시지(now-playing)의 티어 버튼으로 한다. → player.NowPlayingControls

    # ================= /tier =================
    @app_commands.command(name="tier", description="곡의 평가(티어)를 살펴봅니다. 비우면 현재 곡.")
    @app_commands.describe(song="살펴볼 곡 제목 (비우면 지금 재생 중인 곡)")
    async def tier(self, interaction: discord.Interaction, song: str | None = None):
        if not await self._guard(interaction):
            return

        if song:
            # 제목으로 찾기 — 저장된 곡 중 제목이 일치/포함되는 것
            songs = await db.top_songs(limit=500)
            song_lower = song.lower()
            match = next((s for s in songs if song_lower in s["title"].lower()), None)
            if not match:
                return await interaction.response.send_message(
                    f"『{song}』 곡의 평가 기록이 아직 없사옵니다, 나으리.", ephemeral=True
                )
            info = match
        else:
            track = self._current_track(interaction)
            if track is None:
                return await interaction.response.send_message(
                    "지금 트는 곡이 없사옵니다. 곡 제목을 적어 주시옵소서.", ephemeral=True
                )
            info = await db.get_song(track.key)
            if info is None:
                return await interaction.response.send_message(
                    f"『{track.title}』 곡은 아직 아무도 평가하지 아니하였사옵니다.",
                    ephemeral=True,
                )

        embed = discord.Embed(
            title=f"{info['tier']}티어 — {info['title']}",
            description=f"평균 점수 **{info['avg_score']:.2f}** / 5 · 총 **{info['votes']}표**",
            color=_TIER_COLOR.get(info["tier"], 0x9B59B6),
        )
        if info.get("dist"):
            dist = info["dist"]
            line = "  ".join(f"{t}: {dist.get(t, 0)}" for t in db.TIERS)
            embed.add_field(name="표 분포", value=line, inline=False)
        await interaction.response.send_message(embed=embed)

    # ================= /tierlist =================
    @app_commands.command(name="tierlist", description="평가된 곡들을 티어표로 보여줍니다.")
    async def tierlist(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        await interaction.response.defer()
        songs = await db.top_songs(limit=200)
        if not songs:
            return await interaction.followup.send(
                "아직 평가된 곡이 하나도 없사옵니다, 나으리."
            )

        # 티어별로 묶기
        by_tier: dict[str, list[str]] = {t: [] for t in db.TIERS}
        for s in songs:
            by_tier[s["tier"]].append(f"{s['title']} ({s['votes']}표)")

        embed = discord.Embed(title="🏆 티어표", color=0xF1C40F)
        for t in db.TIERS:
            items = by_tier[t]
            if not items:
                continue
            shown = items[:10]
            value = "\n".join(shown)
            if len(items) > 10:
                value += f"\n…그 외 {len(items) - 10}곡"
            embed.add_field(name=f"{t}티어", value=value, inline=False)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Rating(bot))
