"""
대시보드 데이터 만들기 (predict.html 용)

노트북이 저장한 결과 csv들을 읽어서
outputs/dashboard_data.json, outputs/dashboard_data.js 를 만듭니다.
노트북을 다시 실행해 csv가 바뀌면 이 파일만 다시 실행하면 됩니다.
"""
import os
import json
from datetime import datetime

import pandas as pd

# ------------------------------------------------------------
# 1. 설정
# ------------------------------------------------------------
RESULT_DIR = 'outputs'          # 결과 csv가 있는 폴더
OUT_DIR = 'outputs'             # json 저장 폴더
SAMPLE_FILE = 'data/data.csv'   # 사고유형·연령 표본 (없으면 해당 섹션 숨김)

# 자치구별 월 실적 (ds · 지역구명 · 이송건수) → 실적 추이·전년 동기 비교에 사용
MONTHLY_FILES = ['ml_data/ambulance_monthly.csv', 'outputs/ambulance_monthly.csv', 'ambulance_monthly.csv']
HISTORY_LEN = 25                # 화면에 보여줄 실적 개월 수 (25 = 2023-12 ~ 2025-12)

DATA_START = '2017-01'          # 월 실적 파일이 없을 때만 쓰는 값
DATA_END = '2025-12'
VALID_PERIOD = None             # 검증 기간 문자열 (예: '2025-01 ~ 2025-06'), 모르면 None

ALL = '서울 전체'


def read(name):
    """결과 csv 읽기 (없으면 None)"""
    path = os.path.join(RESULT_DIR, name)
    if not os.path.isfile(path):
        print('[없음]', path)
        return None
    return pd.read_csv(path, encoding='utf-8-sig')


def records(df, digits=3):
    """표 → [{컬럼: 값}, ...] (소수점 정리, NaN → None)"""
    if df is None:
        return []
    out = df.copy()
    for c in out.select_dtypes('number').columns:
        out[c] = out[c].round(digits)
    out = out.astype(object).where(out.notna(), None)
    return out.to_dict(orient='records')


def to_int_list(values):
    return [None if pd.isna(v) else int(round(v)) for v in values]


# ------------------------------------------------------------
# 2. 이송 건수 : 월 실적 + 평가 기간 예측 + 2026 예측
# ------------------------------------------------------------
def read_monthly():
    """자치구별 월 실적 읽기 (없으면 None)"""
    for path in MONTHLY_FILES:
        if os.path.isfile(path):
            df = pd.read_csv(path, encoding='utf-8-sig')
            df['ds'] = pd.to_datetime(df['ds']).dt.strftime('%Y-%m')
            print('[월 실적]', path)
            return df, path
    print('[없음] 월 실적 파일 → 평가 기간 6개월만 표시')
    return None, None


def build_transport():
    test = read('transport_test_predictions.csv')
    fc = read('transport_forecast_by_gu.csv')

    test_months = sorted(test['날짜'].astype(str).unique())
    future_months = sorted(fc['예측월'].astype(str).unique())
    gu_list = sorted(fc['지역구명'].unique())

    def pivot(df, month_col, value_col, months):
        table = df.pivot_table(index='지역구명', columns=month_col, values=value_col, aggfunc='sum')
        table = table.reindex(columns=months)
        table.loc[ALL] = table.sum()
        return table

    actual = pivot(test, '날짜', '실제_이송건수', test_months)
    forecast = pivot(fc, '예측월', '예측_이송건수', future_months)

    # 월 실적이 있으면 최근 HISTORY_LEN개월 + 1년 전 같은 달, 없으면 평가 기간만
    monthly, monthly_path = read_monthly()
    last_year_months = [str(pd.Period(m, 'M') - 12) for m in future_months]
    if monthly is not None:
        all_months = sorted(monthly['ds'].unique())
        history_months = all_months[-HISTORY_LEN:]
        history = pivot(monthly, 'ds', '이송건수', history_months)
        last_year = pivot(monthly, 'ds', '이송건수', last_year_months)
    else:
        all_months = history_months = test_months
        history = actual
        last_year = None

    test_pred = pivot(test, '날짜', '예측_이송건수', history_months)
    test_pred.loc[ALL] = test_pred.loc[ALL].where(test_pred.loc[ALL] > 0)   # 평가 기간 밖은 비움

    districts = {}
    for gu in [ALL] + gu_list:
        districts[gu] = {
            'actual': to_int_list(actual.loc[gu]),
            'history': to_int_list(history.loc[gu]),
            'test_pred': to_int_list(test_pred.loc[gu]),
            'forecast': to_int_list(forecast.loc[gu]),
            'last_year': to_int_list(last_year.loc[gu]) if last_year is not None else None,
        }

    # 구별 실적 시작 월 (관할 변경 구는 늦게 시작)
    starts = {}
    if monthly is not None:
        starts = monthly.groupby('지역구명')['ds'].min().to_dict()

    # 구별 진단표 + 평가 점수표 합치기
    diag = read('transport_diag_by_gu.csv')
    score_gu = read('transport_test_scores_by_gu.csv')
    by_gu = diag
    if score_gu is not None:
        by_gu = diag.merge(score_gu[['지역구명', 'MAE']].rename(columns={'MAE': '평가_MAE'}),
                           on='지역구명', how='left')

    return {
        'best_model': str(fc['사용모델'].iloc[0]),
        'source_file': os.path.basename(monthly_path) if monthly_path else None,
        'data_start': all_months[0] if monthly is not None else DATA_START,
        'data_end': all_months[-1] if monthly is not None else DATA_END,
        'gu_start': starts,
        'history_months': history_months,
        'test_months': test_months,
        'future_months': future_months,
        'districts': districts,
        'scores': records(read('transport_model_scores.csv')),
        'detail': records(read('transport_model_scores_detail.csv')),
        'experiment': records(read('transport_improve_experiment.csv')),
        'by_gu': records(by_gu, 2),
        'train_rows': int(diag['학습행수'].sum()),
    }


# ------------------------------------------------------------
# 3. 생활인구 (일최대인구) 예측
# ------------------------------------------------------------
def build_population():
    pred = read('population_test_predictions.csv')
    if pred is None:
        return None
    dates = sorted(pred['날짜'].astype(str).unique())

    daily = {}
    for col, key in (('실제_일최대인구수', 'actual'), ('예측_일최대인구수', 'pred')):
        table = pred.pivot_table(index='지역구명', columns='날짜', values=col).reindex(columns=dates)
        table.loc[ALL] = table.sum()
        for gu in table.index:
            daily.setdefault(gu, {})[key] = to_int_list(table.loc[gu])

    return {
        'dates': dates,
        'daily': daily,
        'scores': records(read('population_model_scores.csv')),
        'by_gu': records(read('population_test_scores_by_gu.csv'), 2),
    }


# ------------------------------------------------------------
# 4. 이송 건수 × 생활인구 관계
# ------------------------------------------------------------
def build_relation():
    corr = read('relation_corr_table.csv')
    if corr is None:
        return None
    corr = corr.rename(columns={corr.columns[0]: '특성'})
    select = read('relation_pop_feature_select.csv')
    if select is not None:
        select = select.rename(columns={select.columns[0]: '특성'})
    return {
        'corr': records(corr),
        'district_rate': records(read('relation_district_rate.csv'), 2),
        'model_compare': records(read('relation_model_compare.csv')),
        'feature_select': records(select, 4),
    }


# ------------------------------------------------------------
# 5. 표본 : 사고 유형 · 연령대 구성비
# ------------------------------------------------------------
def build_sample():
    if not os.path.isfile(SAMPLE_FILE):
        print('[없음]', SAMPLE_FILE, '→ 표본 섹션 숨김')
        return None
    df = pd.read_csv(SAMPLE_FILE, encoding='utf-8-sig')

    # 질병은 '질병', 그 외는 구급사고유형 (없으면 '기타')
    kind = df['구급사고유형'].fillna('기타')
    kind = kind.where(df['발생유형'] != '질병', '질병')
    share = (kind.value_counts(normalize=True) * 100).drop('기타', errors='ignore')
    top = share.head(4)
    top['기타'] = 100 - top.sum()     # 상위 4개 외 나머지

    age = df.loc[df['환자연령'] >= 0, '환자연령']
    bins = [0, 20, 40, 60, 80, 200]
    labels = ['0~19세', '20~39세', '40~59세', '60~79세', '80세 이상']
    age_share = pd.cut(age, bins=bins, labels=labels, right=False).value_counts(normalize=True).reindex(labels) * 100

    return {
        'title': f'구급활동 표본 {len(df):,}건 ({os.path.basename(SAMPLE_FILE)})',
        'type_labels': list(top.index),
        'type_values': [round(float(v), 1) for v in top.values],
        'age_labels': labels,
        'age_values': [round(float(v), 1) for v in age_share.values],
    }


# ------------------------------------------------------------
# 6. 저장
# ------------------------------------------------------------
def build_dashboard():
    transport = build_transport()
    cal = read('transport_calendar.csv')
    calendar_features = [c for c in cal.columns if c != 'ds'] if cal is not None else []
    tm, fm = transport['test_months'], transport['future_months']

    dashboard = {
        'meta': {
            'version': 3,
            'target_label': '이송',
            'data_start': transport.pop('data_start'),
            'data_end': transport.pop('data_end'),
            'source_file': transport.pop('source_file'),
            'valid_period': VALID_PERIOD,
            'test_period': f'{tm[0]} ~ {tm[-1]}',
            'forecast_period': f'{fm[0]} ~ {fm[-1]}',
            'best_model': transport['best_model'],
            'train_rows': transport['train_rows'],
            'calendar_features': calendar_features,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        },
        'transport': transport,
        'population': build_population(),
        'relation': build_relation(),
        'sample': build_sample(),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    text = json.dumps(dashboard, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(OUT_DIR, 'dashboard_data.json'), 'w', encoding='utf-8') as f:
        f.write(text)
    with open(os.path.join(OUT_DIR, 'dashboard_data.js'), 'w', encoding='utf-8') as f:
        f.write('const DASHBOARD_DATA = ' + text + ';\n')

    print('저장 완료 :', os.path.join(OUT_DIR, 'dashboard_data.json'))
    print('평가 기간 :', dashboard['meta']['test_period'], '/ 예측 기간 :', dashboard['meta']['forecast_period'])
    return dashboard


if __name__ == '__main__':
    build_dashboard()
