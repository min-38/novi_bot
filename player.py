"""길드(서버)마다 하나씩 두는 재생기. 큐와 재생 루프를 담당한다."""
from __future__ import annotations

import asyncio

import discord

import db
from sources import FFMPEG_OPTS, Track, resolve_stream_url

# 티어 색 사각형은 db.TIER_EMOJI 를 공용으로 쓴다.
_TIER_EMOJI = db.TIER_EMOJI

IDLE_TIMEOUT = 300  # 큐가 비면 5분 뒤 음성 채널에서 나간다.


def _fmt_views(n: int | None) -> str | None:
    if not n:
        return None
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}억회"
    if n >= 10_000:
        return f"{n / 10_000:.1f}만회"
    return f"{n:,}회"


def build_now_playing_embed(track: Track, rating: dict | None = None) -> discord.Embed:
    """현재 재생 곡의 메타데이터·평가 현황으로 임베드를 만든다."""
    embed = discord.Embed(
        title=track.title or "재생 중",
        url=track.webpage_url,
        color=0x1DB954,
    )
    embed.set_author(name="🎶 지금 재생 중")

    # ── 메타데이터 (한 줄에 나란히) ──
    embed.add_field(name="🎙️ 채널", value=track.uploader or "—", inline=True)
    embed.add_field(name="⏱️ 길이", value=track.duration_str, inline=True)
    embed.add_field(name="👁️ 조회수", value=_fmt_views(track.view_count) or "—", inline=True)

    # ── Spotify 출처 ──
    if track.spotify_artist:
        spo = track.spotify_title or ""
        line = f"{track.spotify_artist} — {spo}".strip(" —")
        if track.spotify_url:
            line = f"[{line}]({track.spotify_url})"
        embed.add_field(name="🎧 Spotify", value=line, inline=False)

    # ── 평가 현황 ──
    if rating:
        sq = _TIER_EMOJI.get(rating["tier"], "")
        embed.add_field(
            name="🏅 현재 평가",
            value=f"{sq} **{rating['tier']}티어**　·　{rating['votes']}표　·　평균 {rating['avg_score']:.1f}점",
            inline=False,
        )
    else:
        embed.add_field(
            name="🏅 평가",
            value="아직 평가가 없사옵니다. 아래 버튼으로 이 곡의 품계를 매겨 주시옵소서!",
            inline=False,
        )

    # ── 앨범아트(없으면 유튜브 썸네일) ──
    thumb = track.album_art or track.thumbnail
    if thumb:
        embed.set_thumbnail(url=thumb)
    embed.set_footer(text=f"청하신 나리 · {track.requester}", icon_url=track.requester_icon)
    return embed


class NowPlayingControls(discord.ui.View):
    """현재 재생 곡 메시지에 붙는 조작 버튼 + 티어 평가 버튼.

    티어 버튼은 메시지에 표시된 그 곡(track)에 고정으로 바인딩된다. 곡이 끝나
    다음 곡이 시작돼도 이 버튼은 원래 곡을 평가한다.
    """

    def __init__(self, player: "GuildPlayer", track: Track):
        super().__init__(timeout=None)
        self.player = player
        self.track = track
        # DB 가 켜져 있을 때만 티어 평가 버튼을 붙인다.
        if db.enabled():
            self._add_tier_buttons()

    @discord.ui.button(label="일시정지/재생", emoji="⏯️", style=discord.ButtonStyle.primary, row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.player.voice
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.send_message(
                "트는 곡이 없사옵니다, 나으리.", ephemeral=True
            )
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ 다시 이어 틀어 올리옵니다.")
        else:
            vc.pause()
            await interaction.response.send_message("⏸️ 잠시 멈추어 두었사옵니다.")

    @discord.ui.button(label="건너뛰기", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.player.voice
        if not vc or not vc.is_playing():
            return await interaction.response.send_message(
                "건너뛸 곡이 없사옵니다, 나으리.", ephemeral=True
            )
        title = self.player.current.title if self.player.current else "이 곡"
        vc.stop()
        await interaction.response.send_message(f"⏭️ 『{title}』 건너뛰었사옵니다.")

    def _add_tier_buttons(self):
        # 한 행에 5개까지 → S~D 한 줄(row 1), F 다음 줄(row 2)
        for idx, tier in enumerate(db.TIERS):
            row = 1 if idx < 5 else 2
            btn = discord.ui.Button(
                label=tier,
                emoji=_TIER_EMOJI.get(tier),
                style=discord.ButtonStyle.secondary,
                row=row,
            )
            btn.callback = self._make_rate_callback(tier)
            self.add_item(btn)

    def _make_rate_callback(self, tier: str):
        async def callback(interaction: discord.Interaction):
            track = self.track
            who = interaction.user.display_name
            old = await db.set_rating(track.key, track.title, interaction.user.id, tier)
            song = await db.get_song(track.key)

            if old is None:
                head = f"⭐ **{who}** 님이 『**{track.title}**』 에 **{tier}티어**를 매겼사옵니다!"
            elif old == tier:
                head = f"**{who}** 님이 『**{track.title}**』 에 그대로 **{tier}티어**를 두었사옵니다."
            else:
                head = (
                    f"🔄 **{who}** 님이 『**{track.title}**』 평가를 "
                    f"**{old}티어 → {tier}티어**로 바꾸었사옵니다!"
                )
            tail = ""
            if song:
                tail = f" 이제 이 곡은 **{song['tier']}티어**({song['votes']}표)이옵니다."
            # 누가 어떻게 매겼는지 모두 보이도록 공개 메시지로 아뢴다.
            await interaction.response.send_message(head + tail)

        return callback


class GuildPlayer:
    def __init__(self, bot, guild: discord.Guild, text_channel: discord.abc.Messageable):
        self.bot = bot
        self.guild = guild
        self.text_channel = text_channel
        self.queue: list[Track] = []
        self.current: Track | None = None
        self.voice: discord.VoiceClient | None = guild.voice_client
        self._wakeup = asyncio.Event()  # 새 곡 추가 등으로 깨울 때
        self._next = asyncio.Event()  # 한 곡 재생이 끝났을 때
        self._task = bot.loop.create_task(self._run())

    # ---- 큐 조작 ----
    def add(self, track: Track) -> int:
        self.queue.append(track)
        self._wakeup.set()
        return len(self.queue)

    def remove(self, index: int) -> Track | None:
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None

    def clear(self) -> int:
        n = len(self.queue)
        self.queue.clear()
        return n

    # ---- 재생 흐름 ----
    def _after(self, error):
        if error:
            print(f"[재생 오류] {error}")
        self.bot.loop.call_soon_threadsafe(self._next.set)

    async def _run(self):
        try:
            while True:
                if not self.queue:
                    self._wakeup.clear()
                    try:
                        await asyncio.wait_for(self._wakeup.wait(), timeout=IDLE_TIMEOUT)
                    except asyncio.TimeoutError:
                        await self._notify("오랜 적막에 쇤네 물러가옵니다. 부르시면 다시 오겠나이다.")
                        return await self.destroy()
                    continue

                track = self.queue.pop(0)
                self.current = track
                self._next.clear()

                try:
                    stream_url = await resolve_stream_url(track)
                    source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)
                except Exception as exc:
                    await self._notify(f"『{track.title}』 곡을 들이지 못하였사옵니다: {exc}")
                    self.current = None
                    continue

                if not self.voice or not self.voice.is_connected():
                    await self._notify("음성채널에서 쫓겨났사옵니다. 다시 불러 주시옵소서.")
                    return await self.destroy()

                self.voice.play(source, after=self._after)
                await self._announce(track)
                await self._next.wait()
                source.cleanup()
                self.current = None
        except asyncio.CancelledError:
            pass

    async def _notify(self, msg: str):
        try:
            await self.text_channel.send(msg)
        except Exception:
            pass

    async def _announce(self, track: Track):
        """현재 재생 곡을 메타데이터·평가현황·버튼과 함께 채널에 알린다."""
        rating = None
        if db.enabled():
            try:
                rating = await db.get_song(track.key)
            except Exception:
                rating = None
        embed = build_now_playing_embed(track, rating)
        try:
            await self.text_channel.send(
                content="🎵 이제 한 곡 틀어 올리옵니다.",
                embed=embed,
                view=NowPlayingControls(self, track),
            )
        except Exception:
            pass

    async def destroy(self):
        self.clear()
        if self.voice and self.voice.is_connected():
            await self.voice.disconnect(force=True)
        self.voice = None
        if self._task and not self._task.done():
            self._task.cancel()
        # cog 의 플레이어 레지스트리에서 제거
        self.bot.dispatch("player_destroyed", self.guild.id)
