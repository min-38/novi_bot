"""Neon PostgreSQL 평가(티어) 저장 계층.

곡마다 사용자가 F~S 티어를 매기고, 평균 점수로 대표 티어를 산출한다.
DB 자격이 없거나 연결에 실패하면 enabled() 가 False 가 되어 기능이 비활성화된다.
"""
from __future__ import annotations

import asyncpg

import config

# 높은 티어가 앞에 오도록 정렬된 순서
TIERS = ["S", "A", "B", "C", "D", "F"]
TIER_SCORE = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
# 티어 색 사각형 (UI 공용)
TIER_EMOJI = {"S": "🟥", "A": "🟧", "B": "🟨", "C": "🟩", "D": "🟦", "F": "⬜"}

_pool: asyncpg.Pool | None = None

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS song_ratings (
    song_key   TEXT   NOT NULL,
    user_id    BIGINT NOT NULL,
    title      TEXT   NOT NULL,
    tier       TEXT   NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (song_key, user_id)
);
"""

# 텍스트 티어 → 점수 변환용 SQL 조각
_SCORE_CASE = (
    "CASE tier WHEN 'S' THEN 5 WHEN 'A' THEN 4 WHEN 'B' THEN 3 "
    "WHEN 'C' THEN 2 WHEN 'D' THEN 1 ELSE 0 END"
)


def enabled() -> bool:
    return _pool is not None


def score_to_tier(score: float) -> str:
    """평균 점수(0~5)를 가장 가까운 티어로 환산한다."""
    nearest = round(score)
    nearest = max(0, min(5, nearest))
    for tier, val in TIER_SCORE.items():
        if val == nearest:
            return tier
    return "F"


async def init() -> bool:
    """연결 풀을 만들고 테이블을 보장한다. 성공 시 True."""
    global _pool
    if not (config.DB_HOST and config.DB_USER and config.DB_PASSWORD):
        print("[db] DB 자격이 없어 평가 기능을 끕니다.")
        return False
    try:
        _pool = await asyncpg.create_pool(
            host=config.DB_HOST,
            port=int(config.DB_PORT),
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            ssl="require",  # Neon 은 SSL 필수
            min_size=1,
            max_size=5,
        )
        async with _pool.acquire() as con:
            await con.execute(_CREATE_SQL)
        print("[db] 평가 저장소 준비 완료")
        return True
    except Exception as exc:
        print(f"[db] 연결 실패 — 평가 기능을 끕니다: {exc}")
        _pool = None
        return False


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def set_rating(song_key: str, title: str, user_id: int, tier: str) -> str | None:
    """사용자의 곡 평가를 추가/갱신한다 (곡+사용자당 1표).

    이전에 매긴 티어를 반환한다. 처음 매기는 경우 None.
    """
    assert _pool is not None
    async with _pool.acquire() as con:
        old_tier = await con.fetchval(
            "SELECT tier FROM song_ratings WHERE song_key = $1 AND user_id = $2;",
            song_key,
            user_id,
        )
        await con.execute(
            """
            INSERT INTO song_ratings (song_key, user_id, title, tier, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (song_key, user_id)
            DO UPDATE SET tier = EXCLUDED.tier,
                          title = EXCLUDED.title,
                          updated_at = now();
            """,
            song_key,
            user_id,
            title,
            tier,
        )
        return old_tier


async def get_song(song_key: str) -> dict | None:
    """한 곡의 집계(대표 티어·표수·티어별 분포)를 반환한다. 평가 없으면 None."""
    assert _pool is not None
    async with _pool.acquire() as con:
        row = await con.fetchrow(
            f"""
            SELECT max(title) AS title,
                   count(*)   AS votes,
                   avg({_SCORE_CASE})::float AS avg_score
            FROM song_ratings WHERE song_key = $1;
            """,
            song_key,
        )
        if not row or row["votes"] == 0:
            return None
        dist_rows = await con.fetch(
            "SELECT tier, count(*) AS n FROM song_ratings "
            "WHERE song_key = $1 GROUP BY tier;",
            song_key,
        )
    dist = {r["tier"]: r["n"] for r in dist_rows}
    return {
        "title": row["title"],
        "votes": row["votes"],
        "avg_score": row["avg_score"],
        "tier": score_to_tier(row["avg_score"]),
        "dist": dist,
    }


async def top_songs(limit: int = 50) -> list[dict]:
    """평가된 모든 곡을 평균 점수 내림차순으로 반환한다 (티어표용)."""
    assert _pool is not None
    async with _pool.acquire() as con:
        rows = await con.fetch(
            f"""
            SELECT song_key,
                   max(title) AS title,
                   count(*)   AS votes,
                   avg({_SCORE_CASE})::float AS avg_score
            FROM song_ratings
            GROUP BY song_key
            ORDER BY avg_score DESC, votes DESC
            LIMIT $1;
            """,
            limit,
        )
    return [
        {
            "song_key": r["song_key"],
            "title": r["title"],
            "votes": r["votes"],
            "avg_score": r["avg_score"],
            "tier": score_to_tier(r["avg_score"]),
        }
        for r in rows
    ]
