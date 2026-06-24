"""환경 설정 로딩. .env 의 .NET식 키(__)를 읽어들인다."""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


# 디스코드 봇 토큰 (필수)
DISCORD_TOKEN = _get("Discord__Token")

# Spotify Client Credentials (없으면 Spotify 검색/링크 해석 불가)
SPOTIFY_CLIENT_ID = _get("Spotify__ClientId")
SPOTIFY_CLIENT_SECRET = _get("Spotify__ClientSecret")

# Neon PostgreSQL (현재 미사용)
DB_HOST = _get("Database__Host")
DB_USER = _get("Database__User")
DB_PASSWORD = _get("Database__Password")
DB_PORT = _get("Database__Port", "5432")
DB_NAME = _get("Database__Name", "novi_db")

ENVIRONMENT = _get("ASPNETCORE_ENVIRONMENT", "Production")

# yt-dlp 쿠키 파일 (클라우드/데이터센터 IP 에서 YouTube 봇 차단 우회용)
# Netscape 형식. 파일이 존재할 때만 사용된다.
COOKIES_FILE = _get("Ytdlp__CookiesFile", "cookies.txt")

SPOTIFY_ENABLED = bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)


def require_token() -> str:
    if not DISCORD_TOKEN:
        raise RuntimeError("Discord__Token 이 .env 에 없습니다. 토큰을 설정하세요.")
    return DISCORD_TOKEN
