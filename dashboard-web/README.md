# SentiBoard Web — React 대시보드

Streamlit 버전(`dashboard/app.py`)의 **React(Vite) 포팅**. Lovable과 동일 스택(React SPA)이라
그대로 발전시키거나 Lovable에 이관 가능.

## 구조 (핵심: 프론트는 계산하지 않는다)

```
파이썬 파이프라인 ──→ public/data/*.json ──→ React가 fetch·표시만
(analysis/export_dashboard.py)              (환각 차단 원칙 유지)
```

## 실행

```bash
# 1) 데이터 내보내기 (레포 루트에서)
python3 analysis/export_dashboard.py dashboard-web/public/data

# 2) 개발 서버
cd dashboard-web
npm install        # 최초 1회
npm run dev        # http://localhost:5173
```

`npm run data` = 1)을 대신 실행하는 단축 스크립트.

## 페이지

대시보드(KPI·톤 타임라인·최근신호) · 신호(A/B/C/D) · News 축(일별+CI) ·
괴리 검증(attention signal, 2.4×) · 기자회견(성명문 vs presser, 87%) · 방법론·한계(3중 검증)

## 배포

`npm run build` → `dist/` 정적 파일 → Vercel/Netlify/GitHub Pages 어디든.
데이터 갱신 = export 스크립트 재실행 후 재배포 (CI에 붙이면 자동화 가능).
