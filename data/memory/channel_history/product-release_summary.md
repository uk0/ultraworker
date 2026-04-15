# product-release (C06DDJKKJPQ) - 제품 릴리즈 노트 채널 요약

> 채널 기간: 2024-01-12 ~ 현재 (활성)
> 총 메시지: 660건
> 주요 참여자: shinhs2009(신희수), 김덕현(Dekay), Sigrid Jin(진형), 백은주(eunchu), 권혜선(jada-gwon), 강성우(Claude kang), 김수원(mmmhoj), 박지원(juwon5272), BanseokSuh(서반석), kozistr833(형찬), 조하담(Joy), 최병현(Hyune-c)
> 채널 목적: 프로젝트 단위 production 배포 현황을 공유하는 릴리즈 노트 채널

---

## 2024-Q1 (1월~3월): 초기 릴리즈 체계 구축

### 주요 릴리즈
- **Stargate 0.4.5 ~ 0.6.6**: 카카오톡 연동, SSE 기능, i18n 적용, 피드백 기능, 문서 업로드 개선
- **Probe Service 0.1.0 ~ 0.1.4**: 뤼튼 V2 여성/남성 및 Pet Studio 서비스 (이미지 생성)
  - Cloud Run 배포, API_KEY 접근 제어, 학습 Pod 자동 스케일링
- **Pylon 0.6.0 ~ 0.7.0**:
  - Context 정보 Answer response에 포함
  - GPT-4-0314 지원
  - Advice data API 개발
  - 문서 파싱 라이브러리(unstructured) 버그 대응
  - 할루시네이션 방지 프롬프트 수정
- **Analyze Test 데모**: 데모페이지 배포 (변경된 API 구조 반영)

### 주요 인프라 변경
- 임베딩 서버 Nonce -> Runpod로 이전
- Stargate: CloudRun -> AWS ECS 전환 (Terraform)

---

## 2024-Q2 (4월~6월): 핵심 기능 고도화

### 주요 릴리즈
- **Pylon 0.9.0 ~ 0.11.0**:
  - Storm Write 프롬프트 변경
  - 새로운 임베딩 모델 도입 (Qdrant migration)
  - 새로운 RAG 로직 개발
  - GPT-4-turbo 지원 (Answer 비용 3~4배 절감)
  - Feedback template/prompt 도입
  - Trust score 계산 로직 도입
- **Stargate API 0.9.0 ~ 0.18.0**:
  - 피드백 CRUD
  - 레시피 설정 기능
  - RAG on/off 기능
  - 파일 업로드 100MB 제한
  - Slider 컴포넌트
  - Chat stream 버퍼링 로직
- **Stargate Web 0.9.0 ~ 1.6.4**: 피드백 UI, RAG on/off, 디자인시스템 컴포넌트 다수 개발

### 주요 결정
- 형찬(kozistr833)의 활발한 Pylon 배포 (거의 매주 배포)
- 피드백 시스템 프로덕션 배포 완료

---

## 2024-Q3 (7월~9월): Carrier 연동 및 안정화

### 주요 릴리즈
- **Pylon v1.2.0 ~ v1.3.0**:
  - MidM streaming 지원
  - Authentication token 추가
  - Reranker 모듈 분리
  - Open LLM 모듈 추가
  - 새 임베딩 모델(bge-m3) 도입
  - Storm Parse 기능 추가
  - Contexts API 리팩토링
- **Stargate API v0.19.0 ~ v0.28.0**:
  - Agent 생성시 recipe 지정 가능
  - 문서 관리 개선 (bulk 삭제, 정렬)
  - Carrier 연동 (주문서 기반 워크플로우)
  - Chat 로깅 시스템 개선
  - API key 관리 기능
  - Storm Parse 콘솔 연동
- **Stargate Web 1.6.0 ~ 1.13.3**:
  - 로그인 API 변경
  - 레시피/LLM 설정 UI
  - Chat 상세 로그 뷰어
  - 대시보드 기능 추가
- **Carrier 첫 배포**: Carrier MVP 개발 완료 및 배포

### 주요 인프라 변경
- Cohere API -> AWS Bedrock (Japan Region) 전환
- 신규 임베딩 모델 도입 (bge-m3)

---

## 2024-Q4 (10월~12월): 회원가입 및 파스 기능

### 주요 릴리즈
- **Pylon v1.4.3 ~ v1.5.5**:
  - Cohere Embed 메모리 누수 수정
  - 청크 머징 최대 글자수 3000자로 확장
  - Pylon 리팩토링 1차
  - Cohere API -> AWS Bedrock 전환
  - Qdrant 검색 batch operation 개선
  - Storm Parse JSON 호환 작업
- **Stargate API v0.29.0 ~ v0.33.5**:
  - Chat log 이벤트 타입 추가
  - 팀별 에이전트 관리
  - 워커/매니저 삭제 기능
  - 회원가입 SLA 적용
  - Storm Parse 관련 기능
  - QA 결과 구현
- **Stargate Web 1.13.4 ~ 1.15.0**:
  - 회원가입 기능 (가입 링크는 숨김 처리)
  - JSON 뷰어 (상세 로그)
  - 마크다운 렌더링
  - 파일 업로드 용량 제한 완화
  - 에이전트 이름 특문 허용 및 글자수 제한 변경

### 주요 결정
- 회원가입 기능 단계적 오픈 (링크 숨김 처리)

---

## 2025-Q1 (1월~3월): Storm Parse 및 국제화

### 주요 릴리즈
- **Pylon v1.5.6 ~ v1.6.0**:
  - Storm Parse JSON 호환
  - 헬스체크 엔드포인트 수정
  - 특정 문서의 모든 청크 반환 API 추가
  - BGE-M3 + BGE-M3-Reranker-v2 통합 적용 (한국어/영어/다국어)
- **Stargate API v0.33.6 ~ v0.36.0+**:
  - 만료된 API key 카카오톡 차단
  - QA 결과 구현
  - Redis scan 버그 수정
  - Schema version 관리
  - Order Sheet CRUD API
  - Carrier 연동 고도화
- **Stargate Web 1.16.0 ~ 1.18.0+**:
  - 태국어 추가
  - Storm Parse UI 연동
  - LLM 설정 temperature/topP 기본값 변경
  - Vercel Web Analytics 연동
  - 회원가입 약관 한국어 전용
  - 유진 데모 화면 구성 (회의록 생성)
- **Carrier 1.0.1 ~ 1.1.0**:
  - 후처리 노드 마지막 노드 플래그 추가
  - Storm Parse 캐리어 내재화

### 주요 인프라 변경
- 모든 언어 에이전트 BGE-M3 통합 사용

---

## 2025-Q2 (4월~6월): 워크플로우 UI 및 자동화 릴리즈

### 주요 릴리즈
- **Stargate API v0.36.12 ~ v0.38.6**:
  - 팀 스크리닝(screening) 기능 구현
  - 문서 사용량 카운팅 (document usage)
  - 에이전트 월별 API 호출수 기능 추가
  - JWT payload에 team_id 추가
  - Advice 관련 엔드포인트 구현
  - 문서 업로드 완료 엔드포인트 추가
  - 오더시트(order sheet) snake_case 변환
- **Stargate Web v1.20.3 ~ v2.28.1** (대규모 버전 점프):
  - 학습 데이터 품질 상태 SSE 업데이트
  - 사이트별 설정 파일 분기 처리
  - PSI Lense PDF 뷰어
  - 워크플로우 페이지 구현 (다이어그램, JSON 에디터, 노드 프로퍼티)
  - 피드백 벌크 업로드/단건 등록/수정/삭제 기능
  - 오더시트 JSON 편집기 (검색/치환 기능)
  - 가이드 문서 Oopy로 교체
  - FSD(Feature Sliced Design) 파일구조 변경
  - 온프렘 빌드 가이드 작성
  - GitHub CI/CD 워크플로우 정상화
- **Pylon v1.8.0 ~ v1.9.1**:
  - Overmind 지원 (Late Chunking 클라이언트)
  - 청크 사이즈 2배 확대 (문서 1~10번)
  - 중복 청크 제거 로직 (머징 이슈 해결)
  - Pre-Retrieval Top-K 기능
  - Sparse Vector(BGE-M3-Splade) 검색 지원
  - 머징 파이프라인 전면 개편 및 레시피 머징 추가
  - 복수 GraphRAG 엔진 연결 기능
  - LightRAG Graph 자연어 재작성 기능
  - 웹 검색(Beta) 이스터에그 (외부 웹 결과 RAG 통합)
  - GraphRAG context API 하드코딩 (아이센틱 POC용)
  - uvicorn worker 4개 + CPU 4코어 설정
- **Carrier v1.2.1 ~ v1.4.1**:
  - Storm Parse VLM 반복 감지 및 재시도
  - Storm Parse 프롬프트 외부 작성 기능
  - 병렬처리 로직 추가
  - ifelse 노드 elseif 기능 추가
  - Storm Parse S3/minio 지원
  - 오더시트 리팩토링
  - Storm Parse 반복로직 제거

### 주요 변화
- **릴리즈 자동화**: GitHub 릴리즈 webhook 연동으로 자동 Slack 알림 도입
- **프론트엔드 리브랜딩**: "STARGATE-WEB"에서 "FRONTEND"로 명칭 변경 (일시)
- **신규 기여자**: BanseokSuh(서반석), 권혜선(Jada Gwon), 강성우(Claude kang)
- **배포 속도**: 거의 매일 배포 (Web 기준 v1.20 -> v2.28, 약 50+ 릴리즈)

---

## 2025-Q3 (7월~9월): 골든청크 및 STORM APIs

### 주요 릴리즈
- **Stargate API v0.39.0 ~ v0.41.5**:
  - 골든 청크(golden chunks) 기능 구현
  - Auxiliary Feedback 지원
  - 변수 노드(variable node) 구현
  - 캐시 설정 기능
  - STORM APIs 통합 (storm-apis integration)
  - 플랫폼 어드민 기능
  - 팀 계정 테이블 추가
  - timezone 시스템 설정 추가
  - 문서 dhash 인덱스 최적화
  - 지식 베이스 없이 API 응답 허용
- **Stargate Web v2.29.0 ~ v2.47.0**:
  - 워크플로우 노드 드래그 앤 드롭
  - 유효 청크/출처 표시 기능
  - 결제 페이지 구현
  - STORM APIs 전용 사이드바/대시보드/크레딧/API키/Playground 페이지
  - 커스텀 변수 선언/추가/삭제/수정 기능
  - LLM 노드 커스텀 모델/펑션콜 기능
  - 워크플로우 테스트 패널
  - 모델 파인튜닝 페이지
  - 일본어 회원가입 약관
  - 스톰파스 기본 파서로 전환
  - PDF 뷰어 버전업 및 objectFitMode
- **Pylon v1.10.0 ~ v1.12.0**:
  - 오버랩 처리 청크 확장 로직 개선
  - STORM JSON 파싱용 로컬 Transformer 도입
  - OTEL 추적 데코레이터 (Telemetry 강화)
  - Gemini 임베딩 클라이언트 구현 (gemini-embedding-001)
  - 컨텍스트 기반 검색(Contextual Retrieval) 시스템
  - Gemini 캐싱 메커니즘
  - IBK 멀티턴 대화 속도 개선
  - 검색 응답 속도 약 2배 향상
  - Listwise Reranker & Pointwise Reranker 앙상블
- **Carrier v1.4.2 ~ v1.4.6**:
  - 청크 판단 로직 추가
  - 엑셀 처리 기능 (Phase 2)
  - 변수 노드 개발
  - ifelse NULL_OR_EMPTY 조건 수정
  - 엑셀 엣지 케이스 대응

### 주요 결정
- STORM APIs 별도 제품으로 분리 (API 기반 서비스)
- 워크플로우 편집기 대대적 고도화
- Gemini 임베딩 모델 도입으로 임베딩 옵션 다양화

---

## 2025-Q4 (10월~12월): MS Teams 연동 및 워크플로우 v2

### 주요 릴리즈
- **Stargate API v0.42.0 ~ v0.43.3**:
  - MS Teams 연동 (channels_msteams 테이블, HMAC 검증)
  - OpenAI 호환 엔드포인트 초안 구현
  - 실행 로그(execution log) Phase 1 구현
  - 문서 facade 구현 및 converted 파일 핸들링
  - Storm/text 노드 추가
  - 구독(subscription) 노트 필드 추가
  - 어드민 핸들러 확장
  - 오더시트 노트 기능
  - Carrier v2 표준 에러 처리 적용
- **Stargate Web v2.48.0 ~ v2.92.1**:
  - 팀 선택기 회사명(corporate name) 표시
  - 모델 파인튜닝 세팅 구현
  - STORM APIs 크레딧 결제/사용기록/할인 배너
  - If/Else 노드 편집 폼 (중첩 조건, JSON 모드)
  - 변수 할당 노드 기능 (타입별 연산자, 커스텀 변수 패널)
  - Function 노드 (커스텀 코드 실행)
  - 예상 비용 계산기
  - MS Teams 채널 관리 UI (폼, API 연동, 팀 링크)
  - 워크플로우 리비전(revision) 기능
  - 실행 로그 UI (노드별 상세로그, SSE/API 연동)
  - 한글/엑셀 파일 스톰파스 PDF 뷰어 출력
  - JP Cluster Live Profile 배포 파이프라인
  - Sentry 추적 글로벌 에러 컴포넌트
  - 소스맵 비활성화 (메모리 이슈 대응)
  - 노드 복사 기능
  - 모바일 화면 회원가입 지원
- **Pylon v1.12.3 ~ v1.13.0**:
  - 소형 문서(8KB 이하) MIME Type 추출 문제 해결
  - LogicRAG 적용 파라미터 추가 (이스터에그)
  - MUVERA (vllm-muvera, bge-m3) 앙상블 임베딩
  - Pre-expand 배치처리 속도 개선
  - 임베딩/리랭커 레시피 YAML 관리
- **Carrier v1.4.7 ~ v1.5.3**:
  - Function 노드 추가
  - 재귀 호출 기능
  - Text 노드 추가
  - 에러 정의 추가 및 에러 응답 변경
  - 골든청크 on/off 플래그
  - 좀비 커넥션 풀 정리
  - 링크 레이스 컨디션 수정

### 주요 변화
- **MS Teams 연동**: Slack 외 Teams 채널 지원 시작
- **워크플로우 v2**: 소프트블록, 리비전, 실행 로그 등 대규모 업그레이드
- **신규 기여자**: juwon5272(박지원), hyeonnnnnnnn(김현), MyoungHaSong(송명하-캐리어)
- **storm-apis 레포**: 최병현(Hyune-c)이 GitHub releases 구독 설정
- **배포 속도**: Web만 약 45+ 릴리즈 (거의 매일 배포)

---

## 2026-Q1 (1월~2월): 실행 로그 고도화 및 안정화

### 주요 릴리즈
- **Stargate API v0.43.4 ~ v0.43.7+**:
  - 노드별 result 추출 구현 (RAG, API Call, Post, Text, LLM, Variable)
  - 토큰 사용량(token usage) 필수 검증
  - 실행 상태(node_execution_status) 처리
  - ifelse 노드 displayIdx 추가
  - 후처리 노드 실행 결과 저장 수정
- **Stargate Web v2.93.0 ~ v2.100.0+**:
  - 실행 로그 노드별 상세 구현 (LLM, 변수할당, API, 후처리/펑션, 검색, 응답 노드)
  - 워크플로우 리팩토링 및 소프트블록 구현
  - 워크플로우 JSON 필드 소프트블록
  - 응답 노드(텍스트 노드) 구현
  - HWP 파일 업로드 제한/원복 (폴라리스 라이선스 이슈)
  - 플레이그라운드 파일명 말줄임 표시
  - TXT 확장자 추가
  - 검색/LLM 노드 Placeholder 문구
- **Carrier v1.5.2+**:
  - RAG 노드 rag_context true 제거

### 주요 변화
- **실행 로그 완성**: Phase 1-1 이후 노드별 상세 로그 전면 구현
- **폴라리스 라이선스 이슈**: HWP 업로드 일시 제한 후 원복
- **GitHub 릴리즈 알림**: storm-apis 레포 추가 구독
- **JP 배포 파이프라인**: 일본 클러스터 독립 배포 안정화

---

## 릴리즈 주요 컴포넌트 정리

| 컴포넌트 | 설명 | 주요 담당자 |
|----------|------|------------|
| Stargate API | 백엔드 API 서버 | shinhs2009(신희수), 김덕현(Dekay), BanseokSuh(서반석) |
| Stargate Web | 프론트엔드 웹 | 백은주(eunchu), 권혜선(jada-gwon), 박지원(juwon5272) |
| Pylon | RAG/임베딩/LLM 엔진 | 강성우(Claude kang), Sigrid Jin(진형) |
| Carrier | 워크플로우 실행 엔진 | 김수원(mmmhoj), Sigrid Jin(진형) |
| Probe Service | 이미지 생성 서비스 (뤼튼) | 송명하, Sigrid Jin |
| Storm Parse | 문서 파싱 서비스 | Carrier 내재화 (김수원) |
| Storm APIs | API 기반 서비스 플랫폼 | 최병현(Hyune-c), 신희수 |

## 버전 이력 요약

| 컴포넌트 | 시작 버전 | 최신 버전 (2026-02 기준) |
|----------|----------|---------------------|
| Stargate API | 0.4.5 | 0.43.7+ |
| Stargate Web | 0.5.0 | 2.100.0+ |
| Pylon | 0.6.0 | 1.13.0+ |
| Carrier | 1.0.0 | 1.5.3+ |
