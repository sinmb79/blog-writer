# 블로그 자동 수익 엔진 v3.2

**The 4th Path** — AI 기반 1인 미디어 자동화 엔진

블로그 글 작성부터 멀티플랫폼 배포, YouTube Shorts 생산까지 완전 자동화.
Windows 미니PC 24시간 운영을 전제로 설계된 무인 운영 시스템.

---

## 목차

1. [개요](#개요)
2. [주요 기능](#주요-기능)
3. [아키텍처](#아키텍처)
4. [설치](#설치)
5. [설정](#설정)
6. [사용법](#사용법)
7. [대시보드](#대시보드)
8. [YouTube Shorts 봇](#youtube-shorts-봇)
9. [멀티플랫폼 배포](#멀티플랫폼-배포)
10. [소설 파이프라인](#소설-파이프라인)
11. [수동 어시스트 모드](#수동-어시스트-모드)
12. [Telegram 명령어](#telegram-명령어)
13. [스케줄](#스케줄)
14. [엔진 추상화](#엔진-추상화)
15. [개발 현황](#개발-현황)

---

## 개요

이 프로젝트는 **블로그 자동 수익화**를 위한 풀스택 자동화 엔진입니다.
Google AdSense, 쿠팡 파트너스, YouTube 광고 수익을 동시에 추구하며
하나의 블로그 글을 인스타그램, X, TikTok, YouTube Shorts 등 멀티플랫폼 콘텐츠로 자동 변환합니다.

### 핵심 설계 원칙

- **무인 운영**: 매일 정해진 시간에 자동 실행, 사람 개입 불필요
- **AI 엔진 추상화**: OpenClaw(로컬) / Claude / Gemini 중 선택해 글쓰기 엔진 교체 가능
- **비용 최소화**: 무료 API(Edge TTS, Pexels 등) 우선, 유료는 선택적
- **Telegram 제어**: 외출 중에도 스마트폰으로 승인/거부/명령 가능

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 트렌드 수집 | Google Trends + RSS 피드 자동 수집, 품질 점수(0-100) 부여 |
| AI 글쓰기 | LLM으로 Blogger-ready HTML 원고 자동 생성 |
| 쿠팡 링크 삽입 | 글 주제 키워드 기반 쿠팡 파트너스 링크 자동 삽입 |
| 블로그 발행 | Blogger API로 자동 발행 + Search Console 색인 요청 |
| 멀티플랫폼 배포 | 인스타그램 카드/릴스, X 스레드, TikTok, YouTube 자동 배포 |
| YouTube Shorts | 블로그 글 → TTS + 자막 + 스톡 영상 → Shorts 자동 생산 |
| 이미지 생성 | DALL-E / 수동 / 요청 모드 선택 가능 |
| 소설 연재 | 매주 자동 소설 에피소드 생성 + 블로그 발행 |
| 대시보드 | React + FastAPI 웹 대시보드 (http://localhost:8080) |
| Telegram 봇 | 명령어로 승인/거부/즉시실행/상태확인 |

---

## 아키텍처

```
blog-writer/
├── bots/
│   ├── collector_bot.py       트렌드 수집
│   ├── writer_bot.py          AI 글쓰기
│   ├── article_parser.py      원고 파싱
│   ├── linker_bot.py          쿠팡 링크 삽입
│   ├── publisher_bot.py       Blogger 발행
│   ├── image_bot.py           이미지 생성/수신
│   ├── analytics_bot.py       성과 분석
│   ├── scheduler.py           스케줄러 + Telegram 리스너
│   ├── engine_loader.py       AI 엔진 팩토리
│   ├── assist_bot.py          수동 어시스트 파이프라인
│   ├── shorts_bot.py          YouTube Shorts 오케스트레이터
│   ├── converters/            변환 엔진 (blog/card/thread/shorts)
│   ├── distributors/          배포 엔진 (instagram/x/tiktok/youtube)
│   ├── novel/                 소설 파이프라인
│   └── shorts/                Shorts 서브모듈 (7개)
│       ├── tts_engine.py
│       ├── script_extractor.py
│       ├── asset_resolver.py
│       ├── stock_fetcher.py
│       ├── caption_renderer.py
│       ├── video_assembler.py
│       └── youtube_uploader.py
├── dashboard/
│   ├── backend/               FastAPI
│   └── frontend/              React
├── config/
│   ├── engine.json            AI 엔진 선택
│   └── shorts_config.json     Shorts 파이프라인 설정
├── templates/                 프롬프트 템플릿
├── assets/                    캐릭터/배경 이미지 (직접 추가)
├── input/                     수동 에셋 입력 (semi-auto 모드)
├── scripts/
│   ├── setup.bat
│   ├── get_token.py
│   └── download_fonts.py
├── blog.cmd                   Windows 런처
├── blog_runtime.py
└── runtime_guard.py
```

### 4계층 구조

```
LAYER 1  AI 콘텐츠 생성   OpenClaw / Claude / Gemini
LAYER 2  변환 엔진        Python (AI 없음)
LAYER 3  배포 엔진        Python (AI 없음)
LAYER 4  분석 + 피드백    Python (AI 없음)
```

---

## 설치

### 필수 요구사항

- Python 3.11+
- FFmpeg (https://ffmpeg.org/download.html) — Windows PATH 등록 필요
- Node.js 18+ (https://nodejs.org/) — 대시보드용

### 1단계: 저장소 클론

```bash
git clone https://github.com/sinmb79/blog-writer.git
cd blog-writer
```

### 2단계: 자동 설치

```batch
scripts\setup.bat
```

자동 실행 내용:
- Python venv 생성 + 패키지 설치
- 데이터/에셋/입력 디렉터리 생성
- 한글 폰트 다운로드 (Noto Sans KR)
- Windows 작업 스케줄러 등록

### macOS 빠른 시작

macOS에서는 `scripts\setup.bat` 대신 아래를 사용하세요.

```bash
bash scripts/setup-mac.sh
```

주의사항:
- `pip install -e .` 는 현재 저장소 구조상 필수가 아니며, 직접 실행 방식(`python bots/scheduler.py`, `python -m dashboard.backend.server`)을 권장합니다.
- `.env`는 프로젝트 루트의 `.env`를 기본으로 읽도록 동작합니다.
- Windows 전용 단계(작업 스케줄러 등록, `blog.cmd`)는 macOS에서 실행하지 않습니다.

### 3단계: API 키 설정

`.env.example`을 참고해 API 키를 입력합니다.

```bash
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=   # get_token.py 실행 후 자동 입력
BLOG_MAIN_ID=           # Blogger 블로그 ID (18자리 숫자)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

보안 팁: .env 파일을 프로젝트 폴더 외부(예: D:\key\)에 두고
`load_dotenv()` 형태로 참조하면
git에 절대 포함되지 않습니다. 이 프로젝트는 이 방식을 기본으로 사용합니다.

### 4단계: Google OAuth 토큰 발급

```bash
python scripts/get_token.py
```

브라우저에서 Google 로그인 후 `token.json`에 자동 저장됩니다.
YouTube 업로드를 사용하려면 youtube.upload 스코프가 포함되어야 합니다.

### 5단계: 대시보드 프론트엔드 설치

```bash
cd dashboard/frontend && npm install && cd ../..
```

---

## 설정

### config/engine.json

```json
{
  "writing": "openclaw",
  "tts":     "edge_tts",
  "image":   "openai",
  "video":   "local"
}
```

writing 옵션: openclaw / claude / gemini / gemini_web / openai

### config/shorts_config.json

| 키 | 기본값 | 설명 |
|----|--------|------|
| enabled | true | Shorts 봇 활성화 |
| production_mode | "auto" | auto 또는 semi_auto |
| tts.engine_priority | ["elevenlabs","google_cloud","edge_tts"] | TTS 우선순위 |
| visuals.source_priority | ["input_dir","character_assets","pexels","pixabay"] | 영상 소스 |
| youtube.daily_upload_limit | 6 | 하루 최대 업로드 수 |

---

## 사용법

### Runtime CLI (`blog.cmd`)

```batch
blog scheduler          스케줄러 시작 (메인 프로세스)
blog server             대시보드 서버 시작
blog status             현재 상태 확인
blog pipeline           파이프라인 단계 확인
blog content            콘텐츠 큐 확인
blog review             검수 대기 목록 확인
blog approve <id>       검수 승인
blog reject <id>        검수 반려
blog sessions           수동 어시스트 세션 목록
blog session <id>       세션 상세 확인
blog assist <url>       수동 어시스트 세션 시작
blog logs [n]           최근 로그 확인
blog analytics          분석 요약 확인
```

### Packaged CLI (`bw`)

```bash
python -m blogwriter.cli --help
bw init
bw write
bw shorts
bw publish
bw status
bw doctor
bw config show
```

---

## 대시보드

```batch
blog server
```

접속: http://localhost:8080

| 탭 | 기능 |
|----|------|
| Overview | 오늘 수집/발행/배포 현황 |
| Content | 글감 목록, 원고 검토, 수동 발행 |
| 수동모드 | URL 입력 → 커스텀 콘텐츠 반자동 제작 |
| Analytics | Search Console 성과, 수익 추이 |
| Novel | 소설 에피소드 관리 |
| Settings | AI 연결, 배포채널, 품질/스케줄, 비용관리 |
| Logs | 실시간 로그 조회 |

---

## YouTube Shorts 봇

블로그 글을 15~30초 세로 영상(9:16, 1080x1920)으로 자동 변환합니다.
FFmpeg만으로 조립하며 CapCut 등 별도 편집 도구가 필요 없습니다.

### 파이프라인

```
블로그 글
  STEP 0  Asset Resolution    에셋 소스 결정 (auto/semi_auto)
  STEP 1  Script Extraction   LLM으로 hook/body/closer 추출
  STEP 2  Visual Sourcing     스톡 영상 수집 + 캐릭터 오버레이
  STEP 3  TTS Generation      음성 합성 + 단어별 타임스탬프
  STEP 4  Caption Rendering   ASS 자막 (단어별 노란색 하이라이트)
  STEP 5  Video Assembly      FFmpeg 조립 + 루프 최적화
  STEP 6  YouTube Upload      Data API v3 업로드 + AI 공시 레이블
YouTube Shorts
```

### 생산 모드

| 모드 | 설명 |
|------|------|
| auto | 완전 자동, 무인 실행 |
| semi_auto | input/ 폴더 파일 우선 사용, 없는 항목만 자동 |

#### semi_auto 파일 규칙

```
input/scripts/{article_id}.json    LLM 건너뜀, 직접 작성한 스크립트
input/images/{article_id}_1.png    스톡 영상 대신 이미지 사용 (Ken Burns)
input/videos/{article_id}_1.mp4    스톡 영상 대신 이 클립 사용
input/audio/{article_id}.wav       TTS 건너뜀, 직접 녹음 음성 사용
```

처리된 파일은 input/_processed/ 로 자동 이동됩니다.

### TTS 엔진

| 순위 | 엔진 | 비용 |
|------|------|------|
| 1 | ElevenLabs | 유료 |
| 2 | Google Cloud TTS Neural2 | 유료 |
| 3 | Edge TTS ko-KR-SunHiNeural | 무료 |

API 키 없이 Edge TTS로 즉시 사용 가능합니다.

### Shorts CLI

```bash
python bots/shorts_bot.py                           eligible 글 자동 선택
python bots/shorts_bot.py --slug my-article         특정 글 지정
python bots/shorts_bot.py --dry-run                 렌더링만, 업로드 안 함
python bots/shorts_bot.py --upload path/video.mp4   기존 영상 업로드
```

---

## 멀티플랫폼 배포

| 플랫폼 | 스케줄 | 필요 키 |
|--------|--------|---------|
| Blogger | 09:00 | Google OAuth |
| Instagram 카드 | 10:00 | Instagram Graph API |
| Instagram 릴스 | 10:30 | Instagram Graph API |
| YouTube Shorts | 10:35, 16:00 | YouTube Data API v3 |
| X (Twitter) | 11:00 | X API v2 |
| TikTok | 18:00 | TikTok Content Posting API |
| YouTube (긴 영상) | 20:00 | YouTube Data API v3 |

---

## 소설 파이프라인

매주 월/목요일 09:00에 소설 에피소드를 자동 생성하고 블로그에 발행합니다.

```json
{
  "id": "my-novel",
  "title": "소설 제목",
  "genre": "SF",
  "setting": "2087년 서울...",
  "characters": [{"name": "주인공", "role": "탐정"}],
  "episode_length": 2000,
  "schedule": "mon,thu"
}
```

파일 위치: config/novels/{novel_id}.json

---

## 수동 어시스트 모드

특정 URL의 콘텐츠를 기반으로 반자동으로 콘텐츠를 제작합니다.

1. 대시보드 > 수동모드 탭에서 URL 입력
2. AI가 글 초안 + 이미지 프롬프트 생성
3. Telegram으로 프롬프트 수신 → ChatGPT/Midjourney로 이미지 생성
4. 생성된 이미지를 Telegram으로 전송 → 자동 조립 및 발행

---

## Telegram 명령어

### 기본 명령

| 명령어 | 기능 |
|--------|------|
| /status | 전체 현황 |
| /pending | 발행 대기 글 목록 |
| /approve [slug] | 발행 승인 |
| /reject [slug] | 거부 |
| /report | 성과 리포트 즉시 생성 |
| /topics | 오늘 수집된 글감 |
| /convert | 변환 엔진 즉시 실행 |

### Shorts 명령

| 명령어 | 기능 |
|--------|------|
| /shorts status | Shorts 현황 |
| /shorts mode auto or semi | 생산 모드 전환 |
| /shorts input | input/ 폴더 현황 |
| /shorts character bao or zero | 캐릭터 강제 지정 |
| /shorts upload [경로] | 영상 즉시 업로드 |
| /shorts skip [id] | 특정 글 Shorts 제외 |
| /shorts run | 즉시 실행 |

### 소설 명령

| 명령어 | 기능 |
|--------|------|
| /novel_list | 소설 목록 |
| /novel_gen [id] | 즉시 생성 |
| /novel_status | 파이프라인 현황 |

자연어로도 제어 가능합니다 (Claude API 연동 시):
"오늘 발행한 글 성과 알려줘", "AI 뉴스 주제로 글 써줘"

---

## 스케줄

| 시간 | 작업 |
|------|------|
| 07:00 | 트렌드 수집 |
| 08:00 | AI 글쓰기 |
| 08:30 | 변환 엔진 |
| 09:00 | 블로그 발행 |
| 10:00 | 인스타그램 카드 |
| 10:30 | 인스타그램 릴스 |
| 10:35 | YouTube Shorts 1차 |
| 11:00 | X(Twitter) |
| 16:00 | YouTube Shorts 2차 |
| 18:00 | TikTok |
| 20:00 | YouTube |
| 22:00 | 일일 성과 리포트 |
| 일요일 22:30 | 주간 성과 리포트 |
| 월/목 09:00 | 소설 에피소드 생성 |

---

## 엔진 추상화

| 기능 | 옵션 |
|------|------|
| 글쓰기 | openclaw (로컬, 무료) / claude / gemini / openai |
| TTS | edge_tts (무료) / google_cloud / elevenlabs |
| 이미지 | manual / openai (DALL-E) |
| 영상 | local (FFmpeg) / seedance / runway |

---

## 개발 현황

| Phase | 상태 | 내용 |
|-------|------|------|
| Phase 1A | 로컬 동작 확인 | 블로그 자동화 기본 파이프라인 |
| Phase 1B | 부분 구현 | Instagram, X 배포 모듈 존재, 운영 흐름 보강 필요 |
| Phase 2 | 부분 구현 | Shorts 변환 및 TikTok, YouTube 관련 코드 포함 |
| Shorts Bot | 로컬 검증 필요 | YouTube Shorts 자동 생산 파이프라인 |
| 대시보드 | 로컬 빌드 완료 | React + FastAPI 웹 대시보드 |
| 소설 파이프라인 | 코드 포함 | 자동 소설 연재 |
| 수동 어시스트 | 코드 포함 | 반자동 콘텐츠 제작 |

---

## Release Verification

로컬 릴리즈 체크리스트:

```bash
python -m pytest tests -v
python -m compileall blogwriter bots dashboard blog_engine_cli.py blog_runtime.py runtime_guard.py
cd dashboard/frontend && npm run build
```

---

## 라이선스

MIT License

---

The 4th Path — 22B Labs
AI 시대, 1인 미디어의 새로운 길
