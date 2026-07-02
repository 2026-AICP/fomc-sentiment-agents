#!/bin/sh
# UNIST Dumbo HPC — FinBERT 작업 제출 스크립트 (우리 프로젝트용)
# 사용:  ssh -p 2123 aicp419@dlogin01.usc.unist.ac.kr  로 접속 후
#        sbatch scripts/run_gpu.sh
# 상태:  squeue -u aicp419   |   취소: scancel <JobID>   |   로그: run_gpu.o<JobID>
#
# ※ UNIST 내부망(캠퍼스/VPN)에서만 접속 가능. 외부 접속 불가.
# ※ partition: gpu_v100(24h·최신·빠름) / gpu_p100(72h) / gpu_k80(120h·장시간 학습)

#SBATCH -J finbert            # 작업 이름
#SBATCH -p gpu_p100           # partition (추론=v100 권장, 장시간 학습=p100/k80)
#SBATCH -N 1                  # 노드 1개
#SBATCH -n 4                  # CPU core 4개
#SBATCH -o %x.o%j             # 표준출력 로그 (finbert.o<JobID>)
#SBATCH -e %x.e%j             # 에러 로그   (finbert.e<JobID>)
#SBATCH --time 12:00:00       # 최대 시간 (추론 넉넉, 학습이면 늘리기)
#SBATCH --exclusive=user      # GPU 파티션 사용 시 적용
#SBATCH --gres=gpu:1          # GPU 1개

# ── 환경 로드 ──
source /etc/profile.d/modules.sh
module purge
# 방법 A) 미리 설치된 pytorch 모듈 사용 (가장 간단)
module load conda/pytorch
# 방법 B) 개인 conda 환경 (transformers 최신 필요 시. 위 A 대신 사용)
#   source /apps/application/miniconda3/etc/profile.d/conda.sh
#   conda activate fomc          # 미리 만든 환경 (transformers, torch 설치)

# ── 실행 (원하는 작업으로 교체) ──
cd $HOME/fomc-sentiment-agents         # 코드 위치 (git clone 한 곳)
export SENTIMENT_ENGINE=finbert        # 진짜 FinBERT 엔진
export FINBERT_MODEL_DIR=$HOME/shared/models/finbert-finetuned   # 모델 위치 (공용)

# 예: 뉴스 인덱스 생성 (WSJ 대량 추론 — GPU 이점 큼)
export WSJ_DIR=$HOME/shared/data/wsj
python3 analysis/news_index.py

# 예: 재파인튜닝이면 아래처럼 (학습 스크립트 준비 후)
#   python3 train_finetune.py
