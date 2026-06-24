"""곡 해석 모듈.

모든 곡은 반드시 Spotify 를 거친다. 검색어든 Spotify 링크든 먼저 Spotify 에서
곡(가수-제목)을 확인하고, Spotify 에 없는 곡은 재생하지 않는다. Spotify 는 음원을
제공하지 않으므로, 확인된 곡 이름으로 YouTube 에서 yt-dlp 로 받아온다.
"""
from __future__ import annotations

import asyncio
import functools
import os
import re
from dataclasses import dataclass

import yt_dlp

import config

# ---- Spotify (문지기) ----
_spotify = None
if config.SPOTIFY_ENABLED:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        _spotify = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=config.SPOTIFY_CLIENT_ID,
                client_secret=config.SPOTIFY_CLIENT_SECRET,
            )
        )
    except Exception:
        _spotify = None


class SpotifyUnavailable(Exception):
    """Spotify 자격 증명이 없거나 연결에 실패했을 때."""


YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "skip_download": True,
}

# 쿠키 파일이 있으면 yt-dlp 에 넘긴다 (클라우드 IP 봇 차단 우회).
if config.COOKIES_FILE and os.path.isfile(config.COOKIES_FILE):
    YTDL_OPTS["cookiefile"] = config.COOKIES_FILE
    print(f"[sources] yt-dlp 쿠키 파일 사용: {config.COOKIES_FILE}")
else:
    print("[sources] 쿠키 파일 없음 — 클라우드에서 YouTube 봇 차단이 발생할 수 있음")

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

_ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)

_SPOTIFY_RE = re.compile(r"open\.spotify\.com/(track|album|playlist)/([A-Za-z0-9]+)")


@dataclass
class Track:
    """큐에 담기는 한 곡."""

    title: str  # 표시 이름 (재생 전엔 Spotify, 재생 후엔 YouTube 제목)
    requester: str
    search_query: str  # YouTube 검색어 (가수 제목)

    # Spotify 에서 확인한 정보
    spotify_title: str | None = None
    spotify_artist: str | None = None
    spotify_url: str | None = None
    album_art: str | None = None

    # 재생 직전 YouTube 에서 채워지는 메타데이터
    webpage_url: str | None = None
    duration: int | None = None
    uploader: str | None = None
    view_count: int | None = None
    thumbnail: str | None = None

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "?:??"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _spotify_item_fields(item: dict) -> dict:
    """Spotify 트랙 항목에서 필요한 정보를 추출한다."""
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    name = item.get("name", "")
    album = item.get("album") or {}
    images = album.get("images") or []
    return {
        "title": f"{artists} - {name}".strip(" -"),
        "search_query": f"{artists} {name}".strip(),
        "spotify_title": name,
        "spotify_artist": artists,
        "spotify_url": (item.get("external_urls") or {}).get("spotify"),
        "album_art": images[0]["url"] if images else None,
    }


def _make_track(item: dict, requester: str) -> Track:
    f = _spotify_item_fields(item)
    return Track(
        title=f["title"],
        requester=requester,
        search_query=f["search_query"],
        spotify_title=f["spotify_title"],
        spotify_artist=f["spotify_artist"],
        spotify_url=f["spotify_url"],
        album_art=f["album_art"],
    )


def _resolve_via_spotify(query: str, requester: str) -> list[Track]:
    """검색어 또는 Spotify 링크를 Spotify 로 확인하여 Track 목록을 만든다."""
    if not _spotify:
        raise SpotifyUnavailable()

    m = _SPOTIFY_RE.search(query)
    if m:  # Spotify 링크
        kind, sid = m.group(1), m.group(2)
        if kind == "track":
            return [_make_track(_spotify.track(sid), requester)]
        if kind == "album":
            album = _spotify.album(sid)
            tracks = []
            for it in _spotify.album_tracks(sid)["items"]:
                it = dict(it)
                it.setdefault("album", album)  # album_tracks 에는 앨범아트가 없음
                tracks.append(_make_track(it, requester))
            return tracks
        if kind == "playlist":
            tracks = []
            for it in _spotify.playlist_items(sid)["items"]:
                tr = it.get("track")
                if tr:
                    tracks.append(_make_track(tr, requester))
            return tracks
        return []

    # 일반 검색어 → Spotify 에서 가장 알맞은 한 곡을 찾는다.
    results = _spotify.search(q=query, type="track", limit=1)
    items = (results.get("tracks") or {}).get("items") or []
    if not items:
        return []
    return [_make_track(items[0], requester)]


async def build_tracks(query: str, requester: str) -> list[Track]:
    """검색어/링크에서 큐에 담을 Track 목록을 만든다 (Spotify 확인 필수)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(_resolve_via_spotify, query, requester)
    )


def _search_suggestions(query: str, limit: int = 7) -> list[tuple[str, str]]:
    """자동완성용. Spotify 에서 후보 곡들의 (표시 이름, 링크)를 반환한다."""
    if not _spotify or not query.strip():
        return []
    try:
        results = _spotify.search(q=query, type="track", limit=limit)
    except Exception:
        return []
    items = (results.get("tracks") or {}).get("items") or []
    out: list[tuple[str, str]] = []
    for it in items:
        artists = ", ".join(a["name"] for a in it.get("artists", []))
        label = f"{artists} - {it.get('name', '')}".strip(" -")
        if len(label) > 95:
            label = label[:94] + "…"
        url = (it.get("external_urls") or {}).get("spotify") or label
        out.append((label, url))
    return out


async def search_suggestions(query: str, limit: int = 7) -> list[tuple[str, str]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(_search_suggestions, query, limit)
    )


def _extract(query: str) -> dict | None:
    info = _ytdl.extract_info(query, download=False)
    if info and "entries" in info:
        entries = [e for e in info["entries"] if e]
        info = entries[0] if entries else None
    return info


async def resolve_stream_url(track: Track) -> str:
    """재생 직전, YouTube 에서 스트림 URL 과 메타데이터를 받아온다."""
    loop = asyncio.get_running_loop()
    target = track.webpage_url or f"ytsearch1:{track.search_query}"
    info = await loop.run_in_executor(None, functools.partial(_extract, target))
    if not info:
        raise RuntimeError("YouTube 스트림을 가져오지 못했습니다.")
    # YouTube 메타데이터 채우기
    track.title = info.get("title", track.title)
    track.duration = info.get("duration", track.duration)
    track.webpage_url = info.get("webpage_url", track.webpage_url)
    track.uploader = info.get("uploader") or info.get("channel")
    track.view_count = info.get("view_count")
    track.thumbnail = info.get("thumbnail")
    return info["url"]
