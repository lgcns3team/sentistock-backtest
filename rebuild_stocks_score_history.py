from datetime import datetime, timedelta
from db_config import get_connection


# dt를 시간 단위로 내림
def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def rebuild_stocks_score_history(
    window_hours: int = 1,        # (1=최근1시간, 2=최근2시간, 6=최근6시간...)
    min_count: int = 1,           # 표본 부족 제외하고 싶으면 3 같은 값
    truncate_before: bool = True, # True면 기존 히스토리 싹 지우고 재생성
    commit_every_hours: int = 6   # 몇 시간 단위로 커밋할지(너무 자주 커밋 싫으면 늘려도 됨)
):
    conn = get_connection()

    # sentiments의 전체 기간(min/max)
    range_sql = """
        SELECT MIN(date) AS min_dt, MAX(date) AS max_dt
        FROM sentiments
    """

    # window 구간의 회사별 평균 계산 (sentiments → news → companies)
    agg_sql = """
        SELECT
            c.id AS company_id,
            AVG(s.score) AS avg_score,
            COUNT(*) AS cnt
        FROM sentiments s
        JOIN news n ON s.news_id = n.id
        JOIN companies c ON n.company_id = c.id
        WHERE s.date >= %s AND s.date < %s
        GROUP BY c.id
    """

    # 1시간봉(정각 t)에 업서트
    upsert_sql = """
        INSERT INTO Stocks_score (company_id, score, date)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            score = VALUES(score)
    """

    try:
        with conn.cursor() as cur:
            cur.execute(range_sql)
            r = cur.fetchone()

            if not r or r["min_dt"] is None or r["max_dt"] is None:
                print("[INFO] sentiments 데이터가 없습니다.")
                return

            min_dt = floor_to_hour(r["min_dt"])
            max_dt = floor_to_hour(r["max_dt"])

            if truncate_before:
                cur.execute("TRUNCATE TABLE Stocks_score")
                conn.commit()
                print("[OK] Stocks_score TRUNCATE 완료")

            bucket = timedelta(hours=1) # 1시간봉
            window = timedelta(hours=window_hours)

            # 시간봉 t는 min_dt ~ max_dt까지 (정각)
            t = min_dt
            t_end = max_dt

            total_hours = 0
            total_upserts = 0
            pending_hours = 0

            while t <= t_end:
                # 시간봉 t의 값은 (t - window, t] 구간으로 계산
                # 구현은 [start, end)로 처리
                window_end = t + bucket         # t시봉을 "그 한 시간 끝" 기준으로 볼 경우
                window_start = window_end - window

                cur.execute(agg_sql, (window_start, window_end))
                rows = cur.fetchall()

                params = []
                for row in rows:
                    if row["cnt"] < min_count:
                        continue
                    params.append((row["company_id"], float(row["avg_score"]), t))

                if params:
                    cur.executemany(upsert_sql, params)
                    total_upserts += len(params)

                total_hours += 1
                pending_hours += 1

                # 너무 자주 commit하면 느려질 수 있어서 시간 단위로 묶어서 커밋
                if pending_hours >= commit_every_hours:
                    conn.commit()
                    pending_hours = 0
                    if total_hours % 24 == 0:
                        print(f"[PROGRESS] hours={total_hours}, upserts={total_upserts}, now={t}")

                t += bucket

            # 남은 변경사항 커밋
            conn.commit()
            print(f"[DONE] window_hours={window_hours}, hours={total_hours}, upserts={total_upserts}")

    finally:
        conn.close()


if __name__ == "__main__":
    # 변수는 윈도우만 조절하면됨
    rebuild_stocks_score_history(window_hours=1, min_count=1, truncate_before=True)

    # 예) 최근 2시간 윈도우로 전체 재생성:
    # rebuild_stocks_score_history(window_hours=2, min_count=1, truncate_before=True)
