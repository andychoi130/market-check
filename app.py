import streamlit as st
import FinanceDataReader as fdr
import pandas as pd

st.set_page_config(page_title="내 시장 체크", page_icon="📊", layout="centered")

# ===== 확인할 자산 (코드: 이름) — 자유롭게 추가·삭제 =====
ASSETS = {
    "278530": "KODEX 200TR",
    "411060": "ACE KRX금현물",
    "360750": "TIGER 미국S&P500",
    "005380": "현대차",
    "SPCX": "스페이스X",
}

RULE_NAMES = {
    "MA20>MA60": "단기 (20일선 > 60일선)",
    "Price>MA120": "중기 (주가 > 120일선)",
    "Price>MA200": "장기 (주가 > 200일선)",
}


@st.cache_data(ttl=3600)  # 1시간 동안은 다시 받지 않고 저장해 둔 데이터 사용
def load(code):
    return fdr.DataReader(code, "2022-01-01")["Close"].dropna()


def label(signal):
    if len(signal) == 0:
        return "⚪ 데이터 부족"
    changed = signal != signal.shift()
    days = len(signal[signal[changed].index[-1]:])
    return f"🟢 보유 ({days}일째)" if signal.iloc[-1] else f"🔴 회피 ({days}일째)"


def analyze(close):
    ma = {n: close.rolling(n).mean() for n in [20, 60, 120, 200]}
    rules = {
        "MA20>MA60": (ma[20] > ma[60])[ma[60].notna()],
        "Price>MA120": (close > ma[120])[ma[120].notna()],
        "Price>MA200": (close > ma[200])[ma[200].notna()],
    }
    valid = [r for r in rules.values() if len(r) > 0]
    green = sum(bool(r.iloc[-1]) for r in valid)

    if len(valid) < 2:
        summary = "⚪ 판단 보류"
    elif green == len(valid):
        summary = "💪 강한 상승 추세"
    elif green / len(valid) >= 0.5:
        summary = "🙂 상승 우세"
    elif green > 0:
        summary = "😐 하락 우세"
    else:
        summary = "🥶 하락 추세"

    gap = close.iloc[-1] / ma[200].iloc[-1] - 1
    return {
        "labels": {k: label(v) for k, v in rules.items()},
        "summary": summary,
        "valid": len(valid),
        "gap": None if pd.isna(gap) else gap,
        "ma120": ma[120],
        "ma200": ma[200],
    }


@st.cache_data(ttl=86400)  # 종목 목록은 하루에 한 번만 받아옴
def krx_list():
    try:
        df = fdr.StockListing("KRX")
        return dict(zip(df["Name"], df["Code"]))
    except Exception:
        return {}


def resolve(query):
    """입력값을 (코드, 표시 이름)으로 바꿔줌. 한글 종목명이면 코드로 변환."""
    q = query.strip()
    if not q:
        return None, None
    names = krx_list()
    if q in names:                       # 정확한 종목명 (예: 삼성전자)
        return names[q], q
    for name, code in names.items():     # 코드로 입력했으면 이름 찾아주기
        if code == q:
            return code, name
    return q.upper(), q.upper()          # 그 외에는 티커로 간주 (예: AAPL)


def show_card(code, name):
    try:
        close = load(code)
        if len(close) < 2:
            raise ValueError("데이터가 너무 적어요")
    except Exception as e:
        st.warning(f"{name}: 데이터를 불러오지 못했어요. 코드나 티커를 다시 확인해 주세요. ({e})")
        return

    r = analyze(close)
    day_chg = close.iloc[-1] / close.iloc[-2] - 1

    with st.container(border=True):
        st.subheader(f"{name}")
        st.markdown(f"### {r['summary']}")

        c1, c2 = st.columns(2)
        c1.metric("현재가", f"{close.iloc[-1]:,.2f}", f"{day_chg:+.2%}")
        c2.metric("200일선 대비", "-" if r["gap"] is None else f"{r['gap']:+.1%}")

        for key, text in r["labels"].items():
            st.write(f"**{RULE_NAMES[key]}**: {text}")

        st.caption(f"기준일 {close.index[-1].date()} · 판단 근거: 규칙 {r['valid']}/3개")

        with st.expander("📈 차트 보기 (최근 1년 반)"):
            chart = pd.DataFrame({
                "가격": close,
                "120일선": r["ma120"],
                "200일선": r["ma200"],
            }).iloc[-380:]
            st.line_chart(chart)


# ===== 화면 =====
st.title("📊 내 시장 체크")
st.caption(f"{pd.Timestamp.now(tz='Asia/Seoul'):%Y-%m-%d %H:%M} 기준 · 데이터는 1시간마다 갱신")

# 🔍 종목 검색
st.markdown("#### 🔍 종목 검색")
query = st.text_input(
    "종목코드, 티커 또는 종목명",
    placeholder="예: 005930, 삼성전자, AAPL, TSLA",
)
if query:
    code, name = resolve(query)
    with st.spinner(f"{name} 분석 중..."):
        show_card(code, name)

st.divider()
st.markdown("#### ⭐ 내 관심 자산")

if st.button("🔄 지금 새로고침"):
    st.cache_data.clear()
    st.rerun()

for code, name in ASSETS.items():
    show_card(code, name)

st.divider()
st.caption(
    "이동평균선 기반 추세 상태를 보여주는 개인용 참고 도구예요. "
    "추세 신호는 늦게 나오는 특성이 있고, 투자 권유가 아닙니다."
)
