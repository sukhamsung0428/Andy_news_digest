# 뉴스 다이제스트 봇 (Physical AI / AI 데이터센터 / Bitcoin)

매일 정해진 시간에 **주제별 영문 800자 + 국문 800자 요약**을 텔레그램으로 보내주는 봇입니다.
Google News RSS에서 영문·국문 기사를 모아 Gemini(무료 한도)로 요약하고, GitHub Actions로
서버 없이 무료 자동 실행됩니다.

```
Google News RSS (영문/국문)  ->  Gemini 요약(<=800자)  ->  Telegram 전송
                          (GitHub Actions가 매일 자동 실행)
```

---

## 준비물 3가지 (모두 무료)

### 1) 텔레그램 봇 토큰
1. 텔레그램에서 **@BotFather** 검색 → 대화 시작
2. `/newbot` 입력 → 봇 이름과 username 지정
3. 받은 **토큰**(예: `123456:ABC-DEF...`)을 복사 → 이게 `TELEGRAM_BOT_TOKEN`

### 2) 내 chat_id (요약을 받을 대화방)
가장 쉬운 방법:
1. 방금 만든 **내 봇과의 대화**에서 아무 메시지나 한 번 보냅니다(예: `hi`).
2. 브라우저에서 아래 주소를 엽니다(토큰 교체):
   `https://api.telegram.org/bot<토큰>/getUpdates`
3. 결과 JSON에서 `"chat":{"id": 숫자 ...}` 의 **숫자**가 `TELEGRAM_CHAT_ID`입니다.

> 대안: 텔레그램에서 **@userinfobot** 에게 말 걸면 본인 id를 바로 알려줍니다(개인 DM용 chat_id로 사용 가능).

### 3) Gemini API 키
1. **Google AI Studio** (aistudio.google.com) 접속 → 구글 계정 로그인
2. "Get API key" → 키 생성 (신용카드 불필요, 무료 한도 사용)
3. `AIza...` 로 시작하는 키를 복사 → 이게 `GEMINI_API_KEY`

---

## 배포 (GitHub Actions, 무료)

### 1) 저장소 만들기
GitHub에서 새 저장소(repository)를 만들고, 이 폴더의 파일을 그대로 업로드합니다.
폴더 구조는 반드시 아래처럼 유지하세요(`.github/workflows/` 경로 중요):

```
news-digest-bot/
├─ main.py
├─ requirements.txt
├─ README.md
└─ .github/
   └─ workflows/
      └─ digest.yml
```

### 2) 시크릿 3개 등록
저장소에서 **Settings → Secrets and variables → Actions → New repository secret** 로
아래 3개를 그대로 등록합니다(이름 철자 정확히):

| 이름 | 값 |
|------|-----|
| `GEMINI_API_KEY` | Gemini API 키 |
| `TELEGRAM_BOT_TOKEN` | 봇 토큰 |
| `TELEGRAM_CHAT_ID` | chat_id 숫자 |

> 키는 코드에 직접 적지 말고 반드시 시크릿으로만 넣으세요. 코드는 시크릿을 읽어 씁니다.

### 3) 바로 테스트
**Actions 탭 → News Digest → Run workflow** 버튼으로 즉시 한 번 실행해 보세요.
잠시 후 텔레그램으로 3개 메시지(주제별)가 오면 성공입니다.

### 4) 자동 실행 시간 조정
`.github/workflows/digest.yml` 의 `cron` 값으로 정합니다. **cron은 UTC 기준**이에요.

| 원하는 한국시간(KST) | cron (UTC) |
|----------------------|------------|
| 매일 08:00 | `0 23 * * *` (기본값) |
| 매일 20:00 | `0 11 * * *` |
| 하루 2번(08:00·20:00) | 두 줄 모두 추가 |

---

## 커스터마이징

`main.py` 상단만 고치면 됩니다.

- **주제 추가/변경**: `TOPICS` 리스트 수정. 형식은
  `("표시이름", "이모지", '영문검색어', "국문검색어")`.
  예) 엔비디아 추가 → `("NVIDIA", "💚", "NVIDIA", "엔비디아"),`
- **요약 글자 수**: `CHAR_LIMIT = 800` 값을 변경
- **기사 수집 개수**: `ARTICLES_PER_FEED = 8`
- **AIDC 검색어**: 기본은 `"AI data center"` / `"AI 데이터센터"`.
  다른 의미(예: 자동인식·데이터캡처)면 검색어를 바꾸세요.

---

## 참고 / 주의

- **무료 한도**: Gemini 무료 티어는 모델당 대략 분당 10회·하루 500회 수준입니다.
  하루 6개 요약이라 여유롭습니다.
- **요약 품질**: RSS 제목을 모델이 "직접 문장으로 종합"합니다(원문 복붙 아님).
  더 깊은 요약을 원하면 기사 본문 수집 단계를 추가할 수 있어요.
- **GitHub Actions 일정**: 예약 작업은 서버 부하에 따라 몇 분 지연될 수 있고,
  저장소가 60일 이상 활동이 없으면 예약 실행이 비활성화됩니다.
  가끔 수동 실행(Run workflow)하거나 커밋하면 계속 활성 상태로 유지됩니다.
- **로컬 테스트**(선택): 터미널에서도 돌려볼 수 있습니다.
  ```bash
  pip install -r requirements.txt
  export GEMINI_API_KEY=...   TELEGRAM_BOT_TOKEN=...   TELEGRAM_CHAT_ID=...
  python main.py
  ```
