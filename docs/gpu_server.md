# UNIST Dumbo HPC (GPU) 사용 정보 — AICP 2026

> 재파인튜닝·대량 처리 때 사용. 지금 검증 단계는 노트북 CPU로 충분(불필요).
> 근거: UNIST Dumbo HPC User Guide v10. 사용기간 ~12/31.

## 접속

```
DNS:      dlogin01.usc.unist.ac.kr   (IP 10.0.7.61)
SSH Port: 2123
계정:      aicp419   (팀 공용, 500GB)
접속:  ssh -p 2123 aicp419@dlogin01.usc.unist.ac.kr
```

- ⚠️ **UNIST 외부에서 접속 불가** — 캠퍼스 네트워크 또는 VPN 필요.
- 최초 로그인 후 **비밀번호 변경 필수** (`passwd`). 9자+영숫자특수, 3개월마다.
- `/home`은 전 노드 공유(GPFS). 스크래치 없음 → 홈에서 작업.

## 하드웨어 / partition

| partition | GPU | wall time | 용도 |
|---|---|---|---|
| `gpu_v100` | V100 (1노드, 최신·빠름) | 24h | 추론·짧은 학습 |
| `gpu_p100` | P100 (5노드) | 72h | 일반 학습 |
| `gpu_k80` | K80 (13노드) | 120h | 장시간 학습 |

- 각 GPU 노드 64GB 메모리. CUDA 10.2.

## 소프트웨어 (핵심)

- **conda/pytorch 모듈 이미 설치됨** → `module load conda/pytorch` (환경 구축 쉬움)
- 개인 환경 필요 시(최신 transformers 등):
  ```
  source /apps/application/miniconda3/etc/profile.d/conda.sh
  conda create -n fomc python=3.10 && conda activate fomc
  pip install torch transformers
  ```

## SLURM 기본 명령

```
sbatch scripts/run_gpu.sh    # 작업 제출
squeue -u aicp419            # 내 작업 상태
scancel <JobID>              # 작업 취소
sinfo                        # 노드/partition 상태
```

→ 로그인 노드에서 직접 무거운 계산 금지. **반드시 sbatch로 제출**.

## 우리 프로젝트 작업 스크립트

`scripts/run_gpu.sh` 참조 (저장소에 포함). 접속 후 `sbatch scripts/run_gpu.sh`.
코드는 GPU 자동감지(`engine/sentiment.py`: cuda 있으면 GPU, 없으면 CPU) → 수정 없이 GPU 사용.

## 공용 계정 운용 규칙

```
· 환경 세팅은 한 명이 한 번 → 팀 공유 (각자 반복 X)
· 팀원별 폴더:  /home/aicp419/jaewon/, .../teammate/
· 모델·데이터:  /home/aicp419/shared/ 에 한 번만 (500GB 아끼기)
· GPU 동시 사용 충돌 주의 → 순서 조율
```

## 언제 쓰나 (우리 프로젝트)

| 작업 | GPU 필요도 |
|---|---|
| 감성 추론 (FOMC/뉴스) | CPU로 충분. GPU면 빠름 |
| 대량 뉴스 자동수집 (Phase 7) | GPU 권장 |
| **모델 재파인튜닝** | **GPU 강력 권장** ← 주 용도 |

→ 지금(검증)은 불필요. 재파인튜닝/Phase 7 때 활용.

## 세팅 순서 (실제 쓸 때, 한 명이 대표로)

```
1. (캠퍼스망/VPN) ssh -p 2123 aicp419@dlogin01.usc.unist.ac.kr → passwd 변경
2. mkdir -p ~/shared/models ~/shared/data
3. 코드:   git clone https://github.com/2026-AICP/fomc-sentiment-agents.git
4. 모델:   드롭박스 모델 → ~/shared/models/finbert-finetuned/ (scp/rsync)
5. 데이터: WSJ/FOMC → ~/shared/data/
6. 환경:   module load conda/pytorch  (또는 개인 conda)
7. 테스트: srun --partition=gpu_v100 --gres=gpu:1 --pty python3 -c "import torch;print(torch.cuda.is_available())"
8. 제출:   sbatch scripts/run_gpu.sh  →  squeue -u aicp419
```

## 확인할 것 (UserGuide 상세)
- 개인 conda에서 transformers 설치 가능한지 (인터넷 제한 여부)
- 모델·데이터 업로드 방식 (scp/rsync, 또는 외부망 제한 시 별도)
- GPU 큐 대기·QOS 제한
