"""SentiBoard — FOMC 감성·신호 실시간 대시보드 (Streamlit).

DB(agent_skeleton.db / fomc.db)와 outputs/news_index_live.csv 를 매 실행마다 읽어
회의 톤·시장·신호·News 지수를 보여준다. 신호·통합 로직은 검증된 기존 모듈을 재사용.

실행:
  py -m streamlit run dashboard/app.py
  (한글 경로 인증서 이슈가 있으면 실행 전 CURL_CA_BUNDLE/SSL_CERT_FILE/TEMP 를 ASCII 경로로)
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.signals import load_series, build_alerts, Thresholds  # 검증된 신호 엔진 재사용
from analysis.headline import combine                             # 검증된 통합(headline) 재사용

# ── 데이터 소스 ──
CANDIDATE_DBS = [ROOT / "data" / "agent_skeleton.db", ROOT / "data" / "fomc.db"]
NEWS_CSV = ROOT / "outputs" / "news_index_live.csv"
AGENT_REPORTS = ROOT / "reports" / "agent_out"

# 색 (SentiBoard 팔레트와 동일)
C = dict(accent="#f9812f", good="#2dd4a0", bad="#ef4d4d", warn="#f5a623",
         neutral="#9aa2ad", blue="#4a90e2", ink="#e9ebef", muted="#9aa2ad",
         panel="#15181e", border="#282d37")

GRADE_COLOR = {"🟢 정합": C["good"], "🔴 경고": C["bad"], "⚠️ 주의": C["warn"], "⚪ 중립": C["neutral"]}


# ─────────────────────────── 데이터 로딩 (실시간: ttl 짧게) ───────────────────────────
def _active_db() -> Path | None:
    """meetings 행이 가장 많은 DB 를 고른다 (전체 코퍼스 우선)."""
    best, best_n = None, 0
    for db in CANDIDATE_DBS:
        if not db.exists():
            continue
        try:
            con = sqlite3.connect(db)
            n = con.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
            con.close()
        except sqlite3.Error:
            continue
        if n > best_n:
            best, best_n = db, n
    return best


@st.cache_data(ttl=30)
def load_meetings(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT date, method, index_value, confidence FROM meetings "
        "WHERE granularity='meeting' ORDER BY date", con)
    con.close()
    return df


@st.cache_data(ttl=30)
def load_alerts(db_path: str) -> pd.DataFrame:
    """검증된 load_series+build_alerts 로 회의별 신호·등급 산출."""
    con = sqlite3.connect(db_path)
    series = load_series(con)
    con.close()
    alerts = build_alerts(series, Thresholds(), small_sample=len(series) < 30)
    rows = []
    for a in alerts:
        rows.append(dict(date=a.date, grade=a.grade, tone=a.tone,
                         reaction=a.reaction_ret, fired=", ".join(a.fired_names()) or "—",
                         detail=" · ".join(s.detail for s in a.signals if s.fired)))
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def load_sentences(db_path: str, date: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    tags = [r[0] for r in con.execute(
        "SELECT DISTINCT model_tag FROM sentences WHERE date=?", (date,)).fetchall()]
    tag = next((t for t in tags if t != "dummy"), tags[0] if tags else None)
    df = pd.read_sql_query(
        "SELECT sentence_idx, sentence, p_pos, p_neu, p_neg, score, entropy "
        "FROM sentences WHERE date=? AND model_tag=? ORDER BY sentence_idx",
        con, params=(date, tag))
    con.close()
    return df, tag


@st.cache_data(ttl=30)
def load_market(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT date, spx_close, spx_ret_cc, vix, vix_chg FROM market "
            "WHERE spx_close IS NOT NULL ORDER BY date", con)
    except pd.errors.DatabaseError:
        df = pd.DataFrame()
    con.close()
    return df


@st.cache_data(ttl=30)
def load_yields(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT date, ust2y, ust10y FROM market "
            "WHERE ust2y IS NOT NULL ORDER BY date", con)
    except pd.errors.DatabaseError:
        df = pd.DataFrame()
    con.close()
    if len(df):
        df["date"] = pd.to_datetime(df["date"])
        df["spread"] = df["ust10y"] - df["ust2y"]   # 10Y-2Y 장단기 스프레드
    return df


@st.cache_data(ttl=30)
def load_news() -> pd.DataFrame:
    if not NEWS_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(NEWS_CSV)


# ─────────────────────────── 차트 헬퍼 (다크 Altair) ───────────────────────────
def line_chart(df, x, y, color, title_y="", zero=True):
    import altair as alt
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:O", axis=alt.Axis(title=None, labelColor=C["muted"], grid=False, domainColor=C["border"])),
        y=alt.Y(f"{y}:Q", axis=alt.Axis(title=title_y, labelColor=C["muted"],
                                        gridColor=C["border"], domainColor=C["border"])),
    )
    area = base.mark_area(line={"color": color, "strokeWidth": 2.4},
                          color=alt.Gradient(gradient="linear",
                              stops=[alt.GradientStop(color=color, offset=0),
                                     alt.GradientStop(color=C["panel"], offset=1)],
                              x1=1, x2=1, y1=0, y2=1))
    dots = base.mark_circle(size=55, color=color)
    tip = base.mark_point(size=200, opacity=0).encode(
        tooltip=[alt.Tooltip(f"{x}:O", title="일자"), alt.Tooltip(f"{y}:Q", title="지수", format="+.3f")])
    ch = (area + dots + tip)
    if zero:
        ch = alt.layer(alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(
            color=C["muted"], strokeDash=[4, 4], opacity=0.5).encode(y="z:Q"), ch)
    return ch.properties(height=260, background="transparent").configure_view(strokeWidth=0)


# ─────────────────────────── 공통 CSS ───────────────────────────
def inject_css():
    st.markdown(f"""
    <style>
      .stApp{{background:
        radial-gradient(1100px 520px at 82% -8%, rgba(249,129,47,.06), transparent 60%),
        #0c0e12; color:{C['ink']};}}
      section[data-testid="stSidebar"]{{background:#101319;border-right:1px solid #20242c;}}
      .kpi{{background:{C['panel']};border:1px solid #20242c;border-radius:16px;padding:16px 18px;}}
      .kpi .eb{{font-size:12px;color:{C['muted']};font-weight:600;}}
      .kpi .big{{font-size:32px;font-weight:800;letter-spacing:-.02em;margin:6px 0 2px;
        font-variant-numeric:tabular-nums;}}
      .kpi .mt{{font-size:12px;color:{C['muted']};}}
      .pill{{font-size:11px;font-weight:700;padding:3px 9px;border-radius:20px;margin-left:8px;}}
      .brand{{display:flex;gap:11px;align-items:center;padding:4px 2px 14px;}}
      .brand .mk{{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;
        font-weight:800;color:#1a1205;background:linear-gradient(150deg,#fca35c,{C['accent']});}}
      h1,h2,h3{{letter-spacing:-.02em;}}
      div[data-testid="stMetricValue"]{{font-variant-numeric:tabular-nums;}}
    </style>""", unsafe_allow_html=True)


def svg_spark(vals, color):
    """값 리스트 → 인라인 SVG 스파크라인 HTML (값 2개 미만이면 빈 문자열)."""
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return ""
    lo, hi = min(xs), max(xs)
    rng = (hi - lo) or 1.0
    n = len(xs)
    pts = [(i / (n - 1) * 100, 28 - (v - lo) / rng * 24) for i, v in enumerate(xs)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    ex, ey = pts[-1]
    return (f'<svg viewBox="0 0 100 32" preserveAspectRatio="none" '
            f'style="width:100%;height:34px;margin-top:8px;display:block">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" points="{poly}"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="2.6" fill="{color}"/></svg>')


def kpi(col, eyebrow, value, meta, pill=None, pill_color=None, spark=None, spark_color=None):
    p = f'<span class="pill" style="background:{pill_color}22;color:{pill_color}">{pill}</span>' if pill else ""
    sp = svg_spark(spark, spark_color or C["accent"]) if spark else ""
    col.markdown(f'<div class="kpi"><div class="eb">{eyebrow}</div>'
                 f'<div class="big">{value}{p}</div><div class="mt">{meta}</div>{sp}</div>',
                 unsafe_allow_html=True)


def fmt(v, sign=True):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.3f}" if sign else f"{v:.3f}"


# ─────────────────────────── 페이지들 ───────────────────────────
def page_dashboard(db, mt, alerts, market, news):
    st.markdown("## 오늘의 시장 감성 👋")
    st.caption("FOMC 성명문(Fed 축) + 경제뉴스(News 축) 실시간 감성·신호")

    cw = mt[mt.method == "conf_weighted"]
    fed_latest = cw.iloc[-1] if len(cw) else None
    news_latest = news.iloc[-1] if len(news) else None
    fed_v = fed_latest.index_value if fed_latest is not None else None
    news_v = news_latest.conf_weighted if news_latest is not None else None
    hl = combine(fed_v, news_v if news_v is not None else None)

    fed_series = cw.index_value.tolist()[-12:]        # 최근 회의 톤 추세
    news_series = news.conf_weighted.tolist() if len(news) else []
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "통합 감성 (headline) Σ", fmt(hl["headline"]) if hl else "—",
        f"방식: {hl['method']}" if hl else "데이터 없음",
        "긍정" if hl and hl["headline"] > 0.03 else "중립",
        C["good"] if hl and hl["headline"] > 0.03 else C["neutral"],
        spark=fed_series, spark_color=C["accent"])
    kpi(c2, "Fed 축 (성명문) 🏛", fmt(fed_v),
        f"{fed_latest.date} 성명문" if fed_latest is not None else "—",
        spark=fed_series, spark_color=C["accent_soft"] if "accent_soft" in C else C["accent"])
    if news_latest is not None:
        ci = f"CI {news_latest.ci_lo:+.2f}~{news_latest.ci_hi:+.2f}" if pd.notna(news_latest.ci_lo) else "CI n<2"
        kpi(c3, "News 축 (오늘) ✦", fmt(news_v), f"기사 {int(news_latest.n_articles)}건 · {ci}",
            "중립" if abs(news_v) < 0.1 else ("긍정" if news_v > 0 else "부정"),
            C["neutral"] if abs(news_v) < 0.1 else (C["good"] if news_v > 0 else C["bad"]),
            spark=news_series, spark_color=C["blue"])
    else:
        kpi(c3, "News 축 (오늘) ✦", "—", "outputs/news_index_live.csv 없음")
    # 오늘의 신호: 최근 회의 등급
    g = alerts.iloc[-1].grade if len(alerts) else "—"
    kpi(c4, "최근 회의 신호 ⚑", g.split(" ")[-1] if " " in g else g,
        f"{alerts.iloc[-1].date}" if len(alerts) else "—",
        None, GRADE_COLOR.get(g))

    st.write("")
    left, right = st.columns([1.7, 1])
    with left:
        st.markdown("#### 일별 News 감성 지수")
        if len(news):
            st.altair_chart(line_chart(news, "date", "conf_weighted", C["accent"], "지수"),
                            use_container_width=True)
        else:
            st.info("News 지수 데이터가 없습니다. `py analysis/news_index_live.py` 실행 후 표시됩니다.")
    with right:
        st.markdown("#### 회의 신호 분포")
        if len(alerts):
            dist = alerts.grade.value_counts()
            dd = pd.DataFrame({"등급": dist.index, "건수": dist.values})
            import altair as alt
            donut = alt.Chart(dd).mark_arc(innerRadius=52, stroke=C["panel"], strokeWidth=2).encode(
                theta="건수:Q",
                color=alt.Color("등급:N", scale=alt.Scale(
                    domain=list(GRADE_COLOR), range=list(GRADE_COLOR.values())),
                    legend=alt.Legend(title=None, labelColor=C["muted"])),
                tooltip=["등급", "건수"]).properties(height=260, background="transparent")
            st.altair_chart(donut, use_container_width=True)
        else:
            st.info("신호 데이터 없음")

    lc, rc = st.columns([1, 1])
    with lc:
        st.markdown("#### 톤 vs 시장 반응 (정합/괴리)")
        d = alerts.dropna(subset=["tone", "reaction"]).copy()
        if len(d):
            import altair as alt
            d["관계"] = d.apply(lambda r: "정합" if (r.tone > 0) == (r.reaction > 0) else "괴리", axis=1)
            pts = alt.Chart(d).mark_circle(size=110, opacity=0.85).encode(
                x=alt.X("tone:Q", title="Fed 톤",
                        axis=alt.Axis(labelColor=C["muted"], gridColor=C["border"])),
                y=alt.Y("reaction:Q", title="시장 반응 %",
                        axis=alt.Axis(labelColor=C["muted"], gridColor=C["border"])),
                color=alt.Color("관계:N", scale=alt.Scale(domain=["정합", "괴리"],
                                range=[C["good"], C["bad"]]),
                                legend=alt.Legend(title=None, labelColor=C["muted"])),
                tooltip=[alt.Tooltip("date:T", title="회의"),
                         alt.Tooltip("tone:Q", format="+.3f"),
                         alt.Tooltip("reaction:Q", title="반응%", format="+.2f"), "관계"])
            vline = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=C["muted"], opacity=.4).encode(x="x:Q")
            hline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=C["muted"], opacity=.4).encode(y="y:Q")
            st.altair_chart((vline + hline + pts).properties(height=260, background="transparent")
                            .configure_view(strokeWidth=0), use_container_width=True)
            st.caption("우상·좌하 = 정합(같은 방향) · 우하·좌상 = 괴리(어긋남)")
        else:
            st.info("톤·반응 데이터 부족")
    with rc:
        st.markdown("#### 최근 신호")
        if len(alerts):
            show = alerts.iloc[::-1].head(8)[["date", "grade", "tone", "reaction", "fired"]]
            show.columns = ["회의일", "등급", "톤", "시장반응%", "발동신호"]
            st.dataframe(show, use_container_width=True, hide_index=True, height=300)
        else:
            st.info("신호 데이터 없음")


def page_signals(alerts):
    st.markdown("## 신호")
    st.caption("규칙 A(톤급변)·B(괴리)·C(톤-VIX) — 검증된 analysis.signals 엔진")
    if not len(alerts):
        st.info("신호 데이터 없음 — 파이프라인을 먼저 실행하세요.")
        return
    for _, r in alerts.iloc[::-1].iterrows():
        color = GRADE_COLOR.get(r.grade, C["neutral"])
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**{r.date}** — {r.detail or '특이신호 없음'}")
            a.caption(f"톤 {fmt(r.tone)} · 시장반응 {fmt(r.reaction)}% · 발동 [{r.fired}]")
            b.markdown(f'<div style="text-align:right"><span class="pill" '
                       f'style="background:{color}22;color:{color};font-size:13px">{r.grade}</span></div>',
                       unsafe_allow_html=True)


@st.cache_data(ttl=30)
def load_articles() -> pd.DataFrame:
    scored = ROOT / "outputs" / "news_articles_scored.csv"
    raw = ROOT / "data" / "news" / "fed_news.csv"
    if scored.exists():
        return pd.read_csv(scored, encoding="utf-8-sig")
    if raw.exists():
        df = pd.read_csv(raw, encoding="utf-8-sig")
        return df[["date", "source", "title", "url"]]
    return pd.DataFrame()


def page_news(news, db):
    st.markdown("## News 축")
    st.caption("Marketaux 실시간 뉴스 → FinBERT 채점 → 일별 지수 + 부트스트랩 95% CI")
    if not len(news):
        st.info("News 지수 없음 — `py engine/news_scrape.py` → `py analysis/news_index_live.py`")
        return
    st.altair_chart(line_chart(news, "date", "conf_weighted", C["accent"], "지수"),
                    use_container_width=True)

    st.markdown("#### 일별 상세")
    show = news[["date", "n_articles", "conf_weighted", "ci_lo", "ci_hi", "confidence"]].copy()
    show.columns = ["일자", "기사수", "지수", "CI 하한", "CI 상한", "확신도"]
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.download_button("⬇ 일별 지수 CSV", news.to_csv(index=False).encode("utf-8-sig"),
                       "news_index_live.csv", "text/csv")

    st.markdown("#### 최근 기사")
    arts = load_articles()
    if not len(arts):
        st.info("기사 목록 없음 — `py engine/news_scrape.py` 로 수집하세요.")
        return
    has_sent = "label" in arts.columns
    for _, a in arts.head(15).iterrows():
        if has_sent:
            col = {"긍정": C["good"], "부정": C["bad"], "중립": C["neutral"]}.get(a["label"], C["neutral"])
            chip = (f'<span class="pill" style="background:{col}22;color:{col}">'
                    f'{a["label"]} {a["score"]:+.2f}</span>')
        else:
            chip = ""
        title = str(a["title"]).replace("<", "&lt;")
        url = a.get("url", "")
        link = f'<a href="{url}" target="_blank" style="color:{C["ink"]};text-decoration:none">{title}</a>' if url else title
        st.markdown(
            f'<div style="border-bottom:1px solid #20242c;padding:9px 2px">{chip} '
            f'<span style="font-size:11px;color:#6b727d">{a["date"]} · {a["source"]}</span><br>{link}</div>',
            unsafe_allow_html=True)
    if has_sent:
        st.download_button("⬇ 기사·감성 CSV", arts.to_csv(index=False).encode("utf-8-sig"),
                           "news_articles_scored.csv", "text/csv")


def timeline_chart(df, x, y):
    """회의 톤 타임라인 + 위기 구간 음영 (2008 금융위기 · 2020 COVID)."""
    import altair as alt
    crises = pd.DataFrame([
        {"start": "2008-09-01", "end": "2009-06-30", "label": "금융위기"},
        {"start": "2020-02-15", "end": "2020-06-30", "label": "COVID"},
    ])
    crises["start"] = pd.to_datetime(crises["start"])
    crises["end"] = pd.to_datetime(crises["end"])
    dmin, dmax = pd.to_datetime(df[x].min()), pd.to_datetime(df[x].max())
    crises = crises[(crises.end >= dmin) & (crises.start <= dmax)]  # 데이터 범위와 겹치는 것만
    layers = []
    if len(crises):
        layers.append(alt.Chart(crises).mark_rect(opacity=0.14, color=C["bad"]).encode(
            x=alt.X("start:T"), x2="end:T"))
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:T", axis=alt.Axis(title=None, labelColor=C["muted"], gridColor=C["border"])),
        y=alt.Y(f"{y}:Q", axis=alt.Axis(title="conf_weighted", labelColor=C["muted"],
                                        gridColor=C["border"])))
    layers.append(alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(
        color=C["muted"], strokeDash=[4, 4], opacity=0.5).encode(y="z:Q"))
    layers.append(base.mark_line(color=C["accent"], strokeWidth=2, point=alt.OverlayMarkDef(
        color=C["accent"], size=45)).encode(
        tooltip=[alt.Tooltip(f"{x}:T", title="회의"), alt.Tooltip(f"{y}:Q", title="톤", format="+.3f")]))
    return alt.layer(*layers).properties(height=280, background="transparent").configure_view(strokeWidth=0)


def _highlight_html(sents):
    """문장을 감성 점수(score)로 색상 하이라이트한 HTML 블록."""
    out = ['<div style="line-height:1.7;font-size:14px">']
    for _, r in sents.iterrows():
        s = r["score"]
        if s > 0.1:
            bg, bar = "rgba(45,212,160,.13)", C["good"]
        elif s < -0.1:
            bg, bar = "rgba(239,77,77,.13)", C["bad"]
        else:
            bg, bar = "rgba(154,162,173,.10)", C["neutral"]
        txt = str(r["sentence"]).replace("<", "&lt;")
        out.append(f'<div style="background:{bg};border-left:3px solid {bar};'
                   f'padding:7px 11px;margin:5px 0;border-radius:6px">{txt}'
                   f'<span style="color:#6b727d;font-size:11px;float:right">'
                   f'{"+" if s>=0 else ""}{s:.2f}</span></div>')
    out.append("</div>")
    return "".join(out)


def page_fed(db, mt):
    st.markdown("## Fed 축 (성명문)")
    st.caption("회의별 감성 톤 타임라인 + 문장별 분해 (FinBERT 온도보정 T=3.1)")
    cw = mt[mt.method == "conf_weighted"].copy()
    if not len(cw):
        st.info("회의 톤 없음")
        return
    cw["date"] = pd.to_datetime(cw["date"])
    st.altair_chart(timeline_chart(cw, "date", "index_value"), use_container_width=True)
    st.download_button("⬇ 회의별 톤 CSV", cw.to_csv(index=False).encode("utf-8-sig"),
                       "fed_tone.csv", "text/csv")
    if len(cw) < 10:
        st.caption("※ 현재 DB에 최근 회의만 있음. 전체 타임라인은 "
                   "`SENTIMENT_ENGINE=finbert py agents/graph.py --batch` (전체) 후 표시.")

    st.markdown("#### 회의 드릴다운")
    dates = mt[mt.method == "conf_weighted"].date.tolist()[::-1]
    date = st.selectbox("회의 선택", dates)
    sents, tag = load_sentences(str(db), date)
    st.caption(f"모델: {tag} · {len(sents)}문장 · 초록=긍정 / 빨강=부정 / 회색=중립")
    if len(sents):
        st.markdown(_highlight_html(sents), unsafe_allow_html=True)
        with st.expander("문장별 확률 표 보기"):
            show = sents.copy()
            for c in ["p_pos", "p_neu", "p_neg"]:
                show[c] = (show[c] * 100).round(1)
            show = show[["sentence", "p_pos", "p_neu", "p_neg", "score", "entropy"]]
            show.columns = ["문장", "긍정%", "중립%", "부정%", "score", "불확실성"]
            st.dataframe(show, use_container_width=True, hide_index=True)


def page_headline(mt, news):
    st.markdown("## 통합 지수 (headline)")
    st.caption("Fed 축 + News 축 결합. 뉴스 없으면 Fed 단독 폴백 (검증된 analysis.headline)")
    cw = mt[mt.method == "conf_weighted"]
    news_v = news.iloc[-1].conf_weighted if len(news) else None

    st.caption("각 축을 전 구간(2000~2026) 평균·표준편차로 z-표준화 후 결합 "
               "(analysis/headline_norm.json). News(작은 분산)가 Fed에 묻히지 않도록 보정.")

    rows = []
    for _, r in cw.iterrows():
        h = combine(r.index_value, news_v)
        rows.append(dict(회의일=r.date, Fed=round(r.index_value, 3),
                         News=round(news_v, 3) if news_v is not None else None,
                         통합=round(h["headline"], 3) if h else None,
                         방식=h["method"] if h else "—"))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("※ 현재 뉴스는 최근 회의 주변에만 존재 → 과거 회의는 fed_only 폴백. "
               "검증본(docs/news_fed_index.md)에선 z-표준화 50:50 이 VIX 상관 −0.534 로 최선.")


def page_rates(db, mt):
    st.markdown("## 금리 축 (미 국채)")
    st.caption("FRED 2년물(DGS2)·10년물(DGS10) · 신호 D(톤 vs 2년물)의 기반 데이터")
    import altair as alt
    y = load_yields(str(db))
    if not len(y):
        st.info("금리 데이터 없음 — `py analysis/collect_market.py` 실행 후 표시됩니다.")
        return

    last = y.iloc[-1]
    inv = last.spread < 0
    c1, c2, c3 = st.columns(3)
    kpi(c1, "2년물 (정책 민감) 🏛", f"{last.ust2y:.2f}%", f"{last.date.date()}")
    kpi(c2, "10년물 (장기) 📉", f"{last.ust10y:.2f}%", f"{last.date.date()}")
    kpi(c3, "장단기 스프레드 (10Y−2Y)", f"{last.spread:+.2f}%p",
        "역전(침체 신호)" if inv else "정상",
        "역전" if inv else "정상", C["bad"] if inv else C["good"])

    st.markdown("#### 2년물 · 10년물 추이")
    long = y.melt(id_vars="date", value_vars=["ust2y", "ust10y"],
                  var_name="만기", value_name="금리")
    long["만기"] = long["만기"].map({"ust2y": "2년물", "ust10y": "10년물"})
    lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=alt.X("date:T", axis=alt.Axis(title=None, labelColor=C["muted"], gridColor=C["border"])),
        y=alt.Y("금리:Q", scale=alt.Scale(zero=False),
                axis=alt.Axis(title="%", labelColor=C["muted"], gridColor=C["border"])),
        color=alt.Color("만기:N", scale=alt.Scale(domain=["2년물", "10년물"],
                        range=[C["accent"], C["blue"]]),
                        legend=alt.Legend(title=None, labelColor=C["muted"])),
        tooltip=[alt.Tooltip("date:T", title="일자"), "만기",
                 alt.Tooltip("금리:Q", format=".2f")]
    ).properties(height=260, background="transparent").configure_view(strokeWidth=0)
    st.altair_chart(lines, use_container_width=True)

    st.markdown("#### 장단기 스프레드 (10Y − 2Y)")
    y2 = y.copy()
    y2["국면"] = y2["spread"].apply(lambda s: "역전" if s < 0 else "정상")
    area = alt.Chart(y2).mark_area(opacity=0.85).encode(
        x=alt.X("date:T", axis=alt.Axis(title=None, labelColor=C["muted"], gridColor=C["border"])),
        y=alt.Y("spread:Q", axis=alt.Axis(title="%p", labelColor=C["muted"], gridColor=C["border"])),
        color=alt.Color("국면:N", scale=alt.Scale(domain=["정상", "역전"],
                        range=[C["good"], C["bad"]]),
                        legend=alt.Legend(title=None, labelColor=C["muted"])),
        tooltip=[alt.Tooltip("date:T", title="일자"),
                 alt.Tooltip("spread:Q", title="스프레드", format="+.2f"), "국면"])
    zero = alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(
        color=C["muted"], strokeDash=[4, 4]).encode(y="z:Q")
    st.altair_chart((area + zero).properties(height=220, background="transparent")
                    .configure_view(strokeWidth=0), use_container_width=True)
    st.caption("음수(빨강) = 장단기 금리 역전 → 전통적 침체 선행 신호. "
               "2년물은 Fed 정책 민감 만기라 신호 D(톤 vs 2년물)의 서프라이즈 대리로 쓰임.")
    st.download_button("⬇ 금리 CSV", y.to_csv(index=False).encode("utf-8-sig"),
                       "yields.csv", "text/csv")


def page_backtest(alerts):
    import altair as alt
    st.markdown('## 괴리 신호 — "지금 자세히 봐야 할 때"')
    st.caption("괴리는 위기를 **예측**하는 게 아니라, **추가 검토가 필요한 시점**을 "
               "짚어주는 attention signal 입니다.")

    # ── 괴리란? (평이한 설명) ──
    st.markdown(
        f'<div class="kpi" style="margin:2px 0 18px">'
        f'<div class="eb">괴리(divergence)란?</div>'
        f'<div style="font-size:15px;line-height:1.65;margin-top:7px;color:{C["ink"]}">'
        f'연준의 <b>톤</b>과 시장의 <b>반응</b>이 서로 '
        f'<b style="color:{C["bad"]}">엇갈린</b> 회의입니다.<br>'
        f'<span style="color:{C["muted"]};font-size:13px">'
        f'예 · 연준은 안심시키는데 시장은 급락(2020 COVID) &nbsp;/&nbsp; '
        f'연준은 우려하는데 시장은 안도 랠리(2001 닷컴)</span>'
        f'</div></div>', unsafe_allow_html=True)

    # ── 핵심 한 줄: 2.4배 ──
    st.markdown("#### 괴리가 뜨면? — 위기 구간일 확률이 **평소의 2.4배**")
    cols = st.columns(3)
    kpi(cols[0], "평소 (위기 아닐 때)",
        f'<span style="color:{C["muted"]}">18%</span>', "회의의 18%에서만 괴리")
    kpi(cols[1], "위기 구간에서는",
        f'<span style="color:{C["bad"]}">42%</span>', "괴리가 2.4배 더 자주",
        pill="2.4×", pill_color=C["bad"])
    kpi(cols[2], "우연일 가능성",
        f'<span style="color:{C["good"]}">0.1%</span>', "permutation p=0.001 · 유의")

    # ── 막대 비교 (평소 vs 위기) ──
    comp = pd.DataFrame({"구간": ["평소", "위기 구간"], "비율": [18, 42]})
    bar = alt.Chart(comp).mark_bar(
        size=96, cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
        x=alt.X("구간:N", sort=["평소", "위기 구간"],
                axis=alt.Axis(title=None, labelColor=C["ink"], labelFontSize=14,
                              domainColor=C["border"])),
        y=alt.Y("비율:Q", scale=alt.Scale(domain=[0, 50]),
                axis=alt.Axis(title="괴리 발생 비율 (%)", labelColor=C["muted"],
                              gridColor=C["border"], domainColor=C["border"])),
        color=alt.Color("구간:N", scale=alt.Scale(domain=["평소", "위기 구간"],
                        range=[C["neutral"], C["bad"]]), legend=None),
        tooltip=[alt.Tooltip("구간:N", title="구간"),
                 alt.Tooltip("비율:Q", title="괴리 비율(%)", format=".0f")],
    ).properties(height=230, background="transparent").configure_view(strokeWidth=0)
    st.altair_chart(bar, use_container_width=True)
    st.caption("금융스트레스 구간(NBER 침체 + 알려진 위기)에 괴리가 우연보다 2.4배 몰림. "
               "위기 구간은 신호와 **독립**으로 사전 정의(순환논리 회피). "
               "검정: permutation p=0.001 · Fisher p<0.001 · `analysis/validate_divergence.py`")

    # ── 대표 사례 (연준 ≠ 시장) ──
    st.markdown("#### 대표 사례 — 연준 ≠ 시장")
    ex = [("🦠", "2020-03-15", "COVID 긴급 제로금리", "＋0.10 긍정", "−12.0%"),
          ("🏦", "2008-10-07", "금융위기 공조 인하", "＋0.11 긍정", "−5.7%"),
          ("💻", "2001-01-03", "닷컴 긴급인하 → 안도 랠리", "−0.08 부정", "＋5.0%"),
          ("📉", "2011-08-09", "신용강등 후 저금리 약속", "−0.05 부정", "＋4.7%")]
    ec = st.columns(2)
    for i, (icon, when, ctx, fed, mkt) in enumerate(ex):
        with ec[i % 2].container(border=True):
            st.markdown(f"{icon} **{when}** · {ctx}")
            st.caption(f"연준 톤 {fed} &nbsp;↔&nbsp; 시장 당일 {mkt}")

    # ── 기술 통계 (원하는 사람만) ──
    with st.expander("🔬 통계 자세히 — 신호별 위험사건 동반율 (offset=1 백테스트, 188건)"):
        st.caption("발표 후 2일 최대낙폭 상위 1/3 = '위험사건'. 각 신호가 그 구간에 얼마나 "
                   "**동반**되는지 (예측 아닌 연관). 2000–2021.")
        bt = pd.DataFrame([
            {"신호": "divergence (괴리)", "발동": 60, "위험사건 동반율": "48%", "95% CI": "36–61%",
             "평소 기저율": "34%", "차이": "+15%p", "무작위 p": "0.003", "판정": "유의(주목 신호)"},
            {"신호": "tone_vs_vix", "발동": 32, "위험사건 동반율": "62%", "95% CI": "45–77%",
             "평소 기저율": "34%", "차이": "+29%p", "무작위 p": "0.000", "판정": "유의(주목 신호)"},
            {"신호": "tone_shift", "발동": 19, "위험사건 동반율": "42%", "95% CI": "23–64%",
             "평소 기저율": "34%", "차이": "+9%p", "무작위 p": "0.279", "판정": "구별 어려움"},
        ])
        st.dataframe(bt, use_container_width=True, hide_index=True)
        live = (", ".join(f"{g} {v}" for g, v in alerts.grade.value_counts().items())
                if len(alerts) else "라이브 신호 없음")
        st.caption(f"현재 DB 신호 분포(라이브): {live}")
        st.info("전체 재현: `py -m analysis.backtest` (188건 코퍼스 필요). "
                "현 DB는 최근 회의 표본이라 라이브 백테스트는 표본 부족.")


# ─────────────────────────── 메인 ───────────────────────────
def main():
    st.set_page_config(page_title="SentiBoard", page_icon="📊", layout="wide")
    inject_css()

    st.sidebar.markdown('<div class="brand"><div class="mk">S</div>'
                        '<div><div style="font-weight:800;font-size:16px">SentiBoard</div>'
                        '<div style="font-size:11px;color:#6b727d">FOMC 감성·신호</div></div></div>',
                        unsafe_allow_html=True)

    PAGES = ["📊 대시보드", "🚦 신호", "✦ News 축", "🏛 Fed 축", "🪙 금리 축",
             "📈 통합 지수", "🚩 괴리 검증"]
    # key 로 선택을 session_state 에 보존 → 자동 rerun(60초) 후에도 페이지 유지
    page = st.sidebar.radio("메뉴", PAGES, key="page", label_visibility="collapsed")

    if st.sidebar.button("🔄 새로고침 (최신 데이터 반영)", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    auto = st.sidebar.checkbox("⏱ 자동 새로고침 (60초)", value=True)
    if auto:
        # 세션 유지 rerun(전체 리로드 아님) → key="page" 로 보던 페이지 그대로 유지
        st_autorefresh(interval=60000, key="auto_refresh")

    st.sidebar.caption("규칙 기반 · LLM 미사용\n\n모든 수치·신호는 DB·계산에서 직접. 재현·감사 가능. **예측이 아닌 경향.**")

    db = _active_db()
    if db is None:
        st.warning("meetings 데이터가 있는 DB를 찾지 못했습니다. "
                   "`SENTIMENT_ENGINE=finbert py agents/graph.py --batch` 를 먼저 실행하세요.")
        return
    st.sidebar.caption(f"📁 소스: {db.name}")

    mt = load_meetings(str(db))
    alerts = load_alerts(str(db))
    market = load_market(str(db))
    news = load_news()

    if page.endswith("대시보드"):
        page_dashboard(db, mt, alerts, market, news)
    elif page.endswith("신호"):
        page_signals(alerts)
    elif page.endswith("News 축"):
        page_news(news, db)
    elif page.endswith("Fed 축"):
        page_fed(db, mt)
    elif page.endswith("금리 축"):
        page_rates(db, mt)
    elif page.endswith("통합 지수"):
        page_headline(mt, news)
    elif page.endswith("괴리 검증"):
        page_backtest(alerts)


if __name__ == "__main__":
    main()
