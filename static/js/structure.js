let lastLevelsHash = '';
let lastCurrentIndex = -1;
let lastIsBreak = null;
let currentActiveRow = null;

function hashLevels(levels) {
    return JSON.stringify(levels.map(l => `${l.type}-${l.duration}-${l.small_blind}-${l.big_blind}`));
}

function renderLevels(data) {
    const tbody = document.getElementById('structure-body');
    const titleEl = document.getElementById('structure-title');

    tbody.innerHTML = '';

    if (!data.levels || data.levels.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:2rem;opacity:0.4;">Структура не задана</td></tr>`;
        lastUpdateEl.textContent = now.toLocaleTimeString('ru-RU');
        return;
    }

    let levelCounter = 0;
    const currentIdx = data.current_index;
    const isBreak = data.is_break;
    const remainingSeconds = data.remaining || 0;

    if (titleEl) {
        titleEl.textContent = isBreak ? 'ПЕРЕРЫВ' : 'Структура турнира';
        titleEl.style.color = isBreak ? '#550000' : '#fff';
    }

    data.levels.forEach((lvl, idx) => {
        const row = document.createElement('tr');
        const isCurrent = idx === currentIdx;

        const minutes = Math.floor(remainingSeconds / 60);
        const seconds = (remainingSeconds % 60).toString().padStart(2, '0');
        const timerText = isCurrent ? `${minutes}:${seconds}` : `${lvl.duration} мин`;

        if (lvl.type === 'break') {
            row.classList.add('break-row');
            if (isCurrent) { row.classList.add('current-break'); currentActiveRow = row; }
            row.innerHTML = `
                <td>—</td>
                <td class="duration">${timerText}</td>
                <td>—</td>
                <td>—</td>
                <td>ПЕРЕРЫВ</td>`;
        } else {
            levelCounter++;
            if (isCurrent) { row.classList.add('current-level'); currentActiveRow = row; }
            row.innerHTML = `
                <td class="level-num">${levelCounter}</td>
                <td class="duration">${timerText}</td>
                <td class="blinds">${lvl.small_blind.toLocaleString('ru-RU')}</td>
                <td class="blinds">${lvl.big_blind.toLocaleString('ru-RU')}</td>
                <td></td>`;
        }

        tbody.appendChild(row);
    });

    if (currentActiveRow) {
        currentActiveRow.scrollIntoView({ block: 'center' });
    }
}

async function updateStructure(force = false) {
    try {
        const res = await fetch('/api/structure');
        if (!res.ok) return;
        const data = await res.json();

        const currentHash = hashLevels(data.levels || []);
        const shouldUpdate = force ||
            currentHash !== lastLevelsHash ||
            data.current_index !== lastCurrentIndex ||
            data.is_break !== lastIsBreak;

        if (shouldUpdate) {
            renderLevels(data);
            lastLevelsHash = currentHash;
            lastCurrentIndex = data.current_index;
            lastIsBreak = data.is_break;
        } else {
            // Обновляем только таймер текущего уровня
            const timerCells = document.querySelectorAll('tr.current-level .duration, tr.current-break .duration');
            if (timerCells.length > 0) {
                const r = data.remaining || 0;
                const m = Math.floor(r / 60);
                const s = (r % 60).toString().padStart(2, '0');
                timerCells[0].textContent = `${m}:${s}`;
            }
        }
    } catch (err) {
        console.error('Update failed:', err);
    }
}

updateStructure(true);
setInterval(() => updateStructure(), 1000);
