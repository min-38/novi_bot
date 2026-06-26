"""음악 슬래시 명령 cog. 사용자에게 보내는 응답 메시지만 노비 말투를 쓴다."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from player import GuildPlayer
from sources import SpotifyUnavailable, Track, build_tracks, search_suggestions


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    # ---- 플레이어 레지스트리 ----
    def _get_player(self, interaction: discord.Interaction) -> GuildPlayer | None:
        return self.players.get(interaction.guild_id)

    def _ensure_player(self, interaction: discord.Interaction) -> GuildPlayer:
        player = self.players.get(interaction.guild_id)
        if player is None:
            player = GuildPlayer(self.bot, interaction.guild, interaction.channel)
            self.players[interaction.guild_id] = player
        else:
            player.text_channel = interaction.channel
        return player

    @commands.Cog.listener()
    async def on_player_destroyed(self, guild_id: int):
        self.players.pop(guild_id, None)

    async def _join_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        """명령을 호출한 사용자의 음성 채널에 접속한다."""
        user = interaction.user
        if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
            return None
        channel = user.voice.channel
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
        else:
            vc = await channel.connect()
        return vc

    # ================= /play =================
    async def play_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """입력하는 동안 Spotify 후보 곡을 자동완성으로 제시한다."""
        if len(current.strip()) < 2:
            return []
        try:
            suggestions = await search_suggestions(current, limit=7)
        except Exception:
            return []
        return [
            app_commands.Choice(name=label, value=url) for label, url in suggestions
        ]

    @app_commands.command(name="play", description="노래를 틀거나 큐 맨 뒤에 줄 세우옵니다.")
    @app_commands.describe(query="노래 제목을 적으면 Spotify 후보가 떠오르옵니다. Spotify 링크도 되옵니다.")
    @app_commands.autocomplete(query=play_autocomplete)
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        vc = await self._join_voice(interaction)
        if vc is None:
            return await interaction.followup.send(
                "나으리, 먼저 음성채널에 드시옵소서. 쇤네 따라 들어가오리다."
            )

        try:
            tracks: list[Track] = await build_tracks(query, interaction.user.display_name)
        except SpotifyUnavailable:
            return await interaction.followup.send(
                "송구하오나 Spotify 와 연이 닿지 아니하여 곡을 가려낼 수 없사옵니다, 나으리."
            )
        except Exception as exc:
            return await interaction.followup.send(
                f"송구하옵니다, 곡을 찾지 못하였사옵니다: {exc}"
            )
        if not tracks:
            return await interaction.followup.send(
                f"송구하옵니다 나으리, 『{query}』 곡은 **Spotify 에 없어** 틀어 드릴 수 없사옵니다."
            )

        player = self._ensure_player(interaction)
        player.voice = vc

        icon = interaction.user.display_avatar.url
        for t in tracks:
            t.requester_icon = icon
            player.add(t)

        if len(tracks) == 1:
            t = tracks[0]
            pos = len(player.queue)
            if player.current is None and pos <= 1:
                msg = f"분부 받자와 『**{t.title}**』 곧 틀어 올리겠나이다."
            else:
                msg = f"『**{t.title}**』 곡을 큐 **{pos}번째** 자리에 줄 세웠사옵니다."
        else:
            msg = f"분부대로 **{len(tracks)}곡**을 큐 맨 뒤에 줄 세웠사옵니다, 나으리."
        await interaction.followup.send(msg)

    # ================= /skip =================
    @app_commands.command(name="skip", description="지금 곡을 건너뛰옵니다.")
    async def skip(self, interaction: discord.Interaction):
        player = self._get_player(interaction)
        if not player or not player.voice or not player.voice.is_playing():
            return await interaction.response.send_message(
                "지금 틀린 곡이 없사옵니다, 나으리.", ephemeral=True
            )
        title = player.current.title if player.current else "이 곡"
        player.voice.stop()  # after 콜백이 다음 곡으로 진행시킨다.
        await interaction.response.send_message(f"⏭️ 『{title}』 건너뛰었사옵니다.")

    # ================= /pause =================
    @app_commands.command(name="pause", description="틀린 곡을 잠시 멈추옵니다.")
    async def pause(self, interaction: discord.Interaction):
        player = self._get_player(interaction)
        if not player or not player.voice or not player.voice.is_playing():
            return await interaction.response.send_message(
                "멈출 곡이 없사옵니다, 나으리.", ephemeral=True
            )
        player.voice.pause()
        await interaction.response.send_message("⏸️ 잠시 멈추어 두었사옵니다. 분부만 내리시옵소서.")

    # ================= /resume =================
    @app_commands.command(name="resume", description="멈춘 곡을 다시 트옵니다.")
    async def resume(self, interaction: discord.Interaction):
        player = self._get_player(interaction)
        if not player or not player.voice or not player.voice.is_paused():
            return await interaction.response.send_message(
                "멈춰 둔 곡이 없사옵니다, 나으리.", ephemeral=True
            )
        player.voice.resume()
        await interaction.response.send_message("▶️ 다시 이어 틀어 올리옵니다.")

    # ================= /queue (그룹) =================
    queue_group = app_commands.Group(name="queue", description="큐를 살피고 다스리옵니다.")

    @queue_group.command(name="list", description="큐에 줄 선 곡들을 보여드리옵니다.")
    async def queue_list(self, interaction: discord.Interaction):
        player = self._get_player(interaction)
        if not player or (not player.queue and not player.current):
            return await interaction.response.send_message(
                "큐가 텅 비었사옵니다, 나으리.", ephemeral=True
            )

        embed = discord.Embed(title="🎼 큐 목록이옵니다", color=0x9B59B6)
        if player.current:
            embed.add_field(
                name="지금 트는 곡",
                value=f"**{player.current.title}** ({player.current.duration_str}) — {player.current.requester}",
                inline=False,
            )
        if player.queue:
            lines = []
            for i, t in enumerate(player.queue[:20], start=1):
                lines.append(f"`{i}.` {t.title} ({t.duration_str}) — {t.requester}")
            more = len(player.queue) - 20
            if more > 0:
                lines.append(f"…그 외 **{more}곡**이 더 있사옵니다.")
            embed.add_field(name="줄 선 곡", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="줄 선 곡", value="뒤에 줄 선 곡은 없사옵니다.", inline=False)

        view = QueueControls(self, interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view)

    @queue_group.command(name="remove", description="큐에서 곡 하나를 빼옵니다.")
    @app_commands.describe(position="뺄 곡의 번호이옵니다 (queue list 의 번호).")
    async def queue_remove(self, interaction: discord.Interaction, position: int):
        player = self._get_player(interaction)
        if not player or not player.queue:
            return await interaction.response.send_message(
                "뺄 곡이 없사옵니다, 나으리.", ephemeral=True
            )
        removed = player.remove(position - 1)
        if removed is None:
            return await interaction.response.send_message(
                f"{position}번 자리에는 곡이 없사옵니다.", ephemeral=True
            )
        await interaction.response.send_message(
            f"🗑️ 큐에서 『{removed.title}』 빼었사옵니다."
        )

    @queue_group.command(name="clear", description="큐를 몽땅 비우옵니다.")
    async def queue_clear(self, interaction: discord.Interaction):
        player = self._get_player(interaction)
        if not player or not player.queue:
            return await interaction.response.send_message(
                "이미 큐가 비었사옵니다, 나으리.", ephemeral=True
            )
        n = player.clear()
        await interaction.response.send_message(f"🧹 줄 선 **{n}곡**을 모두 비웠사옵니다.")

    # ================= /leave =================
    @app_commands.command(name="leave", description="음성채널에서 물러나옵니다.")
    async def leave(self, interaction: discord.Interaction):
        player = self._get_player(interaction)
        if not player:
            return await interaction.response.send_message(
                "쇤네 이미 물러나 있사옵니다.", ephemeral=True
            )
        await player.destroy()
        await interaction.response.send_message("👋 분부대로 물러가옵니다. 부르시면 다시 오겠나이다.")


class QueueControls(discord.ui.View):
    """큐 목록 메시지에 붙는 버튼."""

    def __init__(self, cog: Music, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id

    def _player(self) -> GuildPlayer | None:
        return self.cog.players.get(self.guild_id)

    @discord.ui.button(label="건너뛰기", emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self._player()
        if player and player.voice and player.voice.is_playing():
            title = player.current.title if player.current else "이 곡"
            player.voice.stop()
            await interaction.response.send_message(f"⏭️ 『{title}』 건너뛰었사옵니다.")
        else:
            await interaction.response.send_message("틀린 곡이 없사옵니다.", ephemeral=True)

    @discord.ui.button(label="큐 비우기", emoji="🧹", style=discord.ButtonStyle.danger)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self._player()
        if player and player.queue:
            n = player.clear()
            await interaction.response.send_message(f"🧹 줄 선 **{n}곡**을 모두 비웠사옵니다.")
        else:
            await interaction.response.send_message("비울 곡이 없사옵니다.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
