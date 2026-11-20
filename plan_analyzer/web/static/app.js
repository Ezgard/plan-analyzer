/**
 * Клиентский скрипт интерфейса анализа учебных планов и дисциплин.
 * Единица анализа: Дисциплина (с привязкой к Отрасли и Преподавателям).
 */

let allDisciplinesData = [];
let allConflictsData = [];
let allControlConflictsData = [];
let allSemesterAuditsData = [];
let activeControlSubTab = 'conflicts';
let allDepartmentsData = [];
let allTeachersData = [];
let allIndustriesData = [];
let loadedPlansList = [];
let stagedChangesCount = 0;

let currentSelectedDiscipline = null;
let currentUnifyPair = null;

// --- Инициализация при загрузке страницы ---
document.addEventListener('DOMContentLoaded', () => {
    initDragAndDrop();
    initFileInput();
    refreshAllData();
});

// --- Управление вкладками ---
function switchTab(tabId) {
    const tabs = ['upload', 'disciplines', 'conflicts', 'controls', 'similarity', 'staged'];
    tabs.forEach(t => {
        const view = document.getElementById(`view-${t}`);
        const btn = document.getElementById(`tab-${t}`);
        if (view && btn) {
            if (t === tabId) {
                view.classList.remove('hidden');
                view.classList.add('block', 'fade-in');
                btn.classList.add('border-sky-600', 'text-sky-600');
                btn.classList.remove('border-transparent', 'text-slate-500');
            } else {
                view.classList.add('hidden');
                view.classList.remove('block', 'fade-in');
                btn.classList.remove('border-sky-600', 'text-sky-600');
                btn.classList.add('border-transparent', 'text-slate-500');
            }
        }
    });

    if (tabId === 'disciplines') loadDisciplines();
    if (tabId === 'conflicts') loadConflicts();
    if (tabId === 'controls') loadControlData();
    if (tabId === 'similarity') reloadSimilarities();
    if (tabId === 'staged') loadStaged();
}

// --- Индикатор загрузки ---
function showLoading(text = 'Выполняется обработка...') {
    const overlay = document.getElementById('loading-overlay');
    const label = document.getElementById('loading-text');
    if (overlay && label) {
        label.innerText = text;
        overlay.classList.remove('hidden');
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('hidden');
}

// --- Drag and Drop & Загрузка файлов планов ---
function initDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');
    if (!dropZone) return;

    ['dragenter', 'dragover'].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            dropZone.classList.add('border-sky-500', 'bg-sky-50/50');
        });
    });

    ['dragleave', 'drop'].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            dropZone.classList.remove('border-sky-500', 'bg-sky-50/50');
        });
    });

    dropZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            uploadFiles(files);
        }
    });
}

function initFileInput() {
    const input = document.getElementById('file-input');
    if (!input) return;
    input.addEventListener('change', () => {
        if (input.files && input.files.length > 0) {
            uploadFiles(input.files);
        }
    });
}

async function uploadFiles(files) {
    showLoading(`Загрузка и парсинг ${files.length} файлов планов...`);
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    try {
        const res = await fetch('/api/upload-files?append=true', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (data.success) {
            await refreshAllData();
            const fileInput = document.getElementById('file-input');
            if (fileInput) fileInput.value = '';
        } else {
            alert('Ошибка загрузки: ' + (data.detail || 'Не удалось обработать файлы'));
        }
    } catch (err) {
        alert('Ошибка при отправке файлов: ' + err.message);
    } finally {
        hideLoading();
    }
}

async function loadFromDirectory() {
    const input = document.getElementById('dir-input');
    const dirPath = input ? input.value.trim() : '';
    if (!dirPath) {
        alert('Пожалуйста, укажите путь к директории с планами.');
        return;
    }

    showLoading('Сканирование каталога и парсинг учебных планов...');
    try {
        const res = await fetch('/api/load-directory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ directory_path: dirPath, append: true }),
        });
        const data = await res.json();
        if (res.ok && data.success) {
            await refreshAllData();
        } else {
            alert('Ошибка: ' + (data.detail || 'Не удалось просканировать директорию'));
        }
    } catch (err) {
        alert('Ошибка при вызове сервера: ' + err.message);
    } finally {
        hideLoading();
    }
}

async function loadDemoPlans() {
    showLoading('Загрузка демонстрационных планов (ПИ и ПМИ)...');
    try {
        const res = await fetch('/api/load-demo-plans', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            await refreshAllData();
            await loadDisciplines();
        } else {
            alert('Не удалось загрузить демонстрационные планы.');
        }
    } catch (err) {
        alert('Ошибка при загрузке демонстрационных планов: ' + err.message);
    } finally {
        hideLoading();
    }
}

async function clearAllPlans() {
    if (!confirm('Вы уверены, что хотите удалить все загруженные планы из текущей сессии?')) return;
    showLoading('Очистка всех планов...');
    try {
        await fetch('/api/clear-plans', { method: 'POST' });
        await refreshAllData();
    } catch (err) {
        alert('Ошибка очистки: ' + err.message);
    } finally {
        hideLoading();
    }
}

async function deletePlanByIndex(idx) {
    const plan = loadedPlansList[idx];
    if (!plan) return;
    if (!confirm(`Исключить план из анализа?\n${plan.file_name} (${plan.direction_code})`)) return;

    showLoading('Удаление плана...');
    try {
        const res = await fetch('/api/delete-plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: plan.file_path }),
        });
        const data = await res.json();
        if (data.success) {
            await refreshAllData();
        } else {
            alert('Не удалось удалить план: файл не найден в активном списке.');
        }
    } catch (err) {
        alert('Ошибка удаления плана: ' + err.message);
    } finally {
        hideLoading();
    }
}

// --- Загрузка и обновление данных ---
async function refreshAllData() {
    await loadStatus();
    await loadPlans();
    await loadDepartments();
    await loadTeachers();
    await loadIndustries();
    await loadFilterOptions();

    // Если открыта вкладка дисциплин, коллизий или контроля, обновляем их тоже
    const discView = document.getElementById('view-disciplines');
    if (discView && !discView.classList.contains('hidden')) {
        await loadDisciplines();
    }
    const conflictsView = document.getElementById('view-conflicts');
    if (conflictsView && !conflictsView.classList.contains('hidden')) {
        await loadConflicts();
    }
    const controlsView = document.getElementById('view-controls');
    if (controlsView && !controlsView.classList.contains('hidden')) {
        await loadControlData();
    }
    const stagedView = document.getElementById('view-staged');
    if (stagedView && !stagedView.classList.contains('hidden')) {
        await loadStaged();
    }
}

async function loadStatus() {
    try {
        const res = await fetch('/api/status');
        const st = await res.json();
        document.getElementById('stat-staged').innerText = st.staged_count;
        stagedChangesCount = st.staged_count;

        const plansBadge = document.getElementById('tab-plans-badge');
        if (plansBadge) plansBadge.innerText = st.plans_count;

        const discBadge = document.getElementById('tab-disciplines-badge');
        if (discBadge) discBadge.innerText = st.disciplines_count;

        const conflictBadge = document.getElementById('tab-conflict-badge');
        if (conflictBadge) {
            conflictBadge.innerText = st.conflicts_count;
            conflictBadge.classList.toggle('hidden', st.conflicts_count === 0);
        }

        const controlsBadge = document.getElementById('tab-controls-badge');
        const totalControlIssues = (st.control_conflicts_count || 0) + (st.overloaded_semesters_count || 0);
        if (controlsBadge) {
            controlsBadge.innerText = totalControlIssues;
            controlsBadge.classList.toggle('hidden', totalControlIssues === 0);
        }

        const subCtrlConflictsCount = document.getElementById('ctrl-conflicts-count');
        if (subCtrlConflictsCount) subCtrlConflictsCount.innerText = st.control_conflicts_count || 0;

        const subCtrlOverloadCount = document.getElementById('ctrl-overloaded-count');
        if (subCtrlOverloadCount) subCtrlOverloadCount.innerText = st.overloaded_semesters_count || 0;

        const stagedBadge = document.getElementById('tab-staged-badge');
        if (stagedBadge) {
            stagedBadge.innerText = st.staged_count;
            stagedBadge.classList.toggle('hidden', st.staged_count === 0);
        }
    } catch (e) {
        console.error('Ошибка получения статуса:', e);
    }
}

async function loadPlans() {
    try {
        const res = await fetch('/api/plans');
        const plans = await res.json();
        loadedPlansList = plans || [];
        const tbody = document.getElementById('plans-tbody');
        document.getElementById('plans-table-count').innerText = loadedPlansList.length;

        if (!loadedPlansList || loadedPlansList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-slate-400">Планы еще не загружены. Перетащите файлы или укажите папку.</td></tr>`;
            return;
        }

        tbody.innerHTML = loadedPlansList.map((p, idx) => `
            <tr class="hover:bg-slate-50 transition">
                <td class="px-4 py-3 font-medium text-slate-900 truncate max-w-xs" title="${p.file_path}">${escapeHtml(p.file_name)}</td>
                <td class="px-4 py-3"><span class="font-semibold">${escapeHtml(p.direction_code)}</span> ${escapeHtml(p.direction_title || '—')}</td>
                <td class="px-4 py-3 text-slate-600 truncate max-w-xs" title="${p.profile_title}">${escapeHtml(p.profile_title || 'Общий')}</td>
                <td class="px-4 py-3"><span class="inline-block px-2 py-0.5 rounded bg-slate-100 text-slate-700">${escapeHtml(p.edu_level || '—')} / ${escapeHtml(p.study_form || '—')}</span></td>
                <td class="px-4 py-3">${escapeHtml(p.start_year || '—')}</td>
                <td class="px-4 py-3 text-right font-bold text-sky-700">${p.total_disciplines}</td>
                <td class="px-4 py-3 text-center">
                    <button onclick="deletePlanByIndex(${idx})" class="text-slate-400 hover:text-rose-600 p-1.5 rounded hover:bg-rose-50 border border-transparent hover:border-rose-200 transition" title="Удалить план из анализа">
                        <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Ошибка загрузки планов:', e);
    }
}

async function loadDepartments() {
    try {
        const res = await fetch('/api/departments');
        allDepartmentsData = await res.json();

        const filterSelect = document.getElementById('disc-dept-filter');
        if (filterSelect) {
            const currentVal = filterSelect.value;
            filterSelect.innerHTML = `<option value="">Все кафедры (${allDepartmentsData.length})</option>` +
                allDepartmentsData.map(d => `<option value="${d.dept_name}">${d.dept_name} (${d.disciplines_count} дисц.)</option>`).join('');
            filterSelect.value = currentVal;
        }
    } catch (e) {
        console.error('Ошибка загрузки кафедр:', e);
    }
}

async function loadTeachers() {
    try {
        const res = await fetch('/api/teachers');
        allTeachersData = await res.json();

        // Заполняем фильтр в каталоге дисциплин
        const select = document.getElementById('disc-teacher-filter');
        if (select) {
            const curVal = select.value;
            select.innerHTML = `<option value="">Все преподаватели (${allTeachersData.length})</option>` +
                allTeachersData.map(t => `<option value="${t.id}">${t.name} ${t.department ? `(${t.department})` : ''}</option>`).join('');
            select.value = curVal;
        }
    } catch (e) {
        console.error('Ошибка загрузки преподавателей:', e);
    }
}

async function loadIndustries() {
    try {
        const res = await fetch('/api/industries');
        allIndustriesData = await res.json();

        const select = document.getElementById('disc-industry-filter');
        if (select) {
            const curVal = select.value;
            select.innerHTML = `<option value="">Все отрасли (${allIndustriesData.length})</option>` +
                allIndustriesData.map(i => `<option value="${i.name}">${i.name}</option>`).join('');
            select.value = curVal;
        }
    } catch (e) {
        console.error('Ошибка загрузки отраслей:', e);
    }
}

async function loadFilterOptions() {
    try {
        const res = await fetch('/api/filter-options');
        const data = await res.json();
        const years = data.years || [];
        const academicYears = data.academic_years || [];

        // Годы набора в каталоге дисциплин
        const discYearSelect = document.getElementById('disc-year-filter');
        if (discYearSelect) {
            const curVal = discYearSelect.value;
            discYearSelect.innerHTML = `<option value="">Все годы набора</option>` +
                years.map(y => `<option value="${y}">${y} год набора</option>`).join('');
            discYearSelect.value = curVal;
        }

        // Учебные годы в каталоге дисциплин
        const discAySelect = document.getElementById('disc-academic-year-filter');
        if (discAySelect) {
            const curVal = discAySelect.value;
            discAySelect.innerHTML = `<option value="">Все учебные годы</option>` +
                academicYears.map(ay => `<option value="${ay}">${ay} уч. год</option>`).join('');
            discAySelect.value = curVal;
        }

        // Годы набора в коллизиях
        const conflictsYearSelect = document.getElementById('conflicts-year-filter');
        if (conflictsYearSelect) {
            const curVal = conflictsYearSelect.value;
            conflictsYearSelect.innerHTML = `<option value="">Все годы набора</option>` +
                years.map(y => `<option value="${y}">${y} год набора</option>`).join('');
            conflictsYearSelect.value = curVal;
        }

        // Учебные годы в коллизиях
        const conflictsAySelect = document.getElementById('conflicts-academic-year-filter');
        if (conflictsAySelect) {
            const curVal = conflictsAySelect.value;
            conflictsAySelect.innerHTML = `<option value="">Все учебные годы</option>` +
                academicYears.map(ay => `<option value="${ay}">${ay} уч. год</option>`).join('');
            conflictsAySelect.value = curVal;
        }

        // Годы набора во вкладке форм контроля
        const ctrlYearSelect = document.getElementById('controls-year-filter');
        if (ctrlYearSelect) {
            const curVal = ctrlYearSelect.value;
            ctrlYearSelect.innerHTML = `<option value="">Все годы набора</option>` +
                years.map(y => `<option value="${y}">${y} год набора</option>`).join('');
            ctrlYearSelect.value = curVal;
        }

        // Учебные годы во вкладке форм контроля
        const ctrlAySelect = document.getElementById('controls-academic-year-filter');
        if (ctrlAySelect) {
            const curVal = ctrlAySelect.value;
            ctrlAySelect.innerHTML = `<option value="">Все учебные годы</option>` +
                academicYears.map(ay => `<option value="${ay}">${ay} уч. год</option>`).join('');
            ctrlAySelect.value = curVal;
        }
    } catch (e) {
        console.error('Ошибка загрузки опций фильтрации:', e);
    }
}

// --- Вкладка 2: Каталог дисциплин (Единица анализа) ---
async function loadDisciplines() {
    const search = document.getElementById('disc-search')?.value || '';
    const industry = document.getElementById('disc-industry-filter')?.value || '';
    const teacher = document.getElementById('disc-teacher-filter')?.value || '';
    const dept = document.getElementById('disc-dept-filter')?.value || '';
    const year = document.getElementById('disc-year-filter')?.value || '';
    const academicYear = document.getElementById('disc-academic-year-filter')?.value || '';
    const conflictOnly = document.getElementById('disc-conflict-only')?.checked || false;

    const params = new URLSearchParams();
    if (search.trim()) params.append('search', search.trim());
    if (industry.trim()) params.append('industry', industry.trim());
    if (teacher.trim()) params.append('teacher', teacher.trim());
    if (dept.trim()) params.append('dept', dept.trim());
    if (year.trim()) params.append('year', year.trim());
    if (academicYear.trim()) params.append('academic_year', academicYear.trim());
    if (conflictOnly) params.append('conflict_only', 'true');

    try {
        const res = await fetch(`/api/disciplines?${params.toString()}`);
        if (!res.ok) {
            console.error('Ошибка сервера при загрузке дисциплин:', res.status);
            allDisciplinesData = [];
            renderDisciplinesList([]);
            return;
        }
        allDisciplinesData = await res.json();
        renderDisciplinesList(allDisciplinesData);
    } catch (e) {
        console.error('Ошибка загрузки каталога дисциплин:', e);
        allDisciplinesData = [];
        renderDisciplinesList([]);
    }
}

function filterDisciplines() {
    loadDisciplines();
}

function resetDisciplineFilters() {
    const ids = ['disc-search', 'disc-industry-filter', 'disc-teacher-filter', 'disc-dept-filter', 'disc-year-filter', 'disc-academic-year-filter'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const chk = document.getElementById('disc-conflict-only');
    if (chk) chk.checked = false;
    loadDisciplines();
}

function renderDisciplinesList(disciplines) {
    const container = document.getElementById('disciplines-list');
    const list = Array.isArray(disciplines) ? disciplines : [];
    const countLabel = document.getElementById('disc-count-label');
    if (countLabel) countLabel.innerText = list.length;

    if (!container) return;

    if (list.length === 0) {
        if (!loadedPlansList || loadedPlansList.length === 0) {
            container.innerHTML = `
                <div class="bg-white rounded-xl border-2 border-dashed border-sky-300 p-8 text-center space-y-4">
                    <div class="w-12 h-12 bg-sky-100 text-sky-700 rounded-full flex items-center justify-center mx-auto">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
                    </div>
                    <div>
                        <h3 class="text-base font-bold text-slate-800">Учебные планы еще не загружены</h3>
                        <p class="text-xs text-slate-500 max-w-md mx-auto mt-1">
                            Каталог уникальных дисциплин формируется на основе загруженных шахтинских планов (.plx, .xml).
                            Загрузите демонстрационные планы прямо сейчас или добавьте свои файлы.
                        </p>
                    </div>
                    <div class="flex flex-wrap justify-center gap-3 pt-2">
                        <button onclick="loadDemoPlans()" class="px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-sm transition flex items-center space-x-1.5">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                            <span>Загрузить демонстрационные планы</span>
                        </button>
                        <button onclick="switchTab('upload')" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold border border-slate-300 transition">
                            Загрузить свои планы (.plx / .xml)
                        </button>
                        <button onclick="openRegistryModal()" class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold border border-slate-300 transition">
                            Справочники преподавателей и отраслей
                        </button>
                    </div>
                </div>
            `;
        } else {
            container.innerHTML = `
                <div class="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-3">
                    <p class="text-slate-500 text-xs">По выбранным фильтрам дисциплины не найдены.</p>
                    <button onclick="resetDisciplineFilters()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded text-xs transition">
                        Сбросить все фильтры
                    </button>
                </div>
            `;
        }
        return;
    }

    container.innerHTML = disciplines.map((d, idx) => {
        const semsStr = d.semesters && d.semesters.length ? d.semesters.join(', ') : '—';
        const ayStr = d.academic_years && d.academic_years.length ? d.academic_years.join(', ') : '—';
        return `
            <div class="bg-white rounded-xl border ${d.has_conflict ? 'border-rose-300 shadow-rose-50' : 'border-slate-200'} p-4 shadow-sm hover:shadow transition space-y-3">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                    <div class="flex flex-wrap items-center gap-2">
                        <h4 class="text-base font-bold text-slate-900">${escapeHtml(d.title)}</h4>
                        ${d.has_conflict ? `
                            <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                                ⚠ Коллизия кафедр (${d.departments.length})
                            </span>
                        ` : ''}
                        ${d.has_control_conflict ? `
                            <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200" title="${escapeHtml(d.control_conflict_details || '')}">
                                ⚠ Коллизия контроля (${(d.exam_types || []).join(' vs ')})
                            </span>
                        ` : (d.exam_types && d.exam_types.length ? `
                            <span class="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
                                Форма: ${escapeHtml(d.exam_types.join(', '))}
                            </span>
                        ` : '')}
                        <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                            В ${d.plans_count} планах
                        </span>
                    </div>

                    <div class="flex items-center space-x-2">
                        <button onclick="openDisciplineBindModal('${escapeJs(d.title)}')" class="px-3 py-1.5 bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-200 rounded-lg font-semibold text-xs transition flex items-center space-x-1">
                            <svg class="w-3.5 h-3.5 text-sky-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                            <span>Настроить отрасль / преподавателей</span>
                        </button>
                    </div>
                </div>

                <!-- Строка атрибутов: Отрасль, Преподаватели, Кафедры -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                    <!-- Отрасль -->
                    <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-200 flex flex-col justify-between">
                        <div class="text-[11px] text-slate-400 font-semibold uppercase tracking-wider mb-1">Отрасль знаний</div>
                        <div>
                            ${d.industry ? `
                                <span class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                    ${escapeHtml(d.industry)}
                                </span>
                            ` : `
                                <span class="text-slate-400 italic cursor-pointer hover:text-sky-600" onclick="openDisciplineBindModal('${escapeJs(d.title)}')">
                                    + Не указана (нажмите для выбора)
                                </span>
                            `}
                        </div>
                    </div>

                    <!-- Преподаватели -->
                    <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-200 flex flex-col justify-between">
                        <div class="text-[11px] text-slate-400 font-semibold uppercase tracking-wider mb-1">Преподаватели (${d.teachers ? d.teachers.length : 0})</div>
                        <div class="flex flex-wrap gap-1.5">
                            ${d.teachers && d.teachers.length ? d.teachers.map(t => `
                                <span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-sky-100 text-sky-800 border border-sky-200" title="${escapeHtml(t.department || '')}">
                                    ${escapeHtml(t.name)}
                                </span>
                            `).join('') : `
                                <span class="text-slate-400 italic cursor-pointer hover:text-sky-600" onclick="openDisciplineBindModal('${escapeJs(d.title)}')">
                                    + Не назначены (нажмите для добавления)
                                </span>
                            `}
                        </div>
                    </div>

                    <!-- Закрепленные кафедры -->
                    <div class="bg-slate-50 p-2.5 rounded-lg border border-slate-200 flex flex-col justify-between">
                        <div class="text-[11px] text-slate-400 font-semibold uppercase tracking-wider mb-1">Кафедры</div>
                        <div class="space-y-1">
                            ${d.departments.map(dept => `
                                <div class="font-medium text-slate-800 truncate" title="${escapeHtml(dept)}">
                                    • ${escapeHtml(dept)}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <!-- Подвал карточки: нагрузка и вхождения -->
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center text-xs text-slate-500 pt-1 border-t border-slate-100 gap-2">
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
                        <span>Учебные годы: <b class="text-sky-700 font-semibold">${ayStr}</b></span>
                        <span>Семестры: <b class="text-slate-700">${semsStr}</b></span>
                        <span>Трудоемкость: <b class="text-slate-900 font-bold">${d.ze_display || d.total_ze} ЗЕТ</b> <span class="text-slate-500">(${d.hours_display || d.total_hours} ч.)</span></span>
                        ${d.plans_count > 1 ? `<span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-[11px]" title="Суммарная нагрузка по всем ${d.plans_count} планам">Суммарно по ${d.plans_count} пл.: <b>${d.sum_ze} ЗЕТ</b> (${d.sum_hours} ч.)</span>` : ''}
                    </div>
                    <button onclick="toggleDisciplinePlans(${idx})" class="text-sky-600 hover:text-sky-800 font-semibold">
                        Вхождения в планы (${d.occurrences.length}) ↓
                    </button>
                </div>

                <!-- Выпадающий список вхождений -->
                <div id="disc-plans-${idx}" class="hidden bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
                    <div class="font-semibold text-slate-700 mb-2">Перечень планов, в которых читается дисциплина:</div>
                    <ul class="space-y-1.5 divide-y divide-slate-200 text-slate-600">
                        ${d.occurrences.map(o => `
                            <li class="pt-1.5 flex justify-between items-center">
                                <div>
                                    <span class="font-semibold text-slate-800">${escapeHtml(o.direction_code)} ${escapeHtml(o.direction_title || '')}</span>
                                    ${o.profile_title ? `<span class="text-slate-500">(${escapeHtml(o.profile_title)})</span>` : ''}
                                    <div class="text-[11px] text-slate-500 mt-0.5">
                                        ${escapeHtml(o.plan_name)} • <span class="px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 font-semibold">${escapeHtml(o.academic_year || '—')} уч. год</span> • Сем: ${o.semester} • Набор: ${escapeHtml(o.start_year || '—')} • <span class="font-medium text-slate-700">ЗЕТ: ${o.total_ze}</span> <span class="text-slate-400">(${o.total_hours} ч.)</span>
                                        ${o.exam_type ? `• <span class="px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-semibold">${escapeHtml(o.exam_type)}</span>` : ''}
                                    </div>
                                </div>
                                <div class="text-right font-medium text-slate-700">
                                    ${escapeHtml(o.dept_name)} ${o.dept_code ? `<span class="text-slate-400">(№${escapeHtml(o.dept_code)})</span>` : ''}
                                </div>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            </div>
        `;
    }).join('');
}

function toggleDisciplinePlans(idx) {
    const el = document.getElementById(`disc-plans-${idx}`);
    if (el) el.classList.toggle('hidden');
}

// --- Модальное окно настройки дисциплины (Отрасль / Преподаватели) ---
function openDisciplineBindModal(title) {
    currentSelectedDiscipline = title;
    document.getElementById('modal-bind-disc-title').innerText = title;

    // Находим текущий профиль дисциплины
    const disc = allDisciplinesData.find(d => d.title === title);
    const curIndustry = disc ? disc.industry : '';
    const curTeacherIds = disc && disc.teachers ? disc.teachers.map(t => t.id) : [];

    // Заполняем селект отраслей
    const indSelect = document.getElementById('modal-bind-industry');
    indSelect.innerHTML = `<option value="">-- Не указана --</option>` +
        allIndustriesData.map(i => `<option value="${i.name}" ${i.name === curIndustry ? 'selected' : ''}>${escapeHtml(i.name)}</option>`).join('');

    // Заполняем чекбоксы преподавателей
    const tContainer = document.getElementById('modal-bind-teachers-list');
    if (!allTeachersData || allTeachersData.length === 0) {
        tContainer.innerHTML = `<div class="text-slate-400 p-2 italic">Преподаватели еще не добавлены в справочник. Откройте «Справочники» в шапке.</div>`;
    } else {
        tContainer.innerHTML = allTeachersData.map(t => {
            const isChecked = curTeacherIds.includes(t.id);
            return `
                <label class="flex items-center space-x-2 p-1.5 rounded hover:bg-white cursor-pointer transition border border-transparent hover:border-slate-200">
                    <input type="checkbox" name="bind-teacher" value="${t.id}" ${isChecked ? 'checked' : ''} class="rounded border-slate-300 text-sky-600 focus:ring-sky-500">
                    <span class="font-medium text-slate-800">${escapeHtml(t.name)}</span>
                    ${t.department ? `<span class="text-slate-400 text-[11px]">(${escapeHtml(t.department)})</span>` : ''}
                </label>
            `;
        }).join('');
    }

    const modal = document.getElementById('modal-discipline-bind');
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
    }
}

async function saveDisciplineBinding() {
    if (!currentSelectedDiscipline) return;
    const industry = document.getElementById('modal-bind-industry').value;
    const checkedBoxes = document.querySelectorAll('input[name="bind-teacher"]:checked');
    const teacherIds = Array.from(checkedBoxes).map(cb => cb.value);

    showLoading('Сохранение привязки дисциплины...');
    try {
        const res = await fetch('/api/disciplines/bind', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                discipline_title: currentSelectedDiscipline,
                industry: industry || null,
                teacher_ids: teacherIds,
            }),
        });
        const data = await res.json();
        if (data.success) {
            closeModal('modal-discipline-bind');
            await loadDisciplines();
        }
    } catch (e) {
        alert('Ошибка при сохранении: ' + e.message);
    } finally {
        hideLoading();
    }
}

// --- Модальное окно управления справочниками ---
function openRegistryModal(tab = 'teachers') {
    const modal = document.getElementById('modal-registry');
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
    }
    switchRegistryTab(tab);
    // Подгружаем актуальные данные с сервера
    loadTeachers().then(() => renderTeachersTable()).catch(console.error);
    loadIndustries().then(() => renderIndustriesTable()).catch(console.error);
}

function switchRegistryTab(tab) {
    if (tab === 'import-bindings') tab = 'bindings';
    ['teachers', 'industries', 'bindings'].forEach(t => {
        const view = document.getElementById(`reg-view-${t}`);
        const btn = document.getElementById(`reg-tab-${t}`);
        if (view) {
            if (t === tab) {
                view.classList.remove('hidden');
                view.style.display = 'block';
            } else {
                view.classList.add('hidden');
                view.style.display = 'none';
            }
        }
        if (btn) {
            if (t === tab) {
                btn.classList.add('border-sky-600', 'text-sky-700');
                btn.classList.remove('border-transparent', 'text-slate-500');
            } else {
                btn.classList.remove('border-sky-600', 'text-sky-700');
                btn.classList.add('border-transparent', 'text-slate-500');
            }
        }
    });

    if (tab === 'teachers') renderTeachersTable();
    if (tab === 'industries') renderIndustriesTable();
}

function renderTeachersTable() {
    const tbody = document.getElementById('teachers-tbody');
    const countEl = document.getElementById('teachers-count');
    const teachers = Array.isArray(allTeachersData) ? allTeachersData : [];
    if (countEl) countEl.innerText = teachers.length;

    if (!tbody) return;

    if (teachers.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="px-3 py-4 text-center text-slate-400">Преподаватели еще не добавлены. Добавьте вручную выше или загрузите из файла (.xlsx / .csv).</td></tr>`;
        return;
    }

    tbody.innerHTML = teachers.map(t => `
        <tr class="hover:bg-slate-50 transition border-b border-slate-100">
            <td class="px-3 py-2 font-semibold text-slate-800">${escapeHtml(t.name)}</td>
            <td class="px-3 py-2 text-slate-500">${escapeHtml(t.department || '—')}</td>
            <td class="px-3 py-2 text-slate-500">${escapeHtml(t.position || '—')}</td>
            <td class="px-3 py-2 text-right">
                <button onclick="removeTeacher('${t.id}')" class="text-slate-400 hover:text-rose-600 font-bold p-1">✕</button>
            </td>
        </tr>
    `).join('');
}

async function submitNewTeacher() {
    const nameInput = document.getElementById('new-teacher-name');
    const deptInput = document.getElementById('new-teacher-dept');
    const posInput = document.getElementById('new-teacher-pos');

    const name = nameInput.value.trim();
    if (!name) {
        alert('Пожалуйста, введите ФИО преподавателя.');
        return;
    }

    try {
        const res = await fetch('/api/teachers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                department: deptInput.value.trim(),
                position: posInput.value.trim(),
            }),
        });
        if (res.ok) {
            nameInput.value = '';
            deptInput.value = '';
            posInput.value = '';
            await loadTeachers();
            renderTeachersTable();
        }
    } catch (e) {
        alert('Ошибка добавления: ' + e.message);
    }
}

async function removeTeacher(id) {
    if (!confirm('Удалить преподавателя из справочника?')) return;
    try {
        const res = await fetch(`/api/teachers/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await loadTeachers();
            renderTeachersTable();
            await loadDisciplines();
        }
    } catch (e) {
        alert('Ошибка удаления: ' + e.message);
    }
}

async function uploadTeachersFile() {
    const input = document.getElementById('teachers-file-input');
    if (!input.files || input.files.length === 0) {
        alert('Выберите файл Excel (.xlsx) или CSV.');
        return;
    }

    showLoading('Импорт преподавателей...');
    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const res = await fetch('/api/teachers/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (data.success) {
            alert(`Импортировано преподавателей: ${data.imported_count}`);
            input.value = '';
            await loadTeachers();
            renderTeachersTable();
        }
    } catch (e) {
        alert('Ошибка загрузки: ' + e.message);
    } finally {
        hideLoading();
    }
}

function renderIndustriesTable() {
    const tbody = document.getElementById('industries-tbody');
    const countEl = document.getElementById('industries-count');
    const industries = Array.isArray(allIndustriesData) ? allIndustriesData : [];
    if (countEl) countEl.innerText = industries.length;

    if (!tbody) return;

    if (industries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="px-3 py-4 text-center text-slate-400">Отрасли еще не добавлены. Добавьте вручную выше или загрузите из файла (.xlsx / .csv).</td></tr>`;
        return;
    }

    tbody.innerHTML = industries.map(i => `
        <tr class="hover:bg-slate-50 transition border-b border-slate-100">
            <td class="px-3 py-2 font-semibold text-slate-800">${escapeHtml(i.name)}</td>
            <td class="px-3 py-2 text-slate-500">${escapeHtml(i.description || '—')}</td>
            <td class="px-3 py-2 text-right">
                <button onclick="removeIndustry('${i.id}')" class="text-slate-400 hover:text-rose-600 font-bold p-1">✕</button>
            </td>
        </tr>
    `).join('');
}

async function submitNewIndustry() {
    const nameInput = document.getElementById('new-industry-name');
    const descInput = document.getElementById('new-industry-desc');

    const name = nameInput.value.trim();
    if (!name) {
        alert('Пожалуйста, введите название отрасли.');
        return;
    }

    try {
        const res = await fetch('/api/industries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                description: descInput.value.trim(),
            }),
        });
        if (res.ok) {
            nameInput.value = '';
            descInput.value = '';
            await loadIndustries();
            renderIndustriesTable();
        }
    } catch (e) {
        alert('Ошибка добавления: ' + e.message);
    }
}

async function removeIndustry(id) {
    if (!confirm('Удалить отрасль из справочника?')) return;
    try {
        const res = await fetch(`/api/industries/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await loadIndustries();
            renderIndustriesTable();
            await loadDisciplines();
        }
    } catch (e) {
        alert('Ошибка удаления: ' + e.message);
    }
}

async function uploadIndustriesFile() {
    const input = document.getElementById('industries-file-input');
    if (!input.files || input.files.length === 0) {
        alert('Выберите файл Excel (.xlsx) или CSV.');
        return;
    }

    showLoading('Импорт отраслей...');
    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const res = await fetch('/api/industries/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (data.success) {
            alert(`Импортировано отраслей: ${data.imported_count}`);
            input.value = '';
            await loadIndustries();
            renderIndustriesTable();
        }
    } catch (e) {
        alert('Ошибка загрузки: ' + e.message);
    } finally {
        hideLoading();
    }
}

async function uploadBindingsFile() {
    const input = document.getElementById('bindings-file-input');
    if (!input.files || input.files.length === 0) {
        alert('Выберите файл Excel (.xlsx) или CSV.');
        return;
    }

    showLoading('Импорт связок дисциплин...');
    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const res = await fetch('/api/bindings/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (data.success) {
            alert(`Успешно обработано связок: ${data.imported_count}`);
            input.value = '';
            await refreshAllData();
            closeModal('modal-registry');
        }
    } catch (e) {
        alert('Ошибка импорта связок: ' + e.message);
    } finally {
        hideLoading();
    }
}

// --- Вкладка 3: Коллизии кафедр ---
async function loadConflicts() {
    const search = document.getElementById('conflicts-search')?.value || '';
    const year = document.getElementById('conflicts-year-filter')?.value || '';
    const academicYear = document.getElementById('conflicts-academic-year-filter')?.value || '';

    const params = new URLSearchParams();
    if (search.trim()) params.append('search', search.trim());
    if (year.trim()) params.append('year', year.trim());
    if (academicYear.trim()) params.append('academic_year', academicYear.trim());

    try {
        const res = await fetch(`/api/conflicts?${params.toString()}`);
        allConflictsData = await res.json();
        renderConflicts(allConflictsData);
    } catch (e) {
        console.error('Ошибка загрузки коллизий:', e);
    }
}

function filterConflicts() {
    loadConflicts();
}

function renderConflicts(conflicts) {
    const container = document.getElementById('conflicts-container');
    if (!conflicts || conflicts.length === 0) {
        container.innerHTML = `
            <div class="bg-white rounded-xl border border-emerald-200 p-8 text-center text-emerald-800 text-xs">
                <div class="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 mb-2">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                </div>
                <div class="font-bold text-sm">Отлично! Коллизии не обнаружены.</div>
                <p class="text-slate-500 mt-1">Все дисциплины согласованы и закреплены за однозначными кафедрами во всех планах.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = conflicts.map((c, cIdx) => {
        const deptNames = Object.keys(c.by_department);
        return `
            <div class="bg-white rounded-xl border border-rose-200 shadow-sm p-5 space-y-4">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                    <div class="flex items-center space-x-3">
                        <span class="px-2.5 py-1 rounded-md bg-rose-100 text-rose-800 text-xs font-bold">
                            Коллизия: ${c.departments.length} кафедры
                        </span>
                        <h4 class="text-base font-bold text-slate-900">${escapeHtml(c.discipline_title)}</h4>
                    </div>
                    <div class="text-xs text-slate-500">
                        Всего вхождений в планы: <span class="font-bold text-slate-800">${c.total_occurrences}</span>
                    </div>
                </div>

                <!-- Варианты закрепления по кафедрам -->
                <div class="grid grid-cols-1 md:grid-cols-${Math.min(deptNames.length, 3)} gap-4">
                    ${deptNames.map(deptName => {
                        const occurrences = c.by_department[deptName];
                        const isSuggested = c.suggested_target_dept === deptName;
                        const sampleOcc = occurrences[0] || {};
                        const deptCode = sampleOcc.dept_code || '';
                        return `
                            <div class="rounded-lg border ${isSuggested ? 'border-sky-300 bg-sky-50/40' : 'border-slate-200 bg-slate-50/50'} p-3 flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between mb-1.5">
                                        <span class="font-bold text-xs ${isSuggested ? 'text-sky-900' : 'text-slate-900'}">${escapeHtml(deptName)}</span>
                                        ${isSuggested ? `<span class="px-1.5 py-0.5 rounded text-[10px] bg-sky-200 text-sky-800 font-bold">Рекомендуется</span>` : ''}
                                    </div>
                                    <div class="text-[11px] text-slate-500 mb-2">
                                        Закреплено в <span class="font-semibold text-slate-700">${occurrences.length}</span> планах:
                                    </div>
                                    <ul class="text-[11px] text-slate-600 space-y-1 mb-3 max-h-36 overflow-y-auto pr-1">
                                        ${occurrences.map(o => `
                                            <li class="border-l-2 border-slate-300 pl-1.5 py-0.5">
                                                <div class="flex items-center justify-between gap-1">
                                                    <span class="font-medium text-slate-800">${escapeHtml(o.direction_code)} ${escapeHtml(o.profile_title || '')}</span>
                                                    <span class="px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 font-semibold text-[10px] whitespace-nowrap">${escapeHtml(o.academic_year || '—')} уч. год (${o.semester} сем.)</span>
                                                </div>
                                                <div class="text-[10px] text-slate-400">
                                                    ${escapeHtml(o.plan_name)} • Набор: ${escapeHtml(o.start_year || '—')}
                                                </div>
                                            </li>
                                        `).join('')}
                                    </ul>
                                </div>
                                <button onclick="quickResolveConflict('${escapeJs(c.discipline_title)}', '${escapeJs(deptCode)}', '${escapeJs(deptName)}')" class="w-full py-1.5 px-3 bg-white hover:bg-sky-600 hover:text-white text-sky-700 text-xs font-semibold rounded border border-sky-300 shadow-sm transition">
                                    Закрепить везде за этой кафедрой
                                </button>
                            </div>
                        `;
                    }).join('')}
                </div>

                <div class="flex justify-end pt-1">
                    <button onclick="openCustomDeptModal('${escapeJs(c.discipline_title)}')" class="text-xs text-slate-600 hover:text-slate-900 underline font-medium">
                        Выбрать другую кафедру из общего справочника...
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Быстрое закрепление за выбранной кафедрой
async function quickResolveConflict(disciplineTitle, deptCode, deptName) {
    try {
        showLoading(`Добавление закрепления кафедры для '${disciplineTitle}'...`);
        const res = await fetch('/api/stage-change', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action_type: 'change_dept',
                discipline_title: disciplineTitle,
                target_dept_code: deptCode,
                target_dept_name: deptName,
                affected_plan_files: [],
            }),
        });
        const data = await res.json();
        if (data.success) {
            await loadStatus();
            alert(`Изменение добавлено в очередь Diff! Проверьте вкладку 'Очередь изменений'.`);
        }
    } catch (e) {
        alert('Ошибка при добавлении изменения: ' + e.message);
    } finally {
        hideLoading();
    }
}

function openCustomDeptModal(disciplineTitle) {
    currentSelectedDiscipline = disciplineTitle;
    document.getElementById('modal-dept-title').innerText = `Закрепление дисциплины: ${disciplineTitle}`;
    document.getElementById('modal-dept-desc').innerText = `Выберите кафедру, за которой необходимо закрепить дисциплину во всех планах.`;

    const select = document.getElementById('modal-dept-select');
    select.innerHTML = allDepartmentsData.map(d => {
        const code = d.dept_codes && d.dept_codes.length ? d.dept_codes[0] : '';
        return `<option value="${code}">${d.dept_name} ${code ? `(№ ${code})` : ''}</option>`;
    }).join('');

    document.getElementById('modal-dept-picker').classList.remove('hidden');
}

async function confirmStageDeptChange() {
    if (!currentSelectedDiscipline) return;
    const select = document.getElementById('modal-dept-select');
    const selectedCode = select.value;
    const selectedText = select.options[select.selectedIndex]?.text || '';
    const deptName = selectedText.split('(№')[0].trim();

    closeModal('modal-dept-picker');
    await quickResolveConflict(currentSelectedDiscipline, selectedCode, deptName);
}

// --- Вкладка 4: Анализ форм контроля и аудит семестров ---

function switchControlSubTab(tab) {
    activeControlSubTab = tab;
    const btnConflicts = document.getElementById('subtab-ctrl-conflicts');
    const btnAudit = document.getElementById('subtab-ctrl-audit');
    const viewConflicts = document.getElementById('ctrl-view-conflicts');
    const viewAudit = document.getElementById('ctrl-view-audit');
    const overloadFilterWrapper = document.getElementById('controls-overload-filter-wrapper');

    if (tab === 'conflicts') {
        if (btnConflicts) {
            btnConflicts.classList.add('bg-white', 'text-slate-900', 'shadow-sm');
            btnConflicts.classList.remove('text-slate-600');
        }
        if (btnAudit) {
            btnAudit.classList.remove('bg-white', 'text-slate-900', 'shadow-sm');
            btnAudit.classList.add('text-slate-600');
        }
        if (viewConflicts) viewConflicts.classList.remove('hidden');
        if (viewAudit) viewAudit.classList.add('hidden');
        if (overloadFilterWrapper) overloadFilterWrapper.classList.add('hidden');
        loadControlConflicts();
    } else {
        if (btnAudit) {
            btnAudit.classList.add('bg-white', 'text-slate-900', 'shadow-sm');
            btnAudit.classList.remove('text-slate-600');
        }
        if (btnConflicts) {
            btnConflicts.classList.remove('bg-white', 'text-slate-900', 'shadow-sm');
            btnConflicts.classList.add('text-slate-600');
        }
        if (viewAudit) viewAudit.classList.remove('hidden');
        if (viewConflicts) viewConflicts.classList.add('hidden');
        if (overloadFilterWrapper) overloadFilterWrapper.classList.remove('hidden');
        loadSemesterAudits();
    }
}

async function loadControlData() {
    if (activeControlSubTab === 'conflicts') {
        await loadControlConflicts();
    } else {
        await loadSemesterAudits();
    }
}

function filterControlTab() {
    if (activeControlSubTab === 'conflicts') {
        loadControlConflicts();
    } else {
        loadSemesterAudits();
    }
}

async function loadControlConflicts() {
    const search = document.getElementById('controls-search')?.value || '';
    const year = document.getElementById('controls-year-filter')?.value || '';
    const academicYear = document.getElementById('controls-academic-year-filter')?.value || '';

    const params = new URLSearchParams();
    if (search.trim()) params.append('search', search.trim());
    if (year.trim()) params.append('year', year.trim());
    if (academicYear.trim()) params.append('academic_year', academicYear.trim());

    try {
        const res = await fetch(`/api/control-conflicts?${params.toString()}`);
        allControlConflictsData = await res.json();
        renderControlConflicts(allControlConflictsData);
    } catch (e) {
        console.error('Ошибка загрузки коллизий контроля:', e);
    }
}

function renderControlConflicts(conflicts) {
    const container = document.getElementById('ctrl-conflicts-container');
    if (!container) return;

    if (!conflicts || conflicts.length === 0) {
        container.innerHTML = `
            <div class="bg-white rounded-xl border border-emerald-200 p-8 text-center text-emerald-800 text-xs">
                <div class="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 mb-2">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                </div>
                <div class="font-bold text-sm">Коллизий форм контроля между планами не обнаружено</div>
                <p class="text-slate-500 mt-1">Все одинаковые дисциплины в сравниваемых учебных планах имеют согласованный вид аттестации (экзамен / зачет).</p>
            </div>
        `;
        return;
    }

    container.innerHTML = conflicts.map((c, idx) => {
        const formsList = c.control_forms || [];
        const byForm = c.by_form || {};
        const formNames = Object.keys(byForm);

        return `
            <div class="bg-white rounded-xl border border-amber-200 shadow-sm p-5 space-y-4">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="px-2.5 py-1 rounded-md bg-amber-100 text-amber-800 text-xs font-bold border border-amber-200">
                            Коллизия: ${formsList.join(' vs ')}
                        </span>
                        <h4 class="text-base font-bold text-slate-900">${escapeHtml(c.discipline_title)}</h4>
                    </div>
                    <div class="text-xs text-slate-500">
                        Всего вхождений в планы: <span class="font-bold text-slate-800">${c.occurrences_count}</span>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-${Math.min(Math.max(formNames.length, 1), 3)} gap-4">
                    ${formNames.map(formName => {
                        const occurrences = byForm[formName] || [];
                        const isExam = formName.toLowerCase().includes('экзамен');
                        return `
                            <div class="rounded-lg border ${isExam ? 'border-amber-200 bg-amber-50/30' : 'border-slate-200 bg-slate-50/40'} p-3 flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between mb-1.5">
                                        <span class="font-bold text-xs ${isExam ? 'text-amber-900' : 'text-slate-900'}">
                                            Форма: ${escapeHtml(formName)}
                                        </span>
                                        <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${isExam ? 'bg-amber-100 text-amber-800' : 'bg-slate-200 text-slate-700'}">
                                            ${occurrences.length} пл.
                                        </span>
                                    </div>
                                    <ul class="text-[11px] text-slate-600 space-y-1.5 max-h-48 overflow-y-auto pr-1">
                                        ${occurrences.map(o => `
                                            <li class="border-l-2 ${isExam ? 'border-amber-400' : 'border-slate-300'} pl-2 py-0.5">
                                                <div class="flex items-center justify-between gap-1">
                                                    <span class="font-medium text-slate-800 truncate" title="${escapeHtml(o.direction_title || '')}">${escapeHtml(o.direction_code)} ${escapeHtml(o.profile_title || '')}</span>
                                                    <span class="px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 font-semibold text-[10px] whitespace-nowrap">${escapeHtml(o.academic_year || '—')} уч. год</span>
                                                </div>
                                                <div class="text-[10px] text-slate-400 mt-0.5">
                                                    ${escapeHtml(o.plan_name)} • Сем. ${o.semester} • Набор: ${escapeHtml(o.start_year || '—')} • ЗЕТ: ${o.total_ze}
                                                </div>
                                                <div class="text-[10px] text-slate-500">
                                                    Кафедра: ${escapeHtml(o.dept_name || '—')}
                                                </div>
                                            </li>
                                        `).join('')}
                                    </ul>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }).join('');
}

async function loadSemesterAudits() {
    const search = document.getElementById('controls-search')?.value || '';
    const year = document.getElementById('controls-year-filter')?.value || '';
    const academicYear = document.getElementById('controls-academic-year-filter')?.value || '';
    const overloadOnly = document.getElementById('controls-overload-only')?.checked || false;

    const params = new URLSearchParams();
    if (search.trim()) params.append('search', search.trim());
    if (year.trim()) params.append('year', year.trim());
    if (academicYear.trim()) params.append('academic_year', academicYear.trim());
    if (overloadOnly) params.append('overloaded_only', 'true');

    try {
        const res = await fetch(`/api/control-audit?${params.toString()}`);
        allSemesterAuditsData = await res.json();
        renderSemesterAudits(allSemesterAuditsData);
    } catch (e) {
        console.error('Ошибка загрузки аудита семестров:', e);
    }
}

function renderSemesterAudits(audits) {
    const container = document.getElementById('ctrl-audit-container');
    if (!container) return;

    if (!audits || audits.length === 0) {
        container.innerHTML = `
            <div class="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-400 text-xs">
                По выбранным параметрам семестры не найдены либо нарушения нормативов отсутствуют.
            </div>
        `;
        return;
    }

    container.innerHTML = audits.map((a, idx) => {
        const isOverloaded = a.is_overloaded;
        const issues = a.overload_reasons || [];
        const disciplines = a.disciplines_details || [];

        return `
            <div class="bg-white rounded-xl border ${isOverloaded ? 'border-rose-300 shadow-rose-50' : 'border-slate-200'} p-4 shadow-sm hover:shadow transition space-y-3">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="font-bold text-sm text-slate-900">${escapeHtml(a.direction_code)} ${escapeHtml(a.direction_title || '')}</span>
                        ${a.profile_title ? `<span class="text-xs text-slate-500">(${escapeHtml(a.profile_title)})</span>` : ''}
                        <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-100 text-sky-800">
                            ${a.semester} семестр (${a.course} курс)
                        </span>
                        <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                            ${escapeHtml(a.academic_year || '—')} уч. год
                        </span>
                    </div>

                    <div>
                        ${isOverloaded ? `
                            <span class="px-2.5 py-1 rounded-md text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
                                ⚠ Перегрузка: ${issues.join('; ')}
                            </span>
                        ` : `
                            <span class="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                ✓ Нормативы ФГОС соблюдены
                            </span>
                        `}
                    </div>
                </div>

                <!-- Метрики семестра -->
                <div class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2 text-xs">
                    <div class="bg-slate-50 p-2 rounded border border-slate-200 text-center">
                        <div class="text-[10px] text-slate-400 uppercase font-semibold">Экзамены</div>
                        <div class="text-sm font-bold ${a.exams_count > a.max_exams_allowed ? 'text-rose-600' : 'text-slate-800'}">
                            ${a.exams_count} <span class="text-[10px] text-slate-400 font-normal">/ макс ${a.max_exams_allowed}</span>
                        </div>
                    </div>
                    <div class="bg-slate-50 p-2 rounded border border-slate-200 text-center">
                        <div class="text-[10px] text-slate-400 uppercase font-semibold">Зачеты</div>
                        <div class="text-sm font-bold ${a.passes_count > a.max_passes_allowed ? 'text-rose-600' : 'text-slate-800'}">
                            ${a.passes_count} <span class="text-[10px] text-slate-400 font-normal">/ макс ${a.max_passes_allowed}</span>
                        </div>
                    </div>
                    <div class="bg-slate-50 p-2 rounded border border-slate-200 text-center">
                        <div class="text-[10px] text-slate-400 uppercase font-semibold">Дифзачеты</div>
                        <div class="text-sm font-bold text-slate-800">
                            ${a.diff_passes_count}
                        </div>
                    </div>
                    <div class="bg-slate-50 p-2 rounded border border-slate-200 text-center">
                        <div class="text-[10px] text-slate-400 uppercase font-semibold">Курсовые</div>
                        <div class="text-sm font-bold ${a.course_works_count > a.max_course_works_allowed ? 'text-rose-600' : 'text-slate-800'}">
                            ${a.course_works_count} <span class="text-[10px] text-slate-400 font-normal">/ макс ${a.max_course_works_allowed}</span>
                        </div>
                    </div>
                    <div class="bg-slate-50 p-2 rounded border border-slate-200 text-center">
                        <div class="text-[10px] text-slate-400 uppercase font-semibold">Всего дисциплин</div>
                        <div class="text-sm font-bold text-sky-800">${a.total_disciplines}</div>
                    </div>
                    <div class="bg-slate-50 p-2 rounded border border-slate-200 text-center">
                        <div class="text-[10px] text-slate-400 uppercase font-semibold">Сумма ЗЕТ</div>
                        <div class="text-sm font-bold text-sky-800">${a.total_ze} ЗЕТ</div>
                    </div>
                </div>

                <div class="flex justify-between items-center text-xs text-slate-500 pt-1">
                    <span class="truncate max-w-sm" title="${escapeHtml(a.plan_file)}">Файл: <b>${escapeHtml(a.plan_name)}</b> (набор ${a.start_year || '—'})</span>
                    <button onclick="toggleAuditDisciplines(${idx})" class="text-sky-600 hover:text-sky-800 font-semibold">
                        Дисциплины семестра (${disciplines.length}) ↓
                    </button>
                </div>

                <!-- Раскрывающийся список дисциплин семестра -->
                <div id="audit-disciplines-${idx}" class="hidden bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
                    <div class="font-semibold text-slate-700 mb-2">Дисциплины и формы контроля в семестре:</div>
                    <ul class="space-y-1 divide-y divide-slate-200 text-slate-600">
                        ${disciplines.map(d => `
                            <li class="pt-1 flex items-center justify-between gap-2">
                                <span class="font-medium text-slate-800">${escapeHtml(d.title)}</span>
                                <div class="flex items-center space-x-2">
                                    <span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-white border border-slate-200 text-slate-700">
                                        ${escapeHtml(d.controls.join(', ') || '—')}
                                    </span>
                                    <span class="text-slate-500 font-medium">${d.ze} ЗЕТ</span>
                                </div>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            </div>
        `;
    }).join('');
}

function toggleAuditDisciplines(idx) {
    const el = document.getElementById(`audit-disciplines-${idx}`);
    if (el) el.classList.toggle('hidden');
}

// --- Вкладка 5: Анализ подобия ---
function updateSimilarityThreshold(val) {
    document.getElementById('similarity-threshold-val').innerText = val + '%';
}

async function reloadSimilarities() {
    const sliderVal = document.getElementById('similarity-slider')?.value || 75;
    const minScore = parseFloat(sliderVal) / 100.0;
    const hiddenOnly = document.getElementById('sim-hidden-only')?.checked || false;

    showLoading('Вычисление векторных эмбеддингов и семантического сходства...');
    try {
        const res = await fetch(`/api/similarities?min_score=${minScore}&hidden_only=${hiddenOnly}`);
        const pairs = await res.json();
        renderSimilarities(pairs);
    } catch (e) {
        console.error('Ошибка анализа подобия:', e);
    } finally {
        hideLoading();
    }
}

function renderSimilarities(pairs) {
    const container = document.getElementById('similarity-container');
    if (!pairs || pairs.length === 0) {
        container.innerHTML = `
            <div class="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-400 text-xs">
                Похожих дисциплин с заданным порогом схожести не найдено. Попробуйте уменьшить порог ползунком.
            </div>
        `;
        return;
    }

    container.innerHTML = pairs.map((p, pIdx) => {
        const percent = Math.round(p.combined_score * 100);
        return `
            <div class="bg-white rounded-xl border ${p.is_hidden_conflict ? 'border-amber-300 bg-amber-50/20' : 'border-slate-200'} p-4 shadow-sm space-y-3">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-100 pb-2">
                    <div class="flex items-center space-x-2">
                        <span class="px-2 py-0.5 rounded text-xs font-bold ${percent >= 90 ? 'bg-emerald-100 text-emerald-800' : 'bg-sky-100 text-sky-800'}">
                            Сходство ${percent}%
                        </span>
                        ${p.is_hidden_conflict ? `
                            <span class="px-2 py-0.5 rounded text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
                                Скрытая коллизия: разные кафедры!
                            </span>
                        ` : ''}
                    </div>
                    <div class="text-xs text-slate-500">
                        Лексика: ${(p.lexical_similarity * 100).toFixed(0)}% | Семантика (AI): ${(p.semantic_similarity * 100).toFixed(0)}%
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div class="p-3 rounded-lg bg-slate-50 border border-slate-200">
                        <div class="font-bold text-slate-900 mb-1 text-sm">${escapeHtml(p.discipline_a)}</div>
                        <div class="text-slate-500">Кафедра: <span class="font-medium text-slate-700">${escapeHtml(p.depts_a.join(', ') || '—')}</span></div>
                        <div class="text-slate-400 text-[11px] mt-0.5">Встречается в планах: ${p.plans_count_a}</div>
                    </div>
                    <div class="p-3 rounded-lg bg-slate-50 border border-slate-200">
                        <div class="font-bold text-slate-900 mb-1 text-sm">${escapeHtml(p.discipline_b)}</div>
                        <div class="text-slate-500">Кафедра: <span class="font-medium text-slate-700">${escapeHtml(p.depts_b.join(', ') || '—')}</span></div>
                        <div class="text-slate-400 text-[11px] mt-0.5">Встречается в планах: ${p.plans_count_b}</div>
                    </div>
                </div>

                <div class="flex justify-end pt-1">
                    <button onclick="openUnifyModal('${escapeJs(p.discipline_a)}', '${escapeJs(p.discipline_b)}')" class="px-3 py-1.5 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold rounded shadow-sm transition">
                        Унифицировать названия и кафедру...
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function openUnifyModal(titleA, titleB) {
    currentUnifyPair = { a: titleA, b: titleB };

    document.getElementById('unify-opt-a').value = titleA;
    document.getElementById('unify-label-a').innerText = titleA;
    document.getElementById('unify-opt-a').checked = true;

    document.getElementById('unify-opt-b').value = titleB;
    document.getElementById('unify-label-b').innerText = titleB;

    const deptSelect = document.getElementById('modal-unify-dept-select');
    deptSelect.innerHTML = `<option value="">-- Оставить кафедры без изменений --</option>` +
        allDepartmentsData.map(d => {
            const code = d.dept_codes && d.dept_codes.length ? d.dept_codes[0] : '';
            return `<option value="${code}">${d.dept_name} ${code ? `(№ ${code})` : ''}</option>`;
        }).join('');

    document.getElementById('modal-unify').classList.remove('hidden');
}

async function confirmStageUnifyChange() {
    if (!currentUnifyPair) return;
    const selectedTitle = document.querySelector('input[name="modal-canonical-title"]:checked')?.value;
    const deptSelect = document.getElementById('modal-unify-dept-select');
    const selectedDeptCode = deptSelect.value || null;
    let selectedDeptName = null;
    if (selectedDeptCode) {
        selectedDeptName = deptSelect.options[deptSelect.selectedIndex]?.text?.split('(№')[0]?.trim();
    }

    const otherTitle = (selectedTitle === currentUnifyPair.a) ? currentUnifyPair.b : currentUnifyPair.a;

    closeModal('modal-unify');
    showLoading(`Добавление унификации дисциплин в очередь Diff...`);

    try {
        const res = await fetch('/api/stage-change', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action_type: 'unify',
                discipline_title: otherTitle,
                new_discipline_title: selectedTitle,
                target_dept_code: selectedDeptCode,
                target_dept_name: selectedDeptName,
            }),
        });

        if (selectedDeptCode) {
            await fetch('/api/stage-change', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action_type: 'change_dept',
                    discipline_title: selectedTitle,
                    target_dept_code: selectedDeptCode,
                    target_dept_name: selectedDeptName,
                }),
            });
        }

        await loadStatus();
        alert('Унификация добавлена в очередь Diff!');
    } catch (e) {
        alert('Ошибка добавления унификации: ' + e.message);
    } finally {
        hideLoading();
    }
}

// --- Вкладка 5: Очередь изменений (Diff Viewer) ---
async function loadStaged() {
    try {
        const res = await fetch('/api/staged');
        const data = await res.json();
        renderDiffTable(data.diffs || []);
    } catch (e) {
        console.error('Ошибка загрузки очереди diff:', e);
    }
}

function renderDiffTable(diffs) {
    const tbody = document.getElementById('diff-tbody');
    if (!diffs || diffs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-8 text-center text-slate-400">Очередь изменений пуста.</td></tr>`;
        return;
    }

    tbody.innerHTML = diffs.map((d, idx) => `
        <tr class="hover:bg-slate-50 transition border-b border-slate-100">
            <td class="px-4 py-3 font-medium text-slate-900">${escapeHtml(d.file_name)}</td>
            <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-100 text-sky-800">${escapeHtml(d.change_type)}</span></td>
            <td class="px-4 py-3 text-slate-500">
                ${d.original_title ? `<div><span class="font-medium text-slate-700">Дисциплина:</span> ${escapeHtml(d.original_title)}</div>` : ''}
                ${d.original_dept_name ? `<div><span class="font-medium text-slate-700">Кафедра:</span> ${escapeHtml(d.original_dept_name)} (№${escapeHtml(d.original_dept_code)})</div>` : ''}
            </td>
            <td class="px-4 py-3 text-emerald-700 font-medium">
                ${d.new_title ? `<div><span class="font-semibold text-emerald-900">Новое название:</span> ${escapeHtml(d.new_title)}</div>` : ''}
                ${d.new_dept_name ? `<div><span class="font-semibold text-emerald-900">Новая кафедра:</span> ${escapeHtml(d.new_dept_name)} (№${escapeHtml(d.new_dept_code)})</div>` : ''}
            </td>
        </tr>
    `).join('');
}

async function clearStaged() {
    if (!confirm('Вы уверены, что хотите очистить всю очередь подготовленных изменений?')) return;
    try {
        await fetch('/api/staged', { method: 'DELETE' });
        await loadStatus();
        await loadStaged();
    } catch (e) {
        alert('Ошибка очистки очереди: ' + e.message);
    }
}

function openApplyModal() {
    if (stagedChangesCount === 0) {
        alert('В очереди нет подготовленных изменений для сохранения.');
        return;
    }
    document.getElementById('modal-apply-confirm').classList.remove('hidden');
}

function toggleApplyOutputDir(show) {
    document.getElementById('apply-output-dir-box').classList.toggle('hidden', !show);
}

async function executeApplyChanges() {
    const mode = document.querySelector('input[name="apply-mode"]:checked')?.value || 'backup';
    const outputDir = (mode === 'output') ? document.getElementById('apply-output-dir').value.trim() : null;

    if (mode === 'output' && !outputDir) {
        alert('Пожалуйста, укажите путь к выходной папке.');
        return;
    }

    closeModal('modal-apply-confirm');
    showLoading('Запись изменений в файлы планов...');

    try {
        const res = await fetch('/api/apply-changes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                backup: (mode === 'backup'),
                output_dir: outputDir,
            }),
        });
        const resp = await res.json();
        if (resp.success) {
            alert(`Успешно обновлено файлов: ${resp.modified_files_count}\nВсего модификаций: ${resp.total_modifications}\n${resp.backup_created ? 'Созданы резервные копии .bak' : ''}`);
            await refreshAllData();
            switchTab('conflicts');
        } else {
            alert('Ошибка применения изменений:\n' + (resp.errors || []).join('\n'));
        }
    } catch (e) {
        alert('Ошибка при выполнении операции: ' + e.message);
    } finally {
        hideLoading();
    }
}

// --- Утилиты ---
function closeModal(modalId) {
    const m = document.getElementById(modalId);
    if (m) {
        m.classList.add('hidden');
        m.style.display = 'none';
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeJs(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// Экспорт глобальных функций для вызова из HTML onclick/onchange
window.openRegistryModal = openRegistryModal;
window.closeModal = closeModal;
window.switchRegistryTab = switchRegistryTab;
window.switchTab = switchTab;
window.loadDemoPlans = loadDemoPlans;
window.loadDisciplines = loadDisciplines;
window.filterDisciplines = filterDisciplines;
window.resetDisciplineFilters = resetDisciplineFilters;
window.openDisciplineBindModal = openDisciplineBindModal;
window.saveDisciplineBinding = saveDisciplineBinding;
window.submitNewTeacher = submitNewTeacher;
window.removeTeacher = removeTeacher;
window.uploadTeachersFile = uploadTeachersFile;
window.submitNewIndustry = submitNewIndustry;
window.removeIndustry = removeIndustry;
window.uploadIndustriesFile = uploadIndustriesFile;
window.uploadBindingsFile = uploadBindingsFile;
window.deletePlanByIndex = deletePlanByIndex;
window.clearAllPlans = clearAllPlans;
window.loadFromDirectory = loadFromDirectory;
window.switchControlSubTab = switchControlSubTab;
window.filterControlTab = filterControlTab;
window.loadControlData = loadControlData;
window.loadControlConflicts = loadControlConflicts;
window.loadSemesterAudits = loadSemesterAudits;
window.toggleAuditDisciplines = toggleAuditDisciplines;
