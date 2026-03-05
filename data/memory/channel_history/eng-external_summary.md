# eng-external (C05JQPUNYTT) 채널 히스토리 요약

> 마지막 동기화: 2026-02-26
> 총 메시지 수: 23건 (실질 메시지 약 12건, 나머지 입퇴장/봇 메시지)
> 기간: 2023-07-24 ~ 2026-02-24

---

## 채널 개요

외부 개발 파트너와의 협업을 위한 채널. Stargate API 관련 외부 개발자 협업 및 Pylon/USIO 관련 업무 배정에 사용. 전체적으로 활동량이 매우 적다.

---

## 2023-Q3 (7월~9월)

### 주요 주제
- **Stargate API 팀/유저 관리 스펙 공유**
  - `GET /user/{user_id}/teams`, `GET /team/{team_id}`, `GET /team/{team_id}/members`
  - `PATCH /team/{team_id}/members/{user_id}` (admin 속성 변경), `PATCH /team/{team_id}` (팀 이름 변경)
  - rinmin2가 `/user/{user_id}/teams` -> `/user/me/teams`로 엔드포인트 변경 제안 후 반영
- **Jest 테스트 프레임워크 도입**: supertest를 활용한 API 요청 테스트 구성
- **Jest globalSetup 공유 이슈**: 샌드박스 제약으로 인해 병렬 테스트 스위트 간 app 인스턴스 공유 불가 확인 (Jest issue #7184 참조)
- **Swagger 문서 자동 생성 문제 해결**: 덕현님이 해결 방법 발견

### 주요 참여자
- 김덕현 (Dekay): 프로젝트 리드, API 스펙 정의, PR 머지, 기술 가이드
- rinmin2: 외부 개발자, API 엔드포인트 개발 및 PR 제출

### 주요 결정
- `/user/me/teams` 형태로 API 엔드포인트 변경
- Jest + supertest 기반 API 테스트 도입

### 주요 이벤트
- 07-24: 채널 생성, rinmin2 초대 및 Stargate API GitHub 리포 공유
- 07-25: 첫 PR 제출
- 08-01: Jest 글로벌 상태 공유 이슈 최종 보고
- 10-21: rinmin2 채널 퇴장

---

## 2024-Q2~Q3 (4월~9월)

### 주요 주제
- **Pylon USIO 파일 업로드 암호화 에러 처리 (STM-1211)**
  - USIO를 통한 파일 업로드 시 암호화된 파일의 에러 핸들링 구현 필요
  - USIO API 호출 전 사전 확인 또는 에러 메시지 기반 후처리 방식 검토
- **USIO Encrypted 오탐 버그 (STM-1212)**
  - 암호화되지 않은 파일이 Encrypted로 잘못 감지되는 USIO 자체 버그
  - USIO 팀에서 인지 후 수정 대기 중이나, 자체 원인 파악도 병행
- **USIO PDF 대용량 파싱 성능 이슈 (STM-1218)**
  - PDF 1,000페이지 문서 파싱에 약 8분 소요
  - 복수 건 동시 요청 시 온프렘 쿠버네티스 USIO API 서버 stuck/메모리 릭 발생
  - 한화생명 문서 처리가 주요 대상

### 주요 참여자
- Sigrid Jin / Jin Hyung Park: 업무 배정 및 기술 컨텍스트 제공
- Cheonseong Kang: USIO 관련 작업 담당자

### 주요 결정
- USIO 자체 버그 수정 대기 + 자체 사전 원인 파악 병행
- USIO API 성능 이슈 원인 조사 작업 Cheonseong Kang에게 배정

---

## 2025-Q3 ~ 2026-Q1

실질적 활동 없음. 봇 계정 입장 기록만 존재:
- 2025-07-24: Notion AI 참여
- 2025-11-16: ai-crawler 참여
- 2026-02-24: Storm-Clawd 참여
