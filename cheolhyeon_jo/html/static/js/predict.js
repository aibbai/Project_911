lucide.createIcons();

    // 최신 노트북 결과 기준 (학습 ~2025-12, 예측 2026-01 ~ 2026-06)
    const EXPECTED_DATA_END = '2025-12';
    const EXPECTED_FORECAST_START = '2026-01';

    let D = null, T = null, P = null, R = null;
    const ALL = '서울 전체';
    let selectedMonths = 6;
    let selectedGu = ALL;
    let demandChart = null, popChart = null, detailBuilt = false;

    // 밝은 화면용 색상
    const UP_COLOR = '#dc2626';
    const DOWN_COLOR = '#059669';
    const GRID = 'rgba(15, 23, 42, 0.06)';
    const TICK = '#64748b';
    const LABEL = '#334155';
    const PALETTE = ['#2563eb', '#7c3aed', '#0891b2', '#d97706', '#059669', '#db2777'];

    // 영어 특성 이름 → 한글
    const FEATURE_KO = { night_pop: '야간 인구', day_pop: '주간 인구', total_pop: '총 생활인구', pop_diff: '주야간 인구 차이' };
    const featureKo = name => {
        const key = Object.keys(FEATURE_KO).find(k => name.includes(k));
        return key ? name.replace(key, FEATURE_KO[key]) : name;
    };

    const fmtMonth = ym => String(ym).slice(0, 7).replace('-', '.');
    const fmtNum = v => Math.round(v).toLocaleString();
    const fmt1 = v => Number(v).toFixed(1);
    const fmt2 = v => Number(v).toFixed(2);
    const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
    const sum = arr => arr.reduce((a, b) => a + b, 0);
    const pct = (now, before) => (now / before - 1) * 100;
    const pctText = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
    const pctClass = v => (v >= 0 ? 'up' : 'down');
    const prevYear = ym => (Number(ym.slice(0, 4)) - 1) + ym.slice(4);
    const guLabel = gu => (gu === ALL ? '서울특별시 전체' : gu);
    const pad = len => new Array(Math.max(0, len)).fill(null);
    const guList = () => Object.keys(T.districts).filter(n => n !== ALL);
    const isBase = name => String(name).startsWith('기준선');

    // 컬럼 이름에 words가 모두 들어간 값 (예: col(row, '평가', '6개월', '정확도'))
    function col(row, ...words) {
        if (!row) return null;
        const key = Object.keys(row).find(k => words.every(w => k.includes(w)));
        return key === undefined ? null : row[key];
    }
    const diagOf = gu => T.by_gu.find(r => r['지역구명'] === gu);
    const scoreOf = name => T.scores.find(r => r['모델'] === name);

    // ---------- 차트 만들기 + 범례 ----------
    // Chart.js 기본 범례는 끄고, 차트 위에 작은 버튼형 범례를 그림 (클릭하면 숨김/표시)
    function legendSwatch(color, kind, dashed) {
        if (kind === 'line') {
            return '<span class="sw-line" style="border-top-color:' + color +
                '; border-top-style:' + (dashed ? 'dashed' : 'solid') + ';"></span>';
        }
        return '<span class="' + (kind === 'arc' ? 'sw-dot' : 'sw-box') +
            '" style="background:' + color + ';"></span>';
    }

    function legendBox(canvas) {
        const holder = canvas.parentNode;
        let box = holder.previousElementSibling;
        if (!box || !box.classList.contains('chart-legend')) {
            box = document.createElement('div');
            box.className = 'chart-legend';
            holder.parentNode.insertBefore(box, holder);
        }
        return box;
    }

    // items : [{label, color, kind('line'|'box'|'arc'), dashed}], onToggle(i) → 표시 여부
    function renderLegend(box, items, onToggle) {
        box.innerHTML = '';
        items.forEach((it, i) => {
            const el = document.createElement(onToggle ? 'button' : 'span');
            el.className = 'legend-item';
            if (onToggle) {
                el.type = 'button';
                el.onclick = () => el.classList.toggle('off', !onToggle(i));
            }
            el.innerHTML = legendSwatch(it.color, it.kind, it.dashed) + '<span>' + it.label + '</span>';
            box.appendChild(el);
        });
    }

    function drawLegend(chart) {
        const box = legendBox(chart.$canvas);
        if (chart.$type === 'doughnut') {
            const colors = chart.data.datasets[0].backgroundColor;
            renderLegend(box, chart.data.labels.map((label, i) => ({ label: label, color: colors[i], kind: 'arc' })), i => {
                chart.toggleDataVisibility(i);
                chart.update();
                return chart.getDataVisibility(i);
            });
            return;
        }
        const items = chart.data.datasets.map(d => {
            const kind = (d.type || chart.$type) === 'line' ? 'line' : 'box';
            const bg = Array.isArray(d.backgroundColor) ? d.backgroundColor[d.backgroundColor.length - 1] : d.backgroundColor;
            return { label: d.label, color: d.legendColor || (kind === 'line' ? d.borderColor : bg), kind: kind, dashed: !!d.borderDash };
        });
        chart.data.datasets.forEach((d, i) => chart.setDatasetVisibility(i, true));
        renderLegend(box, items, i => {
            const show = !chart.isDatasetVisible(i);
            chart.setDatasetVisibility(i, show);
            chart.update();
            return show;
        });
    }

    // 데이터가 2개 이상이거나 도넛이면 범례 표시
    function makeChart(canvas, cfg) {
        cfg.options = cfg.options || {};
        cfg.options.plugins = cfg.options.plugins || {};
        cfg.options.plugins.legend = { display: false };
        const chart = new Chart(canvas, cfg);
        chart.$canvas = canvas;
        chart.$type = cfg.type;
        if (cfg.type === 'doughnut' || cfg.data.datasets.length > 1) drawLegend(chart);
        return chart;
    }

    // ---------- 공통 차트 옵션 ----------
    function lineOptions(yFormat) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { grid: { color: GRID }, ticks: { color: TICK, maxRotation: 45, autoSkip: true, maxTicksLimit: 12 } },
                y: { grid: { color: GRID }, ticks: { color: TICK, callback: yFormat || (v => v.toLocaleString()) } }
            },
            plugins: {
                tooltip: { callbacks: { label: c => c.dataset.label + ' : ' + (c.raw === null ? '-' : fmtNum(c.raw)) } }
            }
        };
    }

    function hbarOptions(xMin, xMax, xFormat, onPick) {
        return {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { min: xMin, max: xMax, ticks: { color: TICK, callback: xFormat }, grid: { color: GRID } },
                y: { ticks: { color: LABEL, autoSkip: false, font: { size: 11 } }, grid: { display: false } }
            },
            plugins: {},
            onClick: onPick ? (e, items, chart) => {
                if (items.length) onPick(chart.data.labels[items[0].index]);
            } : undefined
        };
    }

    // ---------- 01. 이송 예측 ----------
    // 비교 기준 : 1년 전 같은 달 실적이 있으면 전년 동기, 없으면 직전 6개월
    function compareBase(gu, n) {
        const d = T.districts[gu];
        const ly = d.last_year ? d.last_year.slice(0, n) : [];
        if (ly.length === n && ly.every(v => v !== null)) return { values: ly, label: '전년 동기' };
        return { values: d.actual, label: '직전 6개월' };
    }

    // 선택 기간(N개월) 예측 평균 · 비교 기준 대비 변화
    function periodStats(gu) {
        const d = T.districts[gu];
        const fc = d.forecast.slice(0, selectedMonths);
        const base = compareBase(gu, selectedMonths);
        return { avgForecast: avg(fc), change: pct(avg(fc), avg(base.values)), baseLabel: base.label };
    }

    // 실적 구간 : 월 실적이 있으면 약 2년(history), 없으면 평가 기간 6개월
    const historyMonths = () => T.history_months || T.test_months;
    const historyOf = gu => T.districts[gu].history || T.districts[gu].actual;

    // 실제 실적 + 평가 기간 예측 + 2026 예측 (+ 1년 전 같은 달)
    function demandData(gu, n, withTest) {
        const d = T.districts[gu];
        const hist = historyOf(gu);
        const last = hist[hist.length - 1];
        const labels = historyMonths().map(fmtMonth)
            .concat(T.future_months.slice(0, n).map(m => fmtMonth(m) + ' (예측)'));
        const sets = [{
            label: '실제',
            data: hist.concat(pad(n)),
            borderColor: '#2563eb',
            backgroundColor: 'rgba(37, 99, 235, 0.08)',
            borderWidth: 2.5, fill: true, tension: 0.3, pointRadius: 3
        }];
        if (withTest) {
            sets.push({
                label: '평가',
                data: d.test_pred.concat(pad(n)),
                borderColor: '#10b981',
                borderDash: [4, 3],
                borderWidth: 2, fill: false, tension: 0.3, pointRadius: 3
            });
        }
        sets.push({
            label: '예측',
            data: pad(hist.length - 1).concat([last], d.forecast.slice(0, n)),
            borderColor: '#dc2626',
            borderDash: [6, 4],
            borderWidth: 2.5, fill: false, tension: 0.3, pointRadius: 3, pointStyle: 'rectRot'
        });
        if (withTest && d.last_year) {
            sets.push({
                label: '1년 전',
                data: pad(hist.length).concat(d.last_year.slice(0, n)),
                borderColor: '#94a3b8',
                borderDash: [2, 4],
                borderWidth: 1.5, fill: false, tension: 0.3, pointRadius: 2
            });
        }
        return { labels: labels, datasets: sets };
    }

    function updateKPIs(gu) {
        const d = T.districts[gu];
        const s = periodStats(gu);
        document.getElementById('kpiAvgDemand').innerText = fmtNum(s.avgForecast) + ' 건';
        const avgSub = document.getElementById('kpiAvgSub');
        avgSub.innerText = s.baseLabel + ' 대비 ' + pctText(s.change);
        avgSub.className = 'kpi-sub ' + pctClass(s.change);

        const fc = d.forecast.slice(0, selectedMonths);
        const peakIdx = fc.indexOf(Math.max(...fc));
        document.getElementById('kpiPeakMonth').innerText = fmtMonth(T.future_months[peakIdx]);
        document.getElementById('kpiPeakSub').innerText = '예상 ' + fmtNum(fc[peakIdx]) + '건 (' + guLabel(gu) + ')';

        // 선택 지역 평가 정확도 (서울 전체 = 최종 모델 전체 점수)
        document.getElementById('kpiGuAccLabel').innerText = (gu === ALL ? '서울 전체' : gu) + ' 예측 모델 정확도';
        const accEl = document.getElementById('kpiGuAcc');
        const accSub = document.getElementById('kpiGuAccSub');
        if (gu === ALL) {
            const best = scoreOf(T.best_model);
            accEl.innerText = fmt2(col(best, '평가', '6개월', '정확도')) + '%';
            accSub.innerText = '25개 구 전체 · MAE ' + fmt1(col(best, '평가', '6개월', 'MAE')) + '건';
        } else {
            const r = diagOf(gu);
            accEl.innerText = r ? fmt2(r['평가_정확도(%)']) + '%' : '-';
            accSub.innerText = r ? ('MAE ' + fmt1(r['평가_MAE']) + '건' + (r['관할변경'] ? ' · 관할 변경' : '')) : '-';
        }
    }

    function rankingItem(name, rankHtml, s, isTotal) {
        const item = document.createElement('div');
        item.className = 'district-item' + (isTotal ? ' total' : '') + (name === selectedGu ? ' active' : '');
        item.onclick = () => selectDistrict(name, false);
        item.innerHTML =
            '<div class="district-info">' + rankHtml + '<span>' + guLabel(name) + '</span></div>' +
            '<span class="predict-inline-32">월평균 ' + fmtNum(s.avgForecast) + '건' +
            '<span class="predict-inline-33"> (' + pctText(s.change) + ')</span></span>';
        return item;
    }

    function updateRanking() {
        const rows = guList()
            .map(name => Object.assign({ name: name }, periodStats(name)))
            .sort((a, b) => b.avgForecast - a.avgForecast);

        const list = document.getElementById('districtList');
        list.innerHTML = '';
        list.appendChild(rankingItem(ALL, '<span class="rank-num">∑</span>', periodStats(ALL), true));
        rows.forEach((r, i) => {
            const rankClass = i < 3 ? ' rank-' + (i + 1) : '';
            list.appendChild(rankingItem(r.name, '<span class="rank-num' + rankClass + '">' + (i + 1) + '</span>', r, false));
        });

        const top = rows.slice().sort((a, b) => b.change - a.change)[0];
        document.getElementById('kpiRiskGu').innerText = top.name;
        const sub = document.getElementById('kpiRiskSub');
        document.getElementById('kpiRiskLabel').innerText = top.baseLabel + ' 대비 증가율 1위 지역';
        sub.innerText = top.baseLabel + ' 대비 ' + pctText(top.change) + ' · 월평균 ' + fmtNum(top.avgForecast) + '건';
        sub.className = 'kpi-sub ' + pctClass(top.change);
    }

    function updateDashboard() {
        const gu = selectedGu;
        const months = T.future_months.slice(0, selectedMonths);
        document.getElementById('guChip').innerText = guLabel(gu);
        document.getElementById('chartGu').innerText = guLabel(gu);
        document.getElementById('chartSubtitle').innerText =
            '실적 ' + fmtMonth(historyMonths()[0]) + ' ~ ' + fmtMonth(historyMonths()[historyMonths().length - 1]) +
            ' · 예측 ' + fmtMonth(months[0]) + ' ~ ' + fmtMonth(months[months.length - 1]);
        demandChart.data = demandData(gu, selectedMonths, true);
        demandChart.update();
        drawLegend(demandChart);
        updateKPIs(gu);
        updateRanking();
        updatePopChart();
        document.querySelectorAll('tr[data-gu]').forEach(tr => tr.classList.toggle('active', tr.dataset.gu === gu));
    }

    function selectDistrict(gu, scroll) {
        if (!T.districts[gu]) return;
        selectedGu = gu;
        updateDashboard();
        if (scroll) document.getElementById('demandCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function setForecastPeriod(months, btn) {
        selectedMonths = months;
        document.querySelectorAll('#monthTabs .tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (D) updateDashboard();
    }

    function fillPeriodTabs() {
        const fm = T.future_months;
        document.getElementById('forecastRange').innerText = fmtMonth(fm[0]) + ' ~ ' + fmtMonth(fm[fm.length - 1]);
        document.querySelectorAll('#monthTabs .tab-btn').forEach((b, i) => {
            if (fm[i]) b.title = fmtMonth(fm[0]) + ' ~ ' + fmtMonth(fm[i]);
            else b.style.display = 'none';
        });
        if (selectedMonths > fm.length) selectedMonths = fm.length;
    }

    // ---------- 02. 2026 상반기 예측 ----------
    function buildTop4() {
        const top = guList()
            .map(name => ({ name: name, total: sum(T.districts[name].forecast) }))
            .sort((a, b) => b.total - a.total)
            .slice(0, 4);
        const grid = document.getElementById('top4Grid');
        grid.innerHTML = '';
        top.forEach((t, i) => {
            const card = document.createElement('div');
            card.className = 'card p-card';
            card.innerHTML =
                '<div class="card-title"><span>' + (i + 1) + '위 · ' + t.name + '</span>' +
                '<span class="hint">6개월 예측 합계 ' + fmtNum(t.total) + '건</span></div>' +
                '<div class="mini-chart"><canvas></canvas></div>';
            grid.appendChild(card);
            const data = demandData(t.name, T.future_months.length, false);
            data.datasets[0].borderColor = PALETTE[i];
            data.datasets[0].fill = false;
            makeChart(card.querySelector('canvas'), { type: 'line', data: data, options: lineOptions() });
        });
    }

    function buildForecastTable() {
        const fm = T.future_months;
        const rows = guList()
            .map(name => ({ name: name, fc: T.districts[name].forecast, prev: compareBase(name, fm.length).values }))
            .sort((a, b) => sum(b.fc) - sum(a.fc));

        const cells = fc => {
            const lo = Math.min(...fc), hi = Math.max(...fc);
            return fc.map(v => {
                const level = hi === lo ? 0 : (v - lo) / (hi - lo);
                return '<td class="predict-inline-34">' + fmtNum(v) + '</td>';
            }).join('');
        };
        const row = (r, extra) => {
            const ch = pct(sum(r.fc), sum(r.prev));
            return '<tr data-gu="' + r.name + '" class="' + extra + '"><td>' + guLabel(r.name) + '</td>' + cells(r.fc) +
                '<td class="total">' + fmtNum(sum(r.fc)) + '</td>' +
                '<td class="' + pctClass(ch) + ' predict-inline-35">' + pctText(ch) + '</td></tr>';
        };
        const seoul = { name: ALL, fc: T.districts[ALL].forecast, prev: compareBase(ALL, fm.length).values };
        const baseLabel = compareBase(ALL, fm.length).label;
        document.getElementById('fcTable').innerHTML =
            '<thead><tr><th>자치구</th>' + fm.map(m => '<th>' + fmtMonth(m) + '</th>').join('') +
            '<th>합계</th><th>' + baseLabel + ' 대비</th></tr></thead>' +
            '<tbody>' + row(seoul, 'seoul') + rows.map(r => row(r, '')).join('') + '</tbody>';
        document.querySelectorAll('#fcTable tbody tr').forEach(tr =>
            tr.addEventListener('click', () => selectDistrict(tr.dataset.gu, true)));

        document.getElementById('fcDesc').innerText =
            D.meta.data_start + ' ~ ' + D.meta.data_end + ' 실적으로 학습한 ' + T.best_model + ' 모델의 ' +
            fmtMonth(fm[0]) + ' ~ ' + fmtMonth(fm[fm.length - 1]) + ' 예측입니다. ' +
            (baseLabel === '전년 동기'
                ? '전년 동기 대비는 1년 전 같은 달(' + fmtMonth(prevYear(fm[0])) + ' ~ ' +
                  fmtMonth(prevYear(fm[fm.length - 1])) + ') 실적 합계와 비교한 값입니다.'
                : '직전 6개월 대비는 ' + fmtMonth(T.test_months[0]) + ' ~ ' + fmtMonth(T.test_months[T.test_months.length - 1]) +
                  ' 실적과 비교한 값이라 계절 차이가 함께 들어 있습니다.');
    }

    // ---------- 03. 평가 기간 자치구별 정확도 ----------
    function buildTestSection() {
        const rows = T.by_gu.slice().sort((a, b) => b['평가_정확도(%)'] - a['평가_정확도(%)']);
        const color = r => r['관할변경'] ? '#f97316' : (r['평가_유형'] === '수준 변화형' ? '#7c3aed' : '#2563eb');
        const accs = rows.map(r => r['평가_정확도(%)']);

        makeChart(document.getElementById('guAccChart'), {
            type: 'bar',
            data: {
                labels: rows.map(r => r['지역구명']),
                datasets: [{ label: '평가 정확도(%)', data: accs, backgroundColor: rows.map(color), borderRadius: 4 }]
            },
            options: hbarOptions(Math.floor(Math.min(...accs) - 1), 100, v => v + '%', gu => selectDistrict(gu, true))
        });
        renderLegend(legendBox(document.getElementById('guAccChart')), [
            { label: '변동형', color: '#2563eb', kind: 'box' },
            { label: '수준 변화형', color: '#7c3aed', kind: 'box' },
            { label: '관할 변경', color: '#f97316', kind: 'box' },
        ]);

        const pill = (text, cls) => '<span class="pill ' + cls + '">' + text + '</span>';
        document.getElementById('diagTable').innerHTML =
            '<thead><tr><th>자치구</th><th>검증 정확도</th><th>평가 정확도</th><th>평가 MAE</th>' +
            '<th>평가 편향</th><th>평가 유형</th><th>관할</th></tr></thead><tbody>' +
            rows.map(r =>
                '<tr data-gu="' + r['지역구명'] + '"><td>' + r['지역구명'] + '</td>' +
                '<td>' + fmt2(r['검증_정확도(%)']) + '%</td>' +
                '<td class="predict-inline-36">' + fmt2(r['평가_정확도(%)']) + '%</td>' +
                '<td>' + (r['평가_MAE'] === null ? '-' : fmt1(r['평가_MAE']) + '건') + '</td>' +
                '<td class="' + (r['평가_편향(%)'] >= 0 ? 'up' : 'down') + '">' + pctText(r['평가_편향(%)']) + '</td>' +
                '<td>' + pill(r['평가_유형'], r['평가_유형'] === '수준 변화형' ? 'level' : 'wave') + '</td>' +
                '<td>' + (r['관할변경'] ? pill('변경', 'change') : '') + '</td></tr>'
            ).join('') + '</tbody>';
        document.querySelectorAll('#diagTable tbody tr').forEach(tr =>
            tr.addEventListener('click', () => selectDistrict(tr.dataset.gu, true)));

        const changed = rows.filter(r => r['관할변경']).map(r => r['지역구명'] + '(학습 ' + r['학습행수'] + '행)');
        const worst = rows[rows.length - 1], best = rows[0];
        document.getElementById('testDesc').innerText =
            D.meta.test_period + ' 6개월 동안 실제 이송 건수와 예측을 비교한 결과입니다. ' +
            '가장 높은 구는 ' + best['지역구명'] + ' ' + fmt2(best['평가_정확도(%)']) + '%, 가장 낮은 구는 ' +
            worst['지역구명'] + ' ' + fmt2(worst['평가_정확도(%)']) + '%입니다. ' +
            '보라 = 수준 변화형(예측이 한쪽으로 치우친 오차), 파랑 = 변동형(달마다 오르내리는 오차)' +
            (changed.length ? ', 주황 = 소방서 관할 변경으로 학습 기간이 짧은 구 : ' + changed.join(', ') : '') + '.';
    }

    // ---------- 04. 생활인구 ----------
    function popData(gu) {
        const d = P.daily[gu];
        return {
            labels: P.dates,
            datasets: [
                { label: '실제', data: d.actual, borderColor: '#7c3aed', borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
                { label: '예측', data: d.pred, borderColor: '#f59e0b', borderDash: [4, 3], borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
            ]
        };
    }

    function updatePopChart() {
        if (!popChart || !P.daily[selectedGu]) return;
        document.getElementById('popGu').innerText = guLabel(selectedGu);
        popChart.data = popData(selectedGu);
        popChart.update();
        drawLegend(popChart);
    }

    function buildPopSection() {
        if (!P) { document.getElementById('popSection').style.display = 'none'; return; }
        const models = P.scores.filter(r => !isBase(r['모델'])).sort((a, b) => b['평가_정확도(%)'] - a['평가_정확도(%)']);
        const best = models[0];
        const base = P.scores.find(r => isBase(r['모델']));

        document.getElementById('popDesc').innerText =
            fmtMonth(P.dates[0]) + '.' + P.dates[0].slice(8) + ' ~ ' + fmtMonth(P.dates[P.dates.length - 1]) + '.' +
            P.dates[P.dates.length - 1].slice(8) + ' (' + P.dates.length + '일) 동안 자치구별 하루 최대 생활인구를 예측한 평가 결과입니다. ' +
            '최고 모델은 ' + best['모델'] + '입니다.';

        const box = (label, value, sub) =>
            '<div class="stat-box"><div class="label">' + label + '</div><div class="value">' + value + '</div><div class="sub">' + sub + '</div></div>';
        document.getElementById('popStats').innerHTML =
            box('최고 모델 평가 정확도', fmt2(best['평가_정확도(%)']) + '%', best['모델'] + ' · 검증 ' + fmt2(best['검증_정확도(%)']) + '%') +
            box('평가 R²', Number(best['평가_R2']).toFixed(3), base ? base['모델'] + ' ' + Number(base['평가_R2']).toFixed(3) : '') +
            box('평가 MAE', fmtNum(best['평가_MAE']) + '명', base ? base['모델'] + ' ' + fmtNum(base['평가_MAE']) + '명' : '');

        const opts = lineOptions(v => (v / 10000).toFixed(0) + '만');
        opts.plugins.tooltip.callbacks.label = c => c.dataset.label + ' : ' + fmtNum(c.raw) + '명';
        popChart = makeChart(document.getElementById('popChart'), { type: 'line', data: popData(P.daily[selectedGu] ? selectedGu : ALL), options: opts });

        const rows = P.by_gu.slice().sort((a, b) => b['정확도(%)'] - a['정확도(%)']);
        const accs = rows.map(r => r['정확도(%)']);
        const o = hbarOptions(Math.floor(Math.min(...accs) - 1), 100, v => v + '%', gu => selectDistrict(gu, false));
        makeChart(document.getElementById('popAccChart'), {
            type: 'bar',
            data: { labels: rows.map(r => r['지역구명']), datasets: [{ label: '평가 정확도(%)', data: accs, backgroundColor: '#a78bfa', borderRadius: 3 }] },
            options: o
        });
    }

    // ---------- 05. 관계 분석 ----------
    function buildRelationSection() {
        if (!R) { document.getElementById('relSection').style.display = 'none'; return; }

        const corr = R.corr.slice().sort((a, b) => b['자치구간'] - a['자치구간']);
        makeChart(document.getElementById('corrChart'), {
            type: 'bar',
            data: {
                labels: corr.map(r => featureKo(r['특성'])),
                datasets: [
                    { label: '구 사이', data: corr.map(r => r['자치구간']), backgroundColor: '#2563eb', borderRadius: 3 },
                    { label: '같은 구 안', data: corr.map(r => r['자치구내_계절제거']), backgroundColor: '#67e8f9', borderRadius: 3 }
                ]
            },
            options: hbarOptions(-0.2, 1, v => v.toFixed(1))
        });

        const rate = R.district_rate.slice().sort((a, b) => b['인구1만명당_이송률'] - a['인구1만명당_이송률']);
        const ro = hbarOptions(0, Math.ceil(Math.max(...rate.map(r => r['인구1만명당_이송률'])) + 2), v => v, gu => selectDistrict(gu, true));
        ro.plugins.tooltip = { callbacks: { label: c => fmt2(c.raw) + '건 / 1만 명 · 월평균 ' + fmtNum(rate[c.dataIndex]['월평균_이송건수']) + '건' } };
        makeChart(document.getElementById('rateChart'), {
            type: 'bar',
            data: { labels: rate.map(r => r['지역구명']), datasets: [{ label: '인구 1만 명당 이송', data: rate.map(r => r['인구1만명당_이송률']), backgroundColor: '#f87171', borderRadius: 3 }] },
            options: ro
        });

        // 특성 조합 × 모델 평가 정확도 (+ 기준선 선)
        const mc = R.model_compare;
        const combos = [...new Set(mc.filter(r => !isBase(r['특성조합'])).map(r => r['특성조합']))];
        const models = [...new Set(mc.filter(r => !isBase(r['특성조합'])).map(r => r['모델']))];
        const base = mc.find(r => isBase(r['특성조합']));
        const val = (c, m) => { const r = mc.find(x => x['특성조합'] === c && x['모델'] === m); return r ? r['평가_정확도(%)'] : null; };
        const sets = models.map((m, i) => ({ type: 'bar', label: m, data: combos.map(c => val(c, m)), backgroundColor: PALETTE[i], borderRadius: 3 }));
        if (base) {
            sets.push({ type: 'line', label: '기준선', data: combos.map(() => base['평가_정확도(%)']),
                        borderColor: '#94a3b8', borderDash: [6, 4], borderWidth: 2, pointRadius: 0 });
        }
        const all = mc.map(r => r['평가_정확도(%)']);
        makeChart(document.getElementById('relModelChart'), {
            data: { labels: combos.map(c => c.replace('_', ' ')), datasets: sets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: LABEL }, grid: { display: false } },
                    y: { min: Math.floor(Math.min(...all) - 1), max: 100, ticks: { color: TICK, callback: v => v + '%' }, grid: { color: GRID } }
                },
                plugins: {
                    tooltip: { callbacks: { label: c => c.dataset.label + ' ' + (c.raw === null ? '-' : fmt2(c.raw) + '%') } }
                }
            }
        });

        // 설명 문장 (값은 데이터에서 계산)
        const topBetween = corr[0];
        const topWithin = R.corr.slice().sort((a, b) => b['자치구내_계절제거'] - a['자치구내_계절제거'])[0];
        const bestOf = c => Math.max(...models.map(m => val(c, m)).filter(v => v !== null));
        const comboText = combos.map(c => '<strong>' + c.replace('_', ' ') + '</strong> ' + fmt2(bestOf(c)) + '%').join(' · ');
        document.getElementById('relInsight').innerHTML =
            '구별 평균을 비교하면 이송 건수와 <strong>' + featureKo(topBetween['특성']) + '</strong>의 상관계수가 <strong>' +
            fmt2(topBetween['자치구간']) + '</strong>까지 높습니다. 반면 같은 구 안에서 달마다 변하는 정도(계절 제거)의 상관계수는 ' +
            '가장 높은 ' + featureKo(topWithin['특성']) + '도 <strong>' + fmt2(topWithin['자치구내_계절제거']) + '</strong>에 그칩니다. ' +
            '즉 인구는 "어느 구가 많은지"는 잘 설명하지만 "다음 달 얼마나 늘지"는 약하게 설명합니다.<br>' +
            '특성 조합별 최고 평가 정확도 : ' + comboText + (base ? ' · 기준선(전월값) ' + fmt2(base['평가_정확도(%)']) + '%' : '');
    }

    // ---------- 06. 표본 ----------
    function buildSampleSection() {
        const S = D.sample;
        if (!S || !S.type_labels || !S.type_labels.length) {
            document.getElementById('sampleSection').style.display = 'none';
            return;
        }
        const note = '출처 : ' + S.title + ' (예측값이 아닌 실제 표본 구성비)';
        document.getElementById('sampleNote1').innerText = note;
        document.getElementById('sampleNote2').innerText = note;
        makeChart(document.getElementById('diseaseChart'), {
            type: 'doughnut',
            data: { labels: S.type_labels, datasets: [{ data: S.type_values,
                    backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#94a3b8'], borderWidth: 2, borderColor: '#ffffff' }] },
            options: { responsive: true, maintainAspectRatio: false,
                       plugins: { tooltip: { callbacks: { label: c => c.label + ' ' + c.raw + '%' } } } }
        });
        makeChart(document.getElementById('ageChart'), {
            type: 'bar',
            data: { labels: S.age_labels, datasets: [{ label: '비율(%)', data: S.age_values, backgroundColor: 'rgba(37, 99, 235, 0.75)', borderRadius: 6 }] },
            options: { responsive: true, maintainAspectRatio: false,
                       scales: { x: { ticks: { color: TICK }, grid: { display: false } },
                                 y: { ticks: { color: TICK, callback: v => v + '%' }, grid: { color: GRID } } },
                       plugins: {} }
        });
    }

    // ---------- 07. 모델 명세 ----------
    function fillModelInfo() {
        const m = D.meta;
        const best = scoreOf(T.best_model);
        const base = T.scores.find(r => r['모델'].includes('마지막'));
        const bases = T.scores.filter(r => isBase(r['모델'])).map(r => r['모델']);
        const nModels = T.scores.length - bases.length;
        const testAcc = col(best, '평가', '6개월', '정확도');
        const validAcc = col(best, '검증', '6개월', '정확도');
        const testMae = col(best, '평가', '6개월', 'MAE');

        document.getElementById('bestAccLabel').innerText = '최종 모델 평가 정확도 (' + m.test_period + ', 6개월 연속 예측)';
        document.getElementById('bestAcc').innerText = fmt2(testAcc) + '%';
        document.getElementById('bestAccSub').innerText =
            T.best_model + ' · MAE ' + fmt1(testMae) + '건 · 검증 정확도 ' + fmt2(validAcc) + '%';

        if (base) {
            const baseAcc = col(base, '평가', '6개월', '정확도');
            const baseMae = col(base, '평가', '6개월', 'MAE');
            document.getElementById('baseGain').innerText = (testAcc - baseAcc >= 0 ? '+' : '') + fmt2(testAcc - baseAcc) + '%p';
            document.getElementById('baseGainSub').innerText =
                '기준선 ' + fmt2(baseAcc) + '% · MAE ' + fmt1(baseMae) + '건 → ' + fmt1(testMae) + '건 (' +
                fmt1((baseMae - testMae) / baseMae * 100) + '% 감소)';
        }

        document.getElementById('modelIntro').innerText =
            '서울시 25개 자치구의 월별 이송 실적(' + m.data_start + ' ~ ' + m.data_end + ')으로 모델 ' + nModels + '종과 기준선 ' +
            bases.length + '종을 비교하고, 검증 6개월 정확도가 가장 높은 ' + T.best_model + ' 모델로 ' +
            fmtMonth(T.future_months[0]) + ' ~ ' + fmtMonth(T.future_months[T.future_months.length - 1]) + ' 6개월을 예측했습니다.';

        const changed = T.by_gu.filter(r => r['관할변경']).map(r => r['지역구명']);
        const li = items => items.filter(Boolean).map(t => '<li>' + t + '</li>').join('');
        document.getElementById('dataInfo').innerHTML = li([
            m.source_file ? '<strong>원본 파일</strong> : ' + m.source_file : null,
            '<strong>데이터 기간</strong> : ' + m.data_start + ' ~ ' + m.data_end + lateStartText(),
            '<strong>예측 기간</strong> : ' + m.forecast_period,
            '<strong>학습 행 수</strong> : ' + m.train_rows.toLocaleString() + '행 (자치구 × 월)',
            changed.length ? '<strong>관할 변경 구</strong> : ' + changed.join(', ') + ' (변경 이후 기간만 학습)' : null,
            m.calendar_features.length ? '<strong>달력 특성</strong> : ' + m.calendar_features.join(', ') : null,
        ]);
        document.getElementById('validInfo').innerHTML = li([
            m.valid_period ? '<strong>검증 기간</strong> : ' + m.valid_period : null,
            '<strong>평가 기간</strong> : ' + m.test_period,
            '<strong>방식</strong> : 6개월 재귀 예측(예측값을 다음 달 입력으로 사용) · 1개월 예측도 함께 비교',
            '<strong>정확도</strong> : 100 − MAPE(평균 절대 백분율 오차)',
            '<strong>기준선</strong> : ' + bases.join(', '),
        ]);
    }

    // 실적 시작이 늦은 구 (예: 관할 변경으로 새로 생긴 소방서)
    function lateStartText() {
        const starts = T.gu_start || {};
        const late = Object.keys(starts).filter(g => starts[g] > D.meta.data_start).sort();
        return late.length ? ' (' + late.map(g => g + ' ' + starts[g] + '~').join(', ') + ')' : '';
    }

    // 접힌 카드를 처음 펼칠 때 그림 (접힌 상태에서는 크기를 잴 수 없음)
    function buildDetail() {
        if (detailBuilt) return;
        detailBuilt = true;

        const models = T.scores.slice().sort((a, b) => col(b, '평가', '6개월', '정확도') - col(a, '평가', '6개월', '정확도'));
        const sets = [
            { label: '검증 6개월', words: ['검증', '6개월', '정확도'], colors: ['#6ee7b7', '#cbd5e1', '#93c5fd'] },
            { label: '평가 6개월', words: ['평가', '6개월', '정확도'], colors: ['#059669', '#94a3b8', '#2563eb'] },
            { label: '평가 1개월', words: ['평가', '1개월', '정확도'], colors: ['#a7f3d0', '#e2e8f0', '#c4b5fd'] },
        ].filter(s => col(models[0], ...s.words) !== null).map(s => ({
            label: s.label,
            legendColor: s.colors[2],
            data: models.map(r => col(r, ...s.words)),
            backgroundColor: models.map(r => r['모델'] === T.best_model ? s.colors[0] : isBase(r['모델']) ? s.colors[1] : s.colors[2]),
            borderRadius: 3
        }));
        const all = sets.flatMap(s => s.data);
        makeChart(document.getElementById('modelChart'), {
            type: 'bar',
            data: { labels: models.map(r => (r['모델'] === T.best_model ? '★ ' : '') + r['모델']), datasets: sets },
            options: hbarOptions(Math.floor(Math.min(...all) - 1), 100, v => v + '%')
        });

        // 상세 점수표
        const rows = T.detail;
        const keys = Object.keys(rows[0]);
        const cell = v => typeof v === 'number' ? (Math.abs(v) < 1.5 ? v.toFixed(3) : v.toFixed(2)) : v;
        document.getElementById('detailTable').innerHTML =
            '<thead><tr>' + keys.map(k => '<th>' + k + '</th>').join('') + '</tr></thead><tbody>' +
            rows.map(r => '<tr' + (r['모델'] === T.best_model ? ' class="seoul"' : '') + '>' +
                keys.map(k => '<td>' + cell(r[k]) + '</td>').join('') + '</tr>').join('') + '</tbody>';

        // 개선 실험
        const ex = T.experiment;
        if (ex.length) {
            const settings = [...new Set(ex.map(r => r['설정']))];
            const exModels = [...new Set(ex.map(r => r['모델']))];
            const v = (s, m) => { const r = ex.find(x => x['설정'] === s && x['모델'] === m); return r ? col(r, '6개월', '정확도') : null; };
            const vals = ex.map(r => col(r, '6개월', '정확도'));
            makeChart(document.getElementById('expChart'), {
                type: 'bar',
                data: { labels: settings, datasets: exModels.map((m, i) => ({ label: m, data: settings.map(s => v(s, m)), backgroundColor: PALETTE[i], borderRadius: 3 })) },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: { x: { ticks: { color: LABEL }, grid: { display: false } },
                              y: { min: Math.floor(Math.min(...vals) - 1), max: 100, ticks: { color: TICK, callback: x => x + '%' }, grid: { color: GRID } } },
                    plugins: {}
                }
            });
        }
    }

    // 03~07 상세 분석 : 처음 펼칠 때 한 번만 그림 (접힌 상태에서는 차트 크기를 잴 수 없음)
    let detailFoldBuilt = false;
    function buildDetailFold() {
        if (detailFoldBuilt) return;
        detailFoldBuilt = true;
        buildTestSection();
        buildPopSection();
        buildRelationSection();
        buildSampleSection();
        updatePopChart();
        document.querySelectorAll('tr[data-gu]').forEach(tr => tr.classList.toggle('active', tr.dataset.gu === selectedGu));
        lucide.createIcons();
    }

    // ---------- 기본 정보 · 기간 확인 ----------
    function fillHeader() {
        const m = D.meta;

        document.getElementById('systemInfo').innerText =
            '최근 모델 학습 · ' + (D.meta.generated_at || D.meta.created_at || D.meta.updated_at || D.meta.data_end || '-');
    }

    function checkPeriod() {
        const end = D.meta.data_end;
        const start = T.future_months[0];
        if (end === EXPECTED_DATA_END && start === EXPECTED_FORECAST_START) return;
        const banner = document.getElementById('warnBanner');
        banner.innerHTML =
            '불러온 대시보드 데이터가 최신 결과가 아닙니다. 현재 파일은 <strong>학습 ~' + end + ' · 예측 ' + start +
            '부터</strong>입니다. (기대값 : 학습 ~' + EXPECTED_DATA_END + ' · 예측 ' + EXPECTED_FORECAST_START + '부터)<br>' +
            '노트북 결과 csv로 <code>dashboard_build</code>를 다시 실행한 뒤 새로고침하세요.';
        banner.style.display = 'block';
    }

    // ---------- 데이터 불러오기 ----------
    // 1) Flask 서버 : /api/dashboard-data   2) 실패 시 : /static/dashboard_data.js
    function loadScript(src) {
        return new Promise(resolve => {
            const tag = document.createElement('script');
            tag.src = src;
            tag.onload = () => resolve(typeof DASHBOARD_DATA !== 'undefined' ? DASHBOARD_DATA : null);
            tag.onerror = () => resolve(null);
            document.body.appendChild(tag);
        });
    }

    async function loadDashboardData() {
        try {
            const res = await fetch('/api/dashboard-data', { cache: 'no-store' });
            if (res.ok) return await res.json();
        } catch (e) {
            console.warn('API 연결 실패, js 파일로 대체', e);
        }
        return await loadScript("{{ url_for('static', filename='dashboard_data.js') }}");
    }

    window.onload = async () => {
        D = await loadDashboardData();
        if (!D || !D.transport) {
            const banner = document.getElementById('errorBanner');
            if (D) banner.innerHTML = '대시보드 데이터가 예전 형식입니다. <code>dashboard_build</code>로 ' +
                '<code>outputs/dashboard_data.json</code>을 다시 만든 뒤 새로고침하세요.';
            banner.style.display = 'block';
            document.getElementById('systemInfo').innerText = '데이터 없음';
            return;
        }
        T = D.transport;
        P = D.population;
        R = D.relation;

        checkPeriod();
        fillHeader();
        fillPeriodTabs();
        fillModelInfo();

        demandChart = makeChart(document.getElementById('demandChart'), {
            type: 'line', data: demandData(ALL, selectedMonths, true), options: lineOptions()
        });
        
        
        document.getElementById('detailFold').addEventListener('toggle', e => { if (e.target.open) buildDetailFold(); });
        document.getElementById('modelDetails').addEventListener('toggle', e => { if (e.target.open) buildDetail(); });

        updateDashboard();
        lucide.createIcons();
    };

// HTML 인라인 onclick 대신 이벤트 리스너 사용
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#monthTabs [data-forecast-month]').forEach((btn) => {
        btn.addEventListener('click', () => {
            setForecastPeriod(Number(btn.dataset.forecastMonth), btn);
        });
    });
});
