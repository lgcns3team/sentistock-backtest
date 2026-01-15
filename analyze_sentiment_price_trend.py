# analyze_sentiment_price_trend.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

import matplotlib.pyplot as plt
import matplotlib as mpl

from db_config import get_connection


# =========================
# 0) 유틸
# =========================
def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def to_hour_dt(v) -> datetime:
    if isinstance(v, datetime):
        return floor_to_hour(v)

    s = str(v).replace("T", " ")
    if "." in s:
        s = s.split(".")[0]
    if "+" in s:
        s = s.split("+")[0].strip()
    if "Z" in s:
        s = s.replace("Z", "").strip()

    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return floor_to_hour(dt)

def build_compressed_time_axis(x):
    """
    x: List[datetime] (정렬되어 있다고 가정)
    return:
      cx: List[float]  # 압축된 x축
      tick_pos: List[float]
      tick_label: List[str]
    """
    if not x:
        return [], [], []

    # 날짜별 인덱스 부여
    dates = []
    date_index = {}
    for dt in x:
        d = dt.date()
        if d not in date_index:
            date_index[d] = len(dates)
            dates.append(d)

    cx = []
    for dt in x:
        day_idx = date_index[dt.date()]
        hour_offset = dt.hour - 9  # 09시 기준
        cx.append(day_idx * 7 + hour_offset)

    # x축 눈금(하루 시작 기준)
    tick_pos = []
    tick_label = []
    for d, idx in date_index.items():
        tick_pos.append(idx * 7)
        tick_label.append(d.strftime("%m-%d"))

    return cx, tick_pos, tick_label

def build_compressed_ticks(x):
    """
    x(List[datetime]) 기준으로:
    - compressed x축 좌표(cx)
    - 1시간 단위 tick (09~16)
    - 09시 tick에는 날짜도 같이 표기
    """
    if not x:
        return [], [], []

    # 날짜별 인덱스
    date_index = {}
    dates = []
    for dt in x:
        d = dt.date()
        if d not in date_index:
            date_index[d] = len(dates)
            dates.append(d)

    # compressed x
    cx = []
    for dt in x:
        day_idx = date_index[dt.date()]
        hour_offset = dt.hour - 9  # 09->0 ... 16->7
        cx.append(day_idx * 8 + hour_offset)  # 하루를 8칸(09~16)으로

    # tick: 모든 날짜에 대해 09~16 매시간
    tick_pos = []
    tick_label = []
    for d, day_idx in date_index.items():
        for h in range(9, 17):  # 9~16
            pos = day_idx * 8 + (h - 9)
            tick_pos.append(pos)

            if h == 9:
                tick_label.append(f"{d.strftime('%m-%d')}\n{h:02d}")
            else:
                tick_label.append(f"{h:02d}")

    return cx, tick_pos, tick_label

# =========================
# 1) DB 조회
# =========================
def fetch_company_names(conn) -> Dict[str, str]:
    sql = "SELECT id, name FROM companies"
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return {str(r["id"]): (r.get("name") or "") for r in rows}


def fetch_common_data_range(conn, company_id: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    sql = """
    SELECT
      (SELECT MIN(date) FROM Stocks WHERE company_id=%s) AS p_min,
      (SELECT MAX(date) FROM Stocks WHERE company_id=%s) AS p_max,
      (SELECT MIN(date) FROM Stocks_score WHERE company_id=%s) AS s_min,
      (SELECT MAX(date) FROM Stocks_score WHERE company_id=%s) AS s_max
    """
    with conn.cursor() as cur:
        cur.execute(sql, (company_id, company_id, company_id, company_id))
        r = cur.fetchone()

    p_min, p_max = r["p_min"], r["p_max"]
    s_min, s_max = r["s_min"], r["s_max"]

    if p_min is None or p_max is None or s_min is None or s_max is None:
        return None, None

    start = max(p_min, s_min)
    end = min(p_max, s_max)
    if start >= end:
        return None, None

    return start, end


def fetch_hourly_price_close(conn, company_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            t.hour_bucket AS hour_dt,
            s.stck_prpr AS close_price
        FROM (
            SELECT
                DATE_FORMAT(date, '%%Y-%%m-%%d %%H:00:00') AS hour_bucket,
                MAX(date) AS max_dt
            FROM Stocks
            WHERE company_id = %s
              AND date >= %s AND date < %s
            GROUP BY hour_bucket
        ) t
        JOIN Stocks s
          ON s.company_id = %s
         AND s.date = t.max_dt
        ORDER BY t.hour_bucket ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (company_id, start, end, company_id))
        return cur.fetchall()


def fetch_hourly_sentiment(conn, company_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    sql = """
        SELECT date AS hour_dt, score
        FROM Stocks_score
        WHERE company_id = %s
          AND date >= %s AND date < %s
        ORDER BY date ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (company_id, start, end))
        return cur.fetchall()


# =========================
# 2) 머지
# =========================
def merge_by_hour(price_rows, senti_rows):
    price_map: Dict[str, float] = {}
    for r in price_rows:
        if r.get("close_price") is None:
            continue
        key = to_hour_dt(r["hour_dt"]).strftime("%Y-%m-%d %H:%M:%S")
        price_map[key] = float(r["close_price"])

    senti_map: Dict[str, float] = {}
    for r in senti_rows:
        if r.get("score") is None:
            continue
        key = to_hour_dt(r["hour_dt"]).strftime("%Y-%m-%d %H:%M:%S")
        senti_map[key] = float(r["score"])

    common_keys = sorted(set(price_map.keys()) & set(senti_map.keys()))
    x = [datetime.strptime(k, "%Y-%m-%d %H:%M:%S") for k in common_keys]
    price = [price_map[k] for k in common_keys]
    senti = [senti_map[k] for k in common_keys]
    return common_keys, x, price, senti


# =========================
# 3) 플롯 (개별)
# =========================
def plot_company_single(company_id: str, company_name: str, x, price, senti, out_path: str):
    if not x:
        print(f"[SKIP] {company_id} ({company_name}) : 공통 시간대 데이터가 없습니다.")
        return

    fig, ax1 = plt.subplots(figsize=(12, 5))

    # 거래시간 압축축 생성
    cx, tick_pos, tick_label = build_compressed_ticks(x)

    # Price
    ax1.plot(cx, price, color="tab:blue", linewidth=2, label="Price")
    ax1.set_ylabel("Price", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    # Sentiment
    ax2 = ax1.twinx()
    ax2.plot(cx, senti, color="tab:red", linewidth=2, label="Sentiment")
    ax2.set_ylabel("Sentiment", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")

    # x축 설정
    ax1.set_xticks(tick_pos)
    ax1.set_xticklabels(tick_label)
    ax1.set_xlabel("Trading Day")

    title_name = company_name if company_name else company_id
    ax1.set_title(f"{title_name} ({company_id}) - Price vs Sentiment (Trading Hours)")

    # 범례 합치기
    l1, lb1 = ax1.get_legend_handles_labels()
    l2, lb2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, lb1 + lb2, loc="upper left")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    print(f"[OK] saved: {out_path}")



# =========================
# 4) 플롯 (합쳐진 1장)
# =========================
def plot_companies_combined(results, out_path: str):
    """
    results: List of dict
      {
        "cid": str,
        "cname": str,
        "x": List[datetime],
        "price": List[float],
        "senti": List[float]
      }
    """
    valid = [r for r in results if r["x"]]
    if not valid:
        print("[SKIP] combined plot: 데이터가 없습니다.")
        return

    n = len(valid)
    cols = 2
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(14, 4.5 * rows))

    # axes shape 보정
    if rows == 1 and cols == 1:
        axes = [[axes]]
    elif rows == 1:
        axes = [axes]

    idx = 0
    for r in range(rows):
        for c in range(cols):
            ax1 = axes[r][c]

            if idx >= n:
                ax1.axis("off")
                continue

            item = valid[idx]
            idx += 1

            cid = item["cid"]
            cname = item["cname"] or cid
            x = item["x"]
            price = item["price"]
            senti = item["senti"]

            # 거래시간 압축축 생성
            cx, tick_pos, tick_label = build_compressed_ticks(x)

            # Price
            ax1.plot(cx, price, color="tab:blue", linewidth=1.8, label="Price")
            ax1.set_ylabel("Price", color="tab:blue")
            ax1.tick_params(axis="y", labelcolor="tab:blue")

            # Sentiment
            ax2 = ax1.twinx()
            ax2.plot(cx, senti, color="tab:red", linewidth=1.8, label="Sentiment")
            ax2.set_ylabel("Sentiment", color="tab:red")
            ax2.tick_params(axis="y", labelcolor="tab:red")

            # x축: 날짜만 표시(하루 시작점)
            ax1.set_xticks(tick_pos)
            ax1.set_xticklabels(tick_label)
            ax1.set_xlabel("Trading Day")

            ax1.set_title(f"{cname} ({cid})")

            # 범례 합치기
            l1, lb1 = ax1.get_legend_handles_labels()
            l2, lb2 = ax2.get_legend_handles_labels()
            ax1.legend(l1 + l2, lb1 + lb2, loc="upper left")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[OK] saved combined: {out_path}")



# =========================
# 5) 메인
# =========================
def analyze_sentiment_price_trend(company_ids: List[str], out_dir: str = "out_trends", debug: bool = True):
    try:
        mpl.rcParams["font.family"] = "Malgun Gothic"
        mpl.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    os.makedirs(out_dir, exist_ok=True)
    conn = get_connection()

    combined_results = []

    try:
        names = fetch_company_names(conn)

        for cid in company_ids:
            cname = names.get(cid, "")

            r_start, r_end = fetch_common_data_range(conn, cid)
            if r_start is None or r_end is None:
                print(f"[SKIP] {cid} ({cname}) : Stocks/Stocks_score 범위 교집합이 없습니다.")
                combined_results.append({"cid": cid, "cname": cname, "x": [], "price": [], "senti": []})
                continue

            start = floor_to_hour(r_start)
            end = floor_to_hour(r_end) + timedelta(hours=1)

            price_rows = fetch_hourly_price_close(conn, cid, start, end)
            senti_rows = fetch_hourly_sentiment(conn, cid, start, end)

            common_keys, x, price, senti = merge_by_hour(price_rows, senti_rows)

            if debug:
                print(f"\n[DEBUG] {cid} range start={start}, end={end}")
                print("[DEBUG] merged points =", len(x))
                print("[DEBUG] first key =", common_keys[0] if common_keys else None)
                print("[DEBUG] last  key =", common_keys[-1] if common_keys else None)

            # 개별 저장
            single_path = os.path.join(out_dir, f"{cid}_trend.png")
            plot_company_single(cid, cname, x, price, senti, single_path)

            # 합쳐진 플롯용 데이터 저장
            combined_results.append({"cid": cid, "cname": cname, "x": x, "price": price, "senti": senti})

        # 합쳐진 파일 1장 추가 저장
        combined_path = os.path.join(out_dir, "combined_trends.png")
        plot_companies_combined(combined_results, combined_path)

    finally:
        conn.close()


if __name__ == "__main__":
    COMPANY_IDS = ["005930", "005380", "373220", "009830", "034020"]
    analyze_sentiment_price_trend(COMPANY_IDS, out_dir="out_trends", debug=True)
