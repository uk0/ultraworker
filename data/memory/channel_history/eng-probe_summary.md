# eng-probe (C0647GT3MK7) 채널 히스토리 요약

> 마지막 동기화: 2026-02-26
> 총 메시지 수: 236건 (봇/입퇴장 제외 약 200건)
> 기간: 2023-11-05 ~ 2026-02-24
> 이전 채널명: gen-img-develop (2023-12-06에 eng-probe로 변경)

---

## 채널 개요

이미지 학습/생성 프로젝트 "Probe" 개발 채널. 뤼튼(Wrtn)과의 AI 프로필 사진 생성 서비스 협업이 핵심 프로젝트. Stable Diffusion 기반 학습/추론 파이프라인을 구축하고, RunPod GPU 클라우드에서 운영. 외부 개발 파트너(김수원)도 참여. 2024년 Q2 이후 활동 급감.

---

## 2023-Q4 (11월~12월) -- 101건

### 주요 주제

**프로젝트 초기 세팅 (11월 초)**
- Stable Diffusion 기반 이미지 학습/생성 시스템 구축 시작
- 핵심 리포지토리: `sionic-ai/gen-img`, `sionic-ai/kohya_ss`, `sionic-ai/deepfake`
- kohya_ss 기반 학습 코드(`training_sionic.py`), AUTOMATIC1111 WebUI 기반 추론 코드
- 전처리: 얼굴 변경(deepfake), 다수 얼굴 탐지, 저품질 사진 제거

**외부 개발자 온보딩 (11월 초)**
- 김수원(swkim0512) 외주 개발 참여
- 요구사항/스펙 문서 요청, 학습 요청 서버 기능 정의

**뤼튼 협업 시작 (11월 중순)**
- NDA 기반 초기 실험 결과물 Maeve님에게 전달
- Wrtn & Sionic AI 공동 Slack 워크스페이스 생성 (11/15)
- 뤼튼 API 요청/응답 컨벤션 정의 (11/29)

**학습 인프라 구축**
- RunPod GPU 클라우드 (A6000) 활용, Docker 기반 학습 환경
- A6000 RunPod 컨테이너 shim/OCI 런타임 에러 발생
- 학습 파라미터 최적화: Cosine Annealing LR 스케줄러 적용
- xformers 0.0.23 릴리즈 반영 검토
- 학습 종료 조건 모델링: arcface 코사인 거리, 얼굴 회전/크기/품질 기반 필터링

**추론 서버 구성**
- worker2 서버 GPU(14.52.68.81:8081/8082)에서 img2img API 제공
- 이미지 base64 인코딩 방식 페이로드 전달
- SD XL 1.0 + ESRGAN_4x 업스케일러 테스트

**아키텍처 설계 (12월)**
- TO-BE 구조도 작성 (김덕현)
- SQS 기반 학습 큐 시스템: 덕현님이 SQS 밀어넣기, 수원님이 DB 기록 + pod 생성
- GCP Cloud Run + Cloud SQL 기반 API 서버
- Probe 리팩토링 이슈 정리 (12/01)
- 클라우드 비용 산출 (GCP 스토리지 포함)
- Grafana 모니터링 보드 구축 (Sigrid Jin)

**Pod Provisioning 정책 논의 (12월 중순)**
- 요청 대비 Pod 수 조절 전략: 배치 vs 1:1 생성 트레이드오프
- 뤼튼 베타 서비스 2~3만 고객 대상 배치 처리 계획

**뤼튼 라이브 서비스 시작 (12/30)**
- 학습 요청 본격 유입, 시간당 약 $150 RunPod 비용 발생
- RunPod 잔액 관리: 초기 $1,500 -> $2,500 추가 예치
- SQS pulling 시 빈 request에 대한 504 에러 + 잘못된 JSON 반환 문제 발생 및 3시간 점검
- Locust 부하 테스트 실시 (12/31)

### 주요 참여자
- Noah (고석현): 모델 학습 파라미터 최적화, GPU 서버 관리, RunPod 비용 관리 (26건)
- 송명하: 학습/추론 서버 개발, Docker 빌드, 라이브 배포, 비용 산출 (29건)
- 김덕현 (Dekay): API 설계, 아키텍처, 뤼튼 커뮤니케이션 (19건)
- Sigrid Jin (박진형): Grafana 모니터링, RunPod 핫라인, 비용 분석, 라이브 운영 (22건)
- swkim0512 (김수원): 외주 개발, 진행상황 API 구현 (4건)

### 주요 결정
- SD + LoRA/LoCon 기반 학습 파이프라인 확정
- RunPod GPU 클라우드 + SQS 큐 기반 비동기 학습 시스템
- GCP Cloud Run + Cloud SQL 기반 API 서버 아키텍처
- 12/30 뤼튼 라이브 서비스 런칭

### 주요 이벤트
- 11/05: 채널 생성, 프로젝트 킥오프
- 11/06: 외부 개발자 김수원 온보딩
- 11/15: 뤼튼 x Sionic AI 공동 워크스페이스 생성
- 12/06: 채널명 gen-img-develop -> eng-probe 변경
- 12/21: Grafana 모니터링 보드 공개
- 12/28: RunPod 핫라인 다수 이슈 발생
- 12/30: 뤼튼 라이브 서비스 시작

---

## 2024-Q1 (1월~3월) -- 101건

### 주요 주제

**V2 모델 개발 (1월~2월)**
- ComfyUI 기반 새로운 추론 파이프라인으로 전환
- 인물 모델 v2: LoRA -> LoCon 전환, Cosine Annealing 적용, inswapper_128 얼굴 swap + inpaint
- 펫 스튜디오(Pet Studio) 모델 개발: 강아지 대상 AI 프로필 사진 생성
- Comfy Json 규격화 문서 작성 (정세민)
- Outfit Anyone Fit 구현 검토
- arcface 임베딩 기반 토픽 생성 및 대표 이미지 선정 (Noah)
- 모델 파일 용량 92% 감소 (2,000MB -> 150MB)

**비용 최적화**
- 추론 API 원가 50~60% 절감 시도 (버그 해결 기반)
- A100 PCIe -> SXM 전환 원가 검토
- GCP Cloud Storage 비용 1월 15일 이후 100% 상승 이슈
- Inference Pod 다이어트 테스트
- GCP Postgres DB 스펙 다운사이징: vCPU 8->2, mem 32GB->8GB
- DB 커넥션 풀 max 100 -> 10으로 축소 검토

**뤼튼 정식 버전(시즌2) 출시 준비 (1월 말~2월)**
- 1/31 베타 종료, 2월 설 연휴 전 정식 출시 목표
- 서비스 변경: 매일 -> 1주 주기, 4장 -> 3장 생성
- 가격: 10장 업로드 20장 생성 6,600원

**운영 이슈 대응**
- 1/24 트레이닝 큐 40개 적체 문제 발생 및 해결
- max_pod_num 동적 설정 (큐 숫자 기반)
- pod_info 테이블 개선 및 auth_info_id 실효성 논의
- 인퍼런스 유사도 품질 이슈 (뤼튼 측 지속 문의)
- 인퍼런스 Pod 수동 증설 운영 노티 체계

**RunPod 관리**
- RunPod 콜 (01/03): 2024 상반기 로드맵 공유 (Q1 CPU instance, Q2 object storage/docker registry)
- OOM 이슈 시 pod ID 태그 후 Discord 문의
- 런팟 잔액 모니터링: $719 남음, 시간당 $11.44 지출 (01/14 기준)

**비즈니스**
- 펫 모델 비용 단가 산정 논의 (기존 인물 모델 단가 산정 로직 참조)
- Stability AI Japan 협업 검토 (뤼튼 주도)
- 뤼튼 측 모델 비용 미팅 (01/19)

**기술 리서치/도구**
- ComfyUI-Manager, ComfyScript, ComfyUI-Launcher 등 도구 탐색
- pyinstruments 프로파일링으로 10 RPS 정상, 200 RPS 시 30% failure 확인
- litegraph.js (비주얼 프로그래밍)
- Open-Sora (AI 영상 생성) 모니터링

**Probe Tech Spec 도입 (1월 말)**
- Storm 제품군과 동일한 Tech Spec 양식 사용 시작
- Probe Product Spec 노션 페이지 생성

### 주요 참여자
- Sigrid Jin (박진형): V2 API 명세, 비용 분석, 스프린트 관리, ComfyUI, RunPod 관리 (44건)
- hhhssw: 뤼튼 비즈니스 커뮤니케이션, 출시 일정, 비용 협상 (17건)
- Noah (고석현): arcface 연구, 모델 최적화, GPU 관리 (13건)
- 송명하: 인프라/DB 관리, 라이브 배포, 학습 서버 운영 (12건)
- 정세민 (Sem): V2 모델 리서치, ComfyUI 워크플로우, Pet Studio (10건)
- 김덕현 (Dekay): API 개발, 프로덕트 스펙, Jira 스프린트 (5건)

### 주요 결정
- ComfyUI 기반 V2 추론 파이프라인 전환
- 펫 스튜디오 모델 추가 개발 및 출시
- 정식 버전 가격: 6,600원 (10장 업로드 20장 생성)
- DB 스펙 다운사이징으로 비용 절감
- Probe Tech Spec 양식 도입

### 주요 이벤트
- 01/03: RunPod 콜 - 2024 로드맵 공유
- 01/08: Jira 스프린트 체계 도입 (PROB 보드)
- 01/09: 얼굴 모델 v2 리서치 공유
- 01/14: 런팟 잔액 $719, 수요일 오전까지 버틸 수 있음
- 01/19: 뤼튼 모델 비용 미팅
- 01/30: Probe Tech Spec 노션 페이지 생성
- 02/05: 설 전 신규 버전 릴리즈 준비 미팅
- 03/04: Probe 데모 관련 정리

---

## 2024-Q2 (4월~6월) -- 2건

### 주요 주제
- **AI 영상 생성 기술 트렌드 공유**: Higgsfield, Diffuse, fal.ai 등 신규 영상 생성 기술 모니터링
- 채널 활동 급감 -- 프로젝트 안정화 또는 방향 전환 시사

### 주요 참여자
- Sigrid Jin: 기술 트렌드 링크 공유

---

## 2024-Q3 (7월~9월) -- 1건

### 주요 주제
- **과금 데이터 정리**: 뤼튼 서비스 시작일을 12/28로 확인 (사이오닉 타임라인 정리 중)

### 주요 참여자
- 김덕현 (Dekay)

---

## 2025-Q3 ~ 2026-Q1

실질적 활동 없음. 봇 계정 입장 기록만 존재:
- 2025-07-24: Notion AI 참여
- 2025-11-16: ai-crawler 참여
- 2026-02-24: Storm-Clawd 참여
