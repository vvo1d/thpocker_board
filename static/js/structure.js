// static/js/structure.js
// БЕЗ анимации каждую секунду + работает на мобильных

let lastLevelsHash = '';
let lastCurrentIndex = -1;
let lastIsBreak = null;
let lastProgress = -1;
let userHasScrolled = false;
let autoScrollTimeout = null;
let currentActiveRow = null;

function hashLevels(levels) {
    return JSON.stringify(levels.map(l => `${l.type}-${l.duration}-${l.small_blind}-${l.big_blind}`));
}

function renderLevels(data) {
    const tbody = document.getElementById('structure-body');
    const lastUpdateEl = document.getElementById('last-update');
    const titleEl = document.getElementById('structure-title');
    const now = new Date();

    tbody.innerHTML = '';

    if (!data.levels || data.levels.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:2rem;opacity:0.6;">Структура не задана</td></tr>`;
        lastUpdateEl.textContent = now.toLocaleTimeString('ru-RU');
        if (titleEl) titleEl.textContent = 'Структура турнира';
        currentActiveRow = null;
        return;
    }

    let levelCounter = 0;
    const currentIdx = data.current_index;
    const isBreak = data.is_break;
    const currentLevel = data.levels[currentIdx];
    const totalSeconds = (currentLevel?.duration || 0) * 60;
    const remainingSeconds = data.remaining || 0;
    const progress = totalSeconds > 0 ? Math.max(0, Math.min(100, (1 - remainingSeconds / totalSeconds) * 100)) : 0;

    if (titleEl) {
        titleEl.textContent = isBreak ? 'ПЕРЕРЫВ' : 'Структура турнира';
        titleEl.style.color = isBreak ? '#e74c3c' : '#4ecca3';
    }

    data.levels.forEach((lvl, idx) => {
        const row = document.createElement('tr');
        const isCurrent = idx === currentIdx;

        const minutes = isCurrent ? Math.floor(remainingSeconds / 60) : '-';
        const seconds = isCurrent ? (remainingSeconds % 60).toString().padStart(2, '0') : '-';
        const timerText = isCurrent ? `${minutes}:${seconds}` : `${lvl.duration}`;

        if (lvl.type === 'break') {
            row.classList.add('break-row');
            if (isCurrent) { row.classList.add('current-break'); currentActiveRow = row; }
            row.innerHTML = `<td>-</td><td class="duration timer">${timerText}</td><td>-</td><td>-</td><td>ПЕРЕРЫВ</td>`;
        } else {
            levelCounter++;
            if (isCurrent) { row.classList.add('current-level'); currentActiveRow = row; }
            row.innerHTML = `<td class="level-num">${levelCounter}</td><td class="duration timer">${timerText}</td><td class="blinds">${lvl.small_blind}</td><td class="blinds">${lvl.big_blind}</td><td></td>`;
        }

        // === ЗАЛИВКА ===
        if (isCurrent && totalSeconds > 0) {
            const fill = document.createElement('div');
            fill.className = `row-fill ${isBreak ? 'break' : 'level'}`;
            row.appendChild(fill);

            // АНИМАЦИЯ ТОЛЬКО ПРИ СМЕНЕ УРОВНЯ
            if (currentIdx !== lastCurrentIndex || isBreak !== lastIsBreak) {
                fill.style.width = '0%';
                requestAnimationFrame(() => {
                    fill.style.transition = 'width 1.2s cubic-bezier(0.4, 0, 0.2, 1)';
                    fill.style.width = `${progress}%`;
                });
            } else {
                // Каждую секунду — БЕЗ transition
                fill.style.transition = 'none';
                fill.style.width = `${progress}%`;
            }
        }

        tbody.appendChild(row);
    });

    lastUpdateEl.textContent = now.toLocaleTimeString('ru-RU');

    if (currentActiveRow && !userHasScrolled) {
        setTimeout(() => currentActiveRow.scrollIntoView({ behavior: 'smooth', block: 'center' }), 300);
    }
    resetAutoScrollTimer();
}

// === ОБНОВЛЕНИЕ ===
async function updateStructure(force = false) {
    try {
        const res = await fetch('/api/structure');
        if (!res.ok) return;
        const data = await res.json();

        const currentHash = hashLevels(data.levels || []);
        const currentIndex = data.current_index;
        const isBreak = data.is_break;
        const currentLevel = data.levels[currentIndex];
        const totalSeconds = (currentLevel?.duration || 0) * 60;
        const remainingSeconds = data.remaining || 0;
        const progress = totalSeconds > 0 ? (1 - remainingSeconds / totalSeconds) * 100 : 0;

        const shouldUpdate = force ||
            currentHash !== lastLevelsHash ||
            currentIndex !== lastCurrentIndex ||
            isBreak !== lastIsBreak ||
            Math.abs(progress - lastProgress) > 0.1;

        if (shouldUpdate) {
            renderLevels(data);
            lastLevelsHash = currentHash;
            lastCurrentIndex = currentIndex;
            lastIsBreak = isBreak;
            lastProgress = progress;
        }
    } catch (err) {
        console.error('Update failed:', err);
    }
}

// === СКРОЛЛ ===
const tableContainer = document.querySelector('.table-container');
if (tableContainer) {
    let scrollTimer = null;
    tableContainer.addEventListener('scroll', () => {
        userHasScrolled = true;
        if (scrollTimer) clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => { userHasScrolled = false; resetAutoScrollTimer(); }, 1000);
        resetAutoScrollTimer();
    });
}

function resetAutoScrollTimer() {
    if (autoScrollTimeout) clearTimeout(autoScrollTimeout);
    autoScrollTimeout = setTimeout(() => {
        if (userHasScrolled && currentActiveRow) {
            currentActiveRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            userHasScrolled = false;
        }
    }, 10000);
}

// === СИНХРОНИЗАЦИЯ ===
function triggerUpdate() { updateStructure(true); }
window.addEventListener('storage', e => e.key === 'structure-trigger' && triggerUpdate());
window.addEventListener('message', e => e.data?.type === 'structure-updated' && triggerUpdate());
window.addEventListener('structure-updated', triggerUpdate);

// === СТАРТ ===
updateStructure(true);
setInterval(() => updateStructure(), 1000);