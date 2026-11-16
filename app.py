import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

st.set_page_config(page_title="내 시장 체크", page_icon="📊", layout="centered")

# ===== 기본 관심 자산 (코드: 이름) — 앱에서 추가·삭제하기 전의 처음 목록 =====
ASSETS = {
    "278530": "KODEX 200TR",
    "411060": "ACE KRX금현물",
    "360750": "TIGER 미국S&P500",
    "005380": "현대차",
    "SPCX": "스페이스X",
    "USD/KRW": "원/달러 환율",
}

RULE_NAMES = {
    "MA20>MA60": "단기 (20일선 > 60일선)",
    "Price>MA120": "중기 (주가 > 120일선)",
    "Price>MA200": "장기 (주가 > 200일선)",
}


@st.cache_data(ttl=3600)  # 1시간 동안은 다시 받지 않고 저장해 둔 데이터 사용
def load(code):
    return fdr.DataReader(code, "2022-01-01")["Close"].dropna()


@st.cache_data(ttl=1800)  # 뉴스는 30분마다 갱신
def fetch_news(query, limit=5):
    """구글 뉴스 RSS에서 최신 기사 제목·링크 가져오기 (키 필요 없음)"""
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
           + "+when:7d&hl=ko&gl=KR&ceid=KR:ko")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())

    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        source = item.findtext("source", "")
        if source and title.endswith(" - " + source):   # 제목 끝의 " - 언론사" 제거
            title = title[: -len(" - " + source)]
        try:
            when = parsedate_to_datetime(item.findtext("pubDate")).astimezone(
                pd.Timestamp.now(tz="Asia/Seoul").tz).strftime("%m/%d %H:%M")
        except Exception:
            when = ""
        title = title.replace("[", "［").replace("]", "］")   # 마크다운 링크 깨짐 방지
        items.append({"title": title, "link": item.findtext("link", ""),
                      "source": source, "when": when})
        if len(items) >= limit:
            break
    return items


def news_query(code, name):
    """뉴스 검색어 만들기"""
    if "/" in code:                       # 환율: USD/KRW → "USD 환율"
        return f"{code.split('/')[0]} 환율"
    return f'"{name}"'                    # 종목명이 정확히 들어간 기사


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
    code = q.upper()
    return code, name_of(code)           # 그 외에는 코드·티커로 간주 (예: AAPL)


def name_of(code):
    """코드로 표시 이름 찾기"""
    if code in ASSETS:
        return ASSETS[code]
    for name, c in krx_list().items():
        if c == code:
            return name
    return code


# ===== 관심 자산 목록: 주소창(URL)에 저장 =====
def get_watchlist():
    saved = st.query_params.get("w")
    if saved is None:
        return list(ASSETS.keys())
    return [c for c in saved.split(",") if c]


def save_watchlist(codes):
    st.query_params["w"] = ",".join(codes)
    st.rerun()


def show_card(code, name, action=None):
    try:
        close = load(code)
        if len(close) < 2:
            raise ValueError("데이터가 너무 적어요")
    except Exception as e:
        st.warning(f"{name}: 데이터를 불러오지 못했어요. 코드나 티커를 다시 확인해 주세요. ({e})")
        if action == "remove":
            if st.button(f"🗑️ {name} 삭제", key=f"del_{code}"):
                save_watchlist([c for c in get_watchlist() if c != code])
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
        if "/" in code:
            st.caption("💱 환율이 '상승 추세'면 원화 약세(달러 강세), '하락 추세'면 원화 강세라는 뜻이에요.")

        with st.expander("📈 차트 보기 (최근 1년 반)"):
            chart = pd.DataFrame({
                "가격": close,
                "120일선": r["ma120"],
                "200일선": r["ma200"],
            }).iloc[-380:]
            st.line_chart(chart)

        with st.expander("📰 관련 뉴스 (최근 7일)"):
            try:
                news = fetch_news(news_query(code, name))
                if not news:
                    st.caption("최근 7일 동안 관련 뉴스가 없어요.")
                for n in news:
                    st.markdown(f"- [{n['title']}]({n['link']})  \n"
                                f"  <small>{n['source']} · {n['when']}</small>",
                                unsafe_allow_html=True)
            except Exception as e:
                st.caption(f"뉴스를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요. ({e})")

        # 관심 자산 추가·삭제 버튼
        watch = get_watchlist()
        if action == "add":
            if code in watch:
                st.caption("⭐ 이미 관심 자산에 있어요")
            elif st.button("⭐ 관심 자산에 추가", key=f"add_{code}"):
                save_watchlist(watch + [code])
        elif action == "remove":
            if st.button("🗑️ 관심 자산에서 삭제", key=f"del_{code}"):
                save_watchlist([c for c in watch if c != code])


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
        show_card(code, name, action="add")

st.divider()
st.markdown("#### ⭐ 내 관심 자산")

c1, c2 = st.columns(2)
if c1.button("🔄 지금 새로고침"):
    st.cache_data.clear()
    st.rerun()
if c2.button("↩️ 기본 목록으로"):
    save_watchlist(list(ASSETS.keys()))

st.caption("📌 추가·삭제한 목록은 이 페이지 주소에 저장돼요. 바꾼 뒤에는 지금 주소를 즐겨찾기나 홈 화면에 다시 추가하세요.")

watchlist = get_watchlist()
if not watchlist:
    st.info("관심 자산이 비어 있어요. 위 검색창에서 종목을 찾아 ⭐ 추가를 눌러보세요.")
for code in watchlist:
    show_card(code, name_of(code), action="remove")

st.divider()
st.caption(
    "이동평균선 기반 추세 상태를 보여주는 개인용 참고 도구예요. "
    "추세 신호는 늦게 나오는 특성이 있고, 투자 권유가 아닙니다."
)
