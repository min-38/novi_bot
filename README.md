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
| `/tier [곡]` | 곡의 평가(티어)·표 분포 보기 (비우면 현재 곡) |
| `/tierlist` | 평가된 곡을 티어별로 모은 티어표 보기 |

재생 중 메시지의 **⏯️ / ⏭️ 버튼**으로 일시정지·재생·건너뛰기를 할 수 있습니다. 큐가 5분간 비어 있으면 자동으로 음성 채널에서 나갑니다.

### 곡 평가 (티어)

곡이 재생되면 now-playing 메시지에 **티어 버튼(S · A · B · C · D · F)** 이 함께 표시됩니다. 버튼을 누르면 그 곡에 티어를 매기며, 한 사람당 곡별 1표(다시 누르면 갱신)입니다. 여러 사람의 표를 점수(S=5 … F=0)로 환산해 평균을 내고, 가장 가까운 티어를 대표 티어로 산출합니다.

- 곡 식별은 **Spotify 곡 ID** 기준이라, 같은 곡을 다른 YouTube 영상으로 틀어도 평가가 합쳐집니다.
- 평가 데이터는 **Neon PostgreSQL**에 저장되어 봇 재시작·재배포 후에도 유지됩니다.
- DB 연결이 없으면 평가 버튼·명령은 자동으로 비활성화되고, 음악 기능은 정상 동작합니다.

## 환경 변수 (`.env`)

`.NET` 계층 키 형식(언더스코어 2개 `__`)을 사용합니다.

| 키 | 필수 | 설명 |
|----|------|------|
| `Discord__Token` | ✅ | 디스코드 봇 토큰 |
| `Spotify__ClientId` | ✅ | Spotify 앱 Client ID |
| `Spotify__ClientSecret` | ✅ | Spotify 앱 Client Secret |
| `Database__Host` / `Database__User` / `Database__Password` | ⬜ | Neon PostgreSQL. 있으면 곡 평가(티어) 기능 활성화. 없으면 음악만 동작 |
| `Database__Port` / `Database__Name` | ❌ | 기본값 `5432` / `novi_db` |
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

### 3) `cookies.txt` 준비 (클라우드 필수)

클라우드/VM의 데이터센터 IP에서는 YouTube가 yt-dlp를 봇으로 간주해 차단하는 경우가 많습니다(`Sign in to confirm you're not a bot`). 이를 우회하려면 YouTube 쿠키를 Netscape 형식으로 내보낸 `cookies.txt`가 필요합니다.

1. 로컬 브라우저에서 YouTube에 로그인 (전용/부계정 권장)
2. 쿠키 내보내기 확장 프로그램 사용 — 예: "Get cookies.txt LOCALLY" (Chrome/Firefox). youtube.com 접속 상태에서 내보내면 Netscape 형식 `cookies.txt`가 생성됩니다.
3. 이 파일을 VM의 프로젝트 루트(`novi_bot/cookies.txt`)에 둡니다.

```bash
# 예: 로컬에서 만든 cookies.txt 를 VM 으로 복사
scp cookies.txt <user>@<vm-host>:~/novi_bot/cookies.txt
```

- `cookies.txt`는 `.gitignore` 처리되어 커밋되지 않으며, Compose가 컨테이너의 `/app/cookies.txt`로 마운트합니다.
- 파일이 있으면 자동 사용되고, 없으면 쿠키 없이 동작합니다(로컬에선 보통 문제없음).
- 쿠키는 만료될 수 있으니, 차단이 다시 발생하면 새로 내보내 교체하세요. 경로를 바꾸려면 `.env`에 `Ytdlp__CookiesFile=/경로/cookies.txt`를 지정합니다.

> ⚠️ Compose 볼륨 마운트 특성상, 실행 **전에** 호스트에 `cookies.txt`가 존재해야 합니다. 없으면 Docker가 같은 이름의 빈 디렉터리를 만들어 버립니다. 쿠키를 쓰지 않을 거라면 `docker-compose.yml`의 해당 `volumes` 줄을 지우세요.

### 4) 실행

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
docker run -d --name novi_bot \
  --env-file .env \
  -v "$PWD/cookies.txt:/app/cookies.txt" \
  --restart unless-stopped novi_bot

docker logs -f novi_bot           # 로그 보기
docker rm -f novi_bot             # 중지/제거
```

(쿠키를 쓰지 않으면 `-v` 줄은 생략하세요.)

### 참고
- 이 봇은 외부로 음성 연결만 하므로 **포트 개방(인바운드)이 필요 없습니다.**
- 이미지에 FFmpeg가 포함되어 있어 VM에 별도 설치할 필요가 없습니다.
- `restart: unless-stopped` 덕분에 VM 재부팅 후에도 컨테이너가 자동으로 다시 뜹니다.

---

## 구조

- `bot.py` — 진입점. 봇 기동, DB 초기화, 슬래시 명령 등록
- `config.py` — `.env`(`.NET` 식 `__` 키) 로딩
- `sources.py` — Spotify 확인 + yt-dlp로 곡/메타데이터 해석, 자동완성
- `player.py` — 길드별 큐와 재생 루프, 재생 임베드, 조작·티어 평가 버튼
- `db.py` — Neon PostgreSQL 평가(티어) 저장 계층
- `cogs/music.py` — 음악 슬래시 명령 (노비 말투 응답)
- `cogs/rating.py` — 평가 조회 명령(`/tier`, `/tierlist`)
