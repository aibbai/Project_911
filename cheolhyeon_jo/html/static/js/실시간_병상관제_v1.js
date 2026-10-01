// 실시간_병상관제_v1 화면 동작 (데이터 조회·필터·카드 그리기)

const districtZones = {"강남구":"동남권","강동구":"동남권","강북구":"동북권","강서구":"서남권","관악구":"서남권","광진구":"동북권","구로구":"서남권","금천구":"서남권","노원구":"동북권","도봉구":"동북권","동대문구":"동북권","동작구":"서남권","마포구":"서북권","서대문구":"서북권","서초구":"동남권","성동구":"동북권","성북구":"동북권","송파구":"동남권","양천구":"서남권","영등포구":"서남권","용산구":"도심권","은평구":"서북권","종로구":"도심권","중구":"도심권","중랑구":"동북권"};
const districtNames = Object.keys(districtZones);
// 구별 가용 병상 합계 기준
const CRITICAL_BED_LIMIT = 5;    // 위험 : 5석 이하
const WARNING_BED_LIMIT = 10;    // 주의 : 10석 이하
const fmt = n => Number(n ?? 0).toLocaleString('ko-KR', {maximumFractionDigits:1});

function formatApiDate(value) {
    if (!value) return '-';
    const s = String(value).replace(/\D/g, '');
    if (s.length >= 14) {
        return `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)} ${s.slice(8,10)}:${s.slice(10,12)}:${s.slice(12,14)}`;
    }
    if (s.length >= 12) {
        return `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)} ${s.slice(8,10)}:${s.slice(10,12)}`;
    }
    return value;
}

// 병원 이름 등 외부 데이터를 화면에 넣기 전 특수문자 처리
function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

const HOSPITAL_NAME_REMOVE = [
    '학교법인', '의료법인', '재단법인', '가톨릭학원', '고려중앙학원','학교 ','학교',
    '풍산의료재단', '한전의료재단', '성화의료재단', '동신의료재단', '성애의료재단',
    '성심의료재단', '서울효천의료재단', '아산사회복지재단', '한국보훈복지의료공단','서울특별시',
    '가톨릭대학교', '인제대학교', '연세대학교의과대학', '한림대학교', '한국원자력의학원', '의과대학부속',
];
const HOSPITAL_NAME_REGEX = new RegExp(HOSPITAL_NAME_REMOVE.join('|'), 'g');

function cleanHospitalName(name) {
    return String(name ?? '')
        .replace(HOSPITAL_NAME_REGEX, '')
	.replace('여자', '여')
        .replace(/\s+/g, ' ')
        .trim();
}

function hospitalRisk(h) {
    const b = Number(h.Available_Beds);
    if (h.Available_Beds === null || !Number.isFinite(b)) return 'unknown';
    if (b <= 0) return 'high';
    if (b <= 3) return 'medium';
    return 'low';
}

function districtRisk(result) {
    const hospitals = result.hospitals || [];
    if (result.data_type === 'static_er_beds') return 'static';
    const known = hospitals.filter(h => hospitalRisk(h) !== 'unknown');
    if (!known.length) return 'unknown';
    // 구 전체 가용 병상 합계로 위험도 판단
    const districtBeds = known.reduce((sum, h) => sum + Math.max(0, Number(h.Available_Beds)), 0);
    if (districtBeds <= CRITICAL_BED_LIMIT) return 'high';
    if (districtBeds <= WARNING_BED_LIMIT) return 'medium';
    return 'low';
}

// 위험/주의 카드 클릭 → 해당 위험도 구만 보기 (한 번 더 누르면 전체 보기)
function showDistrictsByRisk(risk) {
    const riskSelect = document.getElementById('realtime-risk-filter');
    const next = riskSelect.value === risk ? 'all' : risk;

    document.getElementById('realtime-search-input').value = '';
    document.getElementById('realtime-zone-filter').value = 'all';
    riskSelect.value = next;
    filterRealtime();

    if (next !== 'all') {
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        document.getElementById('realtime-card-grid').scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth'});
    }
}

// 현재 선택된 위험도 카드에 테두리 강조
function updateRiskCardState(risk) {
    const cards = {high: 'risk-card-high', medium: 'risk-card-medium'};
    Object.entries(cards).forEach(([key, id]) => {
        const el = document.getElementById(id);
        if (!el) return;
        const on = risk === key;
        el.setAttribute('aria-pressed', String(on));
        el.classList.toggle('ring-2', on);
        el.classList.toggle(key === 'high' ? 'ring-red-400' : 'ring-amber-400', on);
    });
}

async function fetchRealtimeDistrict(d) {
    try {
        const r = await fetch(`/api/realtime-beds?district=${encodeURIComponent(d)}`);
        if (!r.ok) throw new Error('API ' + r.status);
        return await r.json();
    } catch(e) {
        return {district:d, hospitals:[], error:e.message};
    }
}

// 25개 구를 한 번에 받고, 실패하면 구별로 다시 요청
async function fetchRealtimeAll() {
    try {
        const r = await fetch('/api/realtime-beds/all');
        if (!r.ok) throw new Error('API ' + r.status);
        const data = await r.json();
        return {results: data.districts || [], updatedAt: data.snapshot_updated_at};
    } catch(e) {
        const results = await Promise.all(districtNames.map(fetchRealtimeDistrict));
        return {results, updatedAt: results[0]?.snapshot_updated_at};
    }
}

function updateRealtimeSummary(results) {
    const allHospitals = results.flatMap(x => x.hospitals || []);
    const knownHospitals = allHospitals.filter(h => hospitalRisk(h) !== 'unknown');
    const totalBeds = knownHospitals.reduce((sum, h) => sum + Math.max(0, Number(h.Available_Beds)), 0);

    document.getElementById('realtime-target-count').textContent = `${districtNames.length}개 구 전체`;
    document.getElementById('realtime-critical-count').textContent = `${results.filter(x => districtRisk(x) === 'high').length}개 구`;
    document.getElementById('realtime-warning-count').textContent = `${results.filter(x => districtRisk(x) === 'medium').length}개 구`;
    document.getElementById('realtime-total-beds').textContent =
        knownHospitals.length ? `${fmt(totalBeds)} 석` : '조회 데이터 없음';

    updateHeroStats(knownHospitals.length > 0, totalBeds);
}

// 상단 Hero 카드 숫자 갱신 (데이터가 없으면 '–' 표시)
function updateHeroStats(hasData, totalBeds) {
    const bedsEl = document.getElementById('hero-total-beds');
    if (bedsEl) bedsEl.textContent = hasData ? fmt(totalBeds) : '–';
}

let realtimeLoadedAt = 0;
async function loadRealtime(force=false) {
    // 5분 안에 다시 열면 이미 받은 값 사용
    if (!force && window.REALTIME_RESULTS && Date.now() - realtimeLoadedAt < 5 * 60 * 1000) {
        filterRealtime();
        return;
    }
    const grid = document.getElementById('realtime-card-grid');
    grid.innerHTML = '<div class="col-span-full text-center py-10 text-slate-500 font-bold">실시간 병상 정보를 불러오는 중...</div>';

    const {results, updatedAt} = await fetchRealtimeAll();
    window.REALTIME_RESULTS = results;
    realtimeLoadedAt = Date.now();
    // 푸터 안내 문구: 한 줄에 하나씩 표시
    const footerLines = updatedAt
        ? [
            `병상 정보 기준 시각: ${updatedAt.replace('T', ' ')}`,
            '출처: 국립중앙의료원 실시간 병상 API',
            '강북·마포는 등록 응급실 병상 별도 표시',
        ]
        : ['병상 정보를 준비 중입니다. 잠시 후 다시 열어 주세요.'];
    document.getElementById('realtime-updated-at').innerHTML =
        footerLines.map(line => `<div>${esc(line)}</div>`).join('');
    updateRealtimeSummary(results);
    filterRealtime();
}

function hospitalRow(h, showDistrict) {
    const b = Number(h.Available_Beds);
    const hRisk = hospitalRisk(h);
    const bedClass =
        hRisk === 'high' ? 'text-red-600' :
        hRisk === 'medium' ? 'text-amber-600' :
        hRisk === 'low' ? 'text-emerald-700' : 'text-slate-500';
    const bedText = hRisk !== 'unknown' ? `${fmt(Math.max(0, b))} 석` : '확인불가';
    const tag = showDistrict && h.From_District
        ? `<span class="text-[11px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-200 rounded px-1.5 py-0.5 mr-1">${esc(h.From_District)}</span>` : '';
    const tel = h.Tel ? `<div class="text-xs text-slate-500 mt-1">☎ ${esc(h.Tel)}</div>` : '';
    const staleTag = h.Is_Stale ? ' · 24시간 이상 미갱신' : '';

    return `<div class="bg-slate-50 p-3 rounded-xl border border-slate-200">
        <div class="flex justify-between items-start gap-3">
            <div class="min-w-0 flex-1">
                <b class="block text-[17px] text-slate-900 leading-6 truncate" title="${esc(cleanHospitalName(h.Hospital_Name || h.Hospital_ID || '병원'))}">${tag}${esc(cleanHospitalName(h.Hospital_Name || h.Hospital_ID || '병원'))}</b>
                ${tel}
            </div>
            <div class="text-right shrink-0">
                <b class="text-sm ${bedClass} whitespace-nowrap">${bedText}</b>
                <div class="text-[11px] text-slate-500 mt-1">갱신: ${formatApiDate(h.Updated_At)}${staleTag}</div>
            </div>
        </div>
    </div>`;
}

function staticErHospitalRow(h) {
    const beds = Number(h.ER_Beds);
    const bedText = Number.isFinite(beds) ? `${fmt(beds)} 석` : '확인불가';
    return `<div class="bg-indigo-50/60 p-3 rounded-xl border border-indigo-200">
        <div class="flex justify-between items-start gap-3">
            <div class="min-w-0 flex-1">
                <b class="block text-[17px] text-slate-900 leading-6 truncate" title="${esc(cleanHospitalName(h.Hospital_Name || '병원'))}">${esc(cleanHospitalName(h.Hospital_Name || '병원'))}</b>
            </div>
            <div class="text-right shrink-0">
                <b class="text-xs text-indigo-700 whitespace-nowrap">응급실 병상 ${bedText}</b>
                <div class="text-xs text-slate-500 mt-1 whitespace-nowrap">실시간 가용병상: 확인 불가 · API 미제공</div>
            </div>
        </div>
    </div>`;
}

function closeNearbyMenus(exceptId = null) {
    document.querySelectorAll('.nearby-submenu').forEach(menu => {
        if (menu.id === exceptId) return;
        menu.classList.add('hidden');
        const btn = document.querySelector(`[aria-controls="${menu.id}"]`);
        if (btn) {
            btn.setAttribute('aria-expanded', 'false');
            btn.querySelector('.nearby-chevron')?.classList.remove('rotate-180');
        }
    });
}

function toggleNearbyMenu(menuId, event) {
    event?.stopPropagation();
    const menu = document.getElementById(menuId);
    if (!menu) return;
    const button = document.querySelector(`[aria-controls="${menuId}"]`);
    const willOpen = menu.classList.contains('hidden');
    closeNearbyMenus(willOpen ? menuId : null);
    menu.classList.toggle('hidden', !willOpen);
    if (button) {
        button.setAttribute('aria-expanded', String(willOpen));
        button.querySelector('.nearby-chevron')?.classList.toggle('rotate-180', willOpen);
    }
}

document.addEventListener('click', (event) => {
    if (!event.target.closest('.nearby-menu-wrap')) closeNearbyMenus();
});

function filterRealtime() {
    const q = document.getElementById('realtime-search-input').value.toLowerCase().trim();
    const zone = document.getElementById('realtime-zone-filter').value;
    const risk = document.getElementById('realtime-risk-filter').value;
    updateRiskCardState(risk);

    const results = (window.REALTIME_RESULTS || []).filter(x => {
        const zoneMatch = zone === 'all' || districtZones[x.district] === zone;
        const searchMatch =
            x.district.toLowerCase().includes(q) ||
            (x.hospitals || []).some(h => (h.Hospital_Name || '').toLowerCase().includes(q));
        // 'none' 선택 시: 실시간 정보 미제공(강북·마포) + 병상 정보 없음 구를 함께 표시
        const dRisk = districtRisk(x);
        const riskMatch = risk === 'all' || dRisk === risk ||
            (risk === 'none' && (dRisk === 'static' || dRisk === 'unknown'));
        return zoneMatch && searchMatch && riskMatch;
    });

    const cards = results.map(x => {
        const hs = [...(x.hospitals || [])].sort((a, b) => {
            const av = x.data_type === 'static_er_beds' ? Number(a.ER_Beds ?? -1) : Number(a.Available_Beds ?? -1);
            const bv = x.data_type === 'static_er_beds' ? Number(b.ER_Beds ?? -1) : Number(b.Available_Beds ?? -1);
            return bv - av;
        });
        const nearby = [...(x.nearby_hospitals || [])].sort((a, b) => Number(b.Available_Beds ?? -1) - Number(a.Available_Beds ?? -1));
        const dRisk = districtRisk(x);
        const badge =
            dRisk === 'high' ? '<span class="med-badge badge-coral">🚨 포화</span>' :
            dRisk === 'medium' ? '<span class="med-badge badge-amber">⚠️ 주의</span>' :
            dRisk === 'low' ? '<span class="med-badge badge-emerald">✅ 원활</span>' :
            dRisk === 'static' ? '<span class="med-badge bg-indigo-50 text-indigo-700 border border-indigo-200">ℹ️ 실시간 정보 미제공</span>' :
            '<span class="med-badge bg-slate-100 text-slate-500 border border-slate-200">정보 없음</span>';

        let body = '';
        if (x.error) {
            body += `<div class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-xl p-3">${esc(x.error)}</div>`;
        }
        if (x.data_type === 'static_er_beds') {
            body += `<div class="text-xs text-indigo-800 bg-indigo-50 border border-indigo-200 rounded-xl p-3 font-bold">${esc(x.notice || '실시간 가용병상 정보가 제공되지 않습니다.')}</div>`;
            body += `<div class="space-y-2 h-[216px] overflow-y-auto pr-1">${hs.map(staticErHospitalRow).join('')}</div>`;
            if (nearby.length) {
                const menuId = `nearby-menu-${x.district}`;
                body += `<div class="relative pt-1 nearby-menu-wrap">
                    <button type="button"
                        onclick="toggleNearbyMenu('${menuId}', event)"
                        class="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-bold text-slate-700 transition-colors"
                        aria-expanded="false" aria-controls="${menuId}">
                        <span><i class="fa-solid fa-hospital-user mr-1.5 text-emerald-600"></i>${esc(x.nearby_notice || '인접 자치구 실시간 가용병상')}</span>
                        <span class="nearby-chevron text-slate-400 transition-transform"><i class="fa-solid fa-chevron-down"></i></span>
                    </button>
                    <div id="${menuId}" class="nearby-submenu hidden absolute left-0 right-0 top-full mt-2 z-50 bg-white border border-slate-200 rounded-2xl shadow-xl p-3 space-y-2 max-h-[250px] overflow-y-auto">
                        <div class="flex items-center justify-between px-1 pb-1">
                            <span class="text-[11px] font-black text-slate-700">인접 자치구 실시간 병상</span>
                            <span class="text-[10px] text-slate-400">클릭하여 닫기</span>
                        </div>
                        ${nearby.map(h => hospitalRow(h, true)).join('')}
                    </div>
                </div>`;
            }
        } else if (hs.length) {
            body += `<div class="space-y-2 h-[288px] overflow-y-auto pr-1">${hs.map(h => hospitalRow(h, false)).join('')}</div>`;
        } else if (nearby.length) {
            body += `<div class="text-xs text-indigo-800 bg-indigo-50 border border-indigo-200 rounded-xl p-3 font-bold">${esc(x.notice || '인접 자치구 병원을 안내합니다.')}</div>`;
            body += nearby.map(h => hospitalRow(h, true)).join('');
        } else if (!x.error) {
            body += `<div class="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-xl p-4 text-center">현재 조회된 응급실 병상 정보가 없습니다.</div>`;
        }

        const cardHeightClass = 'h-[430px]';
        return `<div class="medical-card p-5 space-y-3 ${cardHeightClass} overflow-visible ${dRisk === 'high' ? 'emergency-card-high' : ''}">
            <div class="flex justify-between items-center gap-3">
                <h3 class="font-black">${esc(x.district)}
                    <span class="text-xs text-slate-500">(${districtZones[x.district] || ''})</span>
                </h3>
                ${badge}
            </div>
            ${body}
        </div>`;
    });

    document.getElementById('realtime-card-grid').innerHTML =
        cards.join('') ||
        '<div class="col-span-full text-center py-12 text-slate-400 font-bold">현재 필터 조건과 일치하는 실시간 병상 데이터가 없습니다.</div>';
}

window.addEventListener('load', () => loadRealtime());
