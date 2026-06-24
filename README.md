# novi_bot

조선시대 노비 말투로 응대하는 디스코드 음악 봇입니다.

모든 곡은 **Spotify를 거쳐 확인**한 뒤, 실제 소리는 확인된 곡 이름으로 **YouTube(yt-dlp)**에서 받아 재생합니다. Spotify에 없는 곡은 재생하지 않습니다. 지금 재생 중인 곡은 YouTube 메타데이터(채널·길이·조회수·섬네일)와 함께 표시합니다.

## 명령어

| 명령 | 설명 |
|------|------|
| `/play <검색어\|Spotify 링크>` | 곡을 재생하거나, 이미 재생 중이면 큐 맨 뒤에 추가. 입력 중 Spotify 자동완성 후보가 표시되며, Spotify에 없으면 거절 |
| `/skip` | 현재 곡 건너뛰기 |
| `/pause` | 일시정지 |
| `/resume` | 다시 재생 |
| `/queue list` | 큐 보기 (건너뛰기·비우기 버튼 포함) |
| `/queue remove <번호>` | 큐에서 특정 곡 삭제 |
| `/queue clear` | 큐 비우기 |
| `/leave` | 음성 채널에서 나가기 |

재생 중 메시지의 **⏯️ / ⏭️ 버튼**으로도 일시정지·재생·건너뛰기를 할 수 있습니다. 큐가 5분간 비어 있으면 자동으로 음성 채널에서 나갑니다.

## 환경 변수 (`.env`)

`.NET` 계층 키 형식(언더스코어 2개 `__`)을 사용합니다.

| 키 | 필수 | 설명 |
|----|------|------|
| `Discord__Token` | ✅ | 디스코드 봇 토큰 |
| `Spotify__ClientId` | ✅ | Spotify 앱 Client ID |
| `Spotify__ClientSecret` | ✅ | Spotify 앱 Client Secret |
| `Database__*` | ❌ | Neon PostgreSQL (현재 미사용) |
| `ASPNETCORE_ENVIRONMENT` | ❌ | 실행 환경 |

> `.env`는 `.gitignore` 처리되어 git에 올라가지 않습니다. 배포하는 VM에서 직접 만들어야 합니다.

봇을 서버에 초대할 때 OAuth2 범위는 `bot` + `applications.commands`, 권한은 음성(Connect, Speak)을 부여하세요.

---

## Docker로 VM에 배포하기

소스는 git clone으로 받아 옵니다. VM에는 **Docker**와 (선택) **Docker Compose**가 설치되어 있어야 합니다.

### 1) 소스 받기

```bash
git clone <레포지토리_URL> novi_bot
cd novi_bot
```

### 2) `.env` 만들기

`.env`는 레포에 포함되지 않으므로 VM에서 직접 생성합니다.

```bash
cat > .env <<'EOF'
Discord__Token=여기에_봇_토큰
Spotify__ClientId=여기에_클라이언트_ID
Spotify__ClientSecret=여기에_클라이언트_시크릿
ASPNETCORE_ENVIRONMENT=Production
EOF
```

### 3) 실행

**방법 A — Docker Compose (권장)**

```bash
docker compose up -d --build      # 빌드 후 백그라운드 실행
docker compose logs -f            # 로그 보기
docker compose down               # 중지/제거
```

코드를 업데이트할 때:

```bash
git pull
docker compose up -d --build
```

**방법 B — Docker 단독**

```bash
docker build -t novi_bot .
docker run -d --name novi_bot --env-file .env --restart unless-stopped novi_bot

docker logs -f novi_bot           # 로그 보기
docker rm -f novi_bot             # 중지/제거
```

### 참고
- 이 봇은 외부로 음성 연결만 하므로 **포트 개방(인바운드)이 필요 없습니다.**
- 이미지에 FFmpeg가 포함되어 있어 VM에 별도 설치할 필요가 없습니다.
- `restart: unless-stopped` 덕분에 VM 재부팅 후에도 컨테이너가 자동으로 다시 뜹니다.

---

## 구조

- `bot.py` — 진입점. 봇 기동 및 슬래시 명령 등록
- `config.py` — `.env`(`.NET` 식 `__` 키) 로딩
- `sources.py` — Spotify 확인 + yt-dlp로 곡/메타데이터 해석, 자동완성
- `player.py` — 길드별 큐와 재생 루프, 재생 임베드·버튼
- `cogs/music.py` — 슬래시 명령 (노비 말투 응답)
