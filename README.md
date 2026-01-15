# sentistock-backtest
<img width="1800" height="726" alt="image" src="https://github.com/user-attachments/assets/61cd1007-0503-4bbb-9261-d4e95e098e2e" />

>이 레포의 스크립트들은 “감정 점수 산출 방식/집계 기간”를 바꿔가며  
>감정 지표가 주가 흐름에 어떤 영향을 주는지 반복 검증하며
>이것을 시각화 하기위한 목적을 가집니다.
>
## :star: Repository Purpose

이 레포지토리는 다음 목적을 가집니다.

- DB에 저장된 **뉴스 단위 감정 결과**를 불러와 종목 단위로 집계합니다.
- 실험 목적에 따라 감정 점수 계산식을 바꿔가며(가중치/정규화/클리핑 등) 지표를 재생성합니다.
- 생성된 종목별 감정 점수는 후속 분석에서 사용할 수 있도록 DB에 다시 저장합니다.
- 이러한 것들을 시각화합니다.
---
## ⚙️Prerequisites

### Environment
- python 3.10

### Project Setup
```
pip install pymysql
pip install matplotlib
pip install python-dotenv
```
### Excute
```
python analyze_sentiment_price_trend.py
python rebuild_sentiments_score.py
python rebuild_sentiments_score_history.py
```

---

### :key: Key Components

`analyze_sentiment_price_trend.py`
- 주가 데이터와 감정 점수를 동일한 시간축으로 정렬하여 비교 분석
- 감정 점수 변화 구간에서의 가격·거래량 반응을 시각화 및 통계적으로 확인

`rebuild_sentiments_score.py`
- DB에 저장된 뉴스 단위 감정 결과를 종목 단위 감정 점수로 재집계
- 감정 점수 산식 또는 가중치 변경에 따른 결과를 비교·검증하기 위한 데이터 재생성

`rebuild_sentiments_score_history.py`
- 종목별 감정 점수를 시간 순서의 히스토리 데이터로 재구성
- 집계 기간(윈도우) 변경에 따른 감정 지표의 안정성 및 설명력 비교

### :file_folder: Data Structure
```
📦sentistock-backtest
 ┣ 📜.gitignore
 ┣ 📜analyze_sentiment_price_trend.py
 ┣ 📜db_config.py
 ┣ 📜README.md
 ┣ 📜rebuild_sentiments_score.py
 ┗ 📜rebuild_sentiments_score_history.py
```
