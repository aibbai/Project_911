"""
대시보드 데이터 저장 (predict.html 용)

예측 노트북 마지막에 save_dashboard()를 한 번 실행하면
outputs/dashboard_data.json, outputs/dashboard_data.js 가 새로 만들어집니다.
"""
import os
import json
from datetime import datetime

import pandas as pd

ALL = '서울 전체'


def to_month(s):
    """날짜를 그 달 1일로 맞춤 (2026-01-15 → 2026-01-01)"""
    return pd.to_datetime(s).dt.to_period('M').dt.to_timestamp()


def clean_frame(frame):
    """ds · 지역구명 · y 세 컬럼만 남기고 월 단위로 정리"""
    out = frame[['ds', '지역구명', 'y']].copy()
    out['ds'] = to_month(out['ds'])
    return out


def month_values(frame, gu, months):
    """구별(또는 서울 전체 합계) 월 값 목록, 없는 달은 None"""
    part = frame if gu == ALL else frame[frame['지역구명'] == gu]
    total = part.groupby('ds')['y'].sum()
    return [None if m not in total.index else int(round(total[m])) for m in months]


def find_col(df, *words):
    """컬럼 이름에 words가 모두 들어간 첫 컬럼"""
    for c in df.columns:
        if all(w in str(c) for w in words):
            return c
    return None


def clean_scores(scores):
    """모델 점수표 → 검증/평가 정확도·MAE 표준 이름으로 변환"""
    rows = []
    cols = {
        '검증_정확도(%)': find_col(scores, '검증', '정확도'),
        '평가_정확도(%)': find_col(scores, '평가', '정확도'),
        '검증_MAE': find_col(scores, '검증', 'MAE'),
        '평가_MAE': find_col(scores, '평가', 'MAE'),
    }
    name_col = '모델' if '모델' in scores.columns else scores.columns[0]
    for _, r in scores.iterrows():
        row = {'모델': str(r[name_col])}
        for key, col in cols.items():
            if col is not None and pd.notna(r[col]):
                row[key] = round(float(r[col]), 4)
        rows.append(row)
    return rows


def load_old_sample(out_dir):
    """이전 json의 표본 분석(사고 유형·연령대) 재사용"""
    path = os.path.join(out_dir, 'dashboard_data.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('sample')
    except (OSError, ValueError):
        return None


def save_dashboard(actual, forecast, scores, best_model,
                   valid_period, test_period=None, test_pred=None,
                   features=None, target_label='이송', source_file='',
                   train_rows=None, dnn_type='', history_len=25,
                   sample=None, out_dir='outputs'):
    actual = clean_frame(actual)
    forecast = clean_frame(forecast)

    all_months = sorted(actual['ds'].unique())
    future_months = sorted(forecast['ds'].unique())
    history_months = all_months[-history_len:]
    recent_months = all_months[-6:]
    last_year_months = [m - pd.DateOffset(months=12) for m in future_months]

    if test_pred is not None:
        test_pred = clean_frame(test_pred)

    gu_list = sorted(actual['지역구명'].unique())
    districts = {}
    for gu in [ALL] + gu_list:
        districts[gu] = {
            'recent': month_values(actual, gu, recent_months),
            'history': month_values(actual, gu, history_months),
            'forecast': month_values(forecast, gu, future_months),
            'last_year': month_values(actual, gu, last_year_months),
        }
        if test_pred is not None:
            districts[gu]['test_pred'] = month_values(test_pred, gu, history_months)

    fmt = lambda months: [pd.Timestamp(m).strftime('%Y-%m') for m in months]

    dashboard = {
        'meta': {
            'target_label': target_label,
            'source_file': source_file,
            'data_start': fmt(all_months[:1])[0],
            'data_end': fmt(all_months[-1:])[0],
            'train_rows': int(train_rows if train_rows is not None else len(actual)),
            'valid_period': valid_period,
            'test_period': test_period,
            'forecast_period': f"{fmt(future_months)[0]} ~ {fmt(future_months)[-1]}",
            'best_model': best_model,
            'dnn_type': dnn_type,
            'features': list(features or []),
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        },
        'recent_months': fmt(recent_months),
        'history_months': fmt(history_months),
        'future_months': fmt(future_months),
        'districts': districts,
        'models': clean_scores(scores),
        'sample': sample if sample is not None else load_old_sample(out_dir),
    }

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, 'dashboard_data.json')
    js_path = os.path.join(out_dir, 'dashboard_data.js')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=1, default=float)
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write('const DASHBOARD_DATA = ')
        json.dump(dashboard, f, ensure_ascii=False, indent=1, default=float)
        f.write(';\n')

    print('저장 완료 :', json_path, ',', js_path)
    print('데이터 기간 :', dashboard['meta']['data_start'], '~', dashboard['meta']['data_end'])
    print('예측 기간   :', dashboard['meta']['forecast_period'])
    return pd.DataFrame({'예측월': dashboard['future_months'],
                         '서울 전체 예측': districts[ALL]['forecast']})
