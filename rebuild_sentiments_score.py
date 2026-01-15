from db_config import get_connection

def compute_k_index(p_pos: float, p_neu: float, p_neg: float) -> float:
    """
    0~100 점수 계산:
    base = 긍정 - 부정
    confidence = 1 - 중립
    S = base * confidence
    score = (S + 1) / 2 * 100
    """
    base = p_pos - p_neg
    confidence = 1.0 - p_neu
    s = base * confidence
    raw_score = (s + 1.0) / 2.0 * 100.0
    return max(0.0, min(100.0, raw_score))

def rebuild_sentiments_score(batch_size: int = 2000):
    conn = get_connection()

    select_sql = """
        SELECT id, prob_pos, prob_neu, prob_neg
        FROM sentiments
    """
    
    update_sql = """
        UPDATE sentiments
        SET score = %s
        WHERE id = %s
    """

    total = 0
    updated = 0

    try:
        with conn.cursor() as cur:
            cur.execute(select_sql)
            rows = cur.fetchall()

            total = len(rows)
            if total == 0:
                print("sentiments 테이블에 데이터가 없습니다.")
                return

            batch_params = []
            for row in rows:
                sid = row["id"]
                p_pos = float(row["prob_pos"] or 0.0)
                p_neu = float(row["prob_neu"] or 0.0)
                p_neg = float(row["prob_neg"] or 0.0)

                new_score = round(compute_k_index(p_pos, p_neu, p_neg), 2)
                batch_params.append((new_score, sid))

                if len(batch_params) >= batch_size:
                    cur.executemany(update_sql, batch_params)
                    conn.commit()
                    updated += len(batch_params)
                    print(f"업데이트 진행: {updated}/{total}")
                    batch_params.clear()

            if batch_params:
                cur.executemany(update_sql, batch_params)
                conn.commit()
                updated += len(batch_params)

        print(f"sentiments.score 리빌드 완료: {updated}/{total}")

    finally:
        conn.close()

if __name__ == "__main__":
    rebuild_sentiments_score(batch_size=2000)