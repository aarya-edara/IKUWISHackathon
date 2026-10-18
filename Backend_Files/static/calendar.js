document.addEventListener('DOMContentLoaded', function () {
    const TASKS_KEY = 'tasks';

    function loadTasks() {
        try { return JSON.parse(localStorage.getItem(TASKS_KEY)) || {}; }
        catch (e) { return {}; }
    }

    function saveTasks(data) {
        try { localStorage.setItem(TASKS_KEY, JSON.stringify(data)); } catch (e) {}
        refresh();
    }

    function dateKey(d) {
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    function formatHours(h) {
        const mins = Math.round(h * 60);
        const hh = Math.floor(mins / 60);
        const mm = mins % 60;
        return (hh ? hh + 'h' : '') + (mm ? (hh ? ' ' : '') + mm + 'm' : '') || '0m';
    }

    const monthYear = document.getElementById('month-year');
    const daysContainer = document.getElementById('days');
    const prevButton = document.getElementById('prev');
    const nextButton = document.getElementById('next');
    const taskList = document.getElementById('task-list');
    const selectedLabel = document.getElementById('selected-date');

    const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
    ];

    let currentDate = new Date();
    let today = new Date();
    let selectedKey = dateKey(today);
    let tasks = loadTasks();

    function renderCalendar(date) {

        const year = date.getFullYear();
        const month = date.getMonth();
        const firstDay = (new Date(year, month, 1).getDay() + 6) % 7;
        const lastDay = new Date(year, month + 1, 0).getDate();

        monthYear.textContent = `${months[month]} ${year}`;

        daysContainer.innerHTML = '';

        const prevMonthLastDay = new Date(year, month, 0).getDate();
        for (let i = firstDay; i > 0; i--) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = prevMonthLastDay - i + 1;
            dayDiv.classList.add('fade');
            daysContainer.appendChild(dayDiv);
        }

        for (let i = 1; i <= lastDay; i++) {
            const dayDiv = document.createElement('div');
            const key = dateKey(new Date(year, month, i));
            dayDiv.textContent = i;
            if (i === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
                dayDiv.classList.add('today');
            }
            if (key === selectedKey) dayDiv.classList.add('selected');
            if (tasks[key] && tasks[key].length) dayDiv.classList.add('has-tasks');

            dayDiv.addEventListener('click', function () {
                selectedKey = key;
                renderCalendar(currentDate);
                renderTasks();
            });

            daysContainer.appendChild(dayDiv);
        }

        const nextMonthStartDay = (7 - (firstDay + lastDay) % 7) % 7;
        for (let i = 1; i <= nextMonthStartDay; i++) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = i;
            dayDiv.classList.add('fade');
            daysContainer.appendChild(dayDiv);
        }

    }

    function renderTasks() {
        if (!taskList) return;
        if (selectedLabel) selectedLabel.textContent = selectedKey;
        taskList.innerHTML = '';
        (tasks[selectedKey] || []).forEach(function (t, index) {
            const li = document.createElement('li');
            li.textContent = (typeof t === 'string'
                ? t
                : t.name + ' – ' + formatHours(t.hours) + (t.priority ? ' (' + t.priority + ')' : '')) + ' ';
            const del = document.createElement('button');
            del.type = 'button';
            del.textContent = '✕';
            del.addEventListener('click', function () {
                tasks[selectedKey].splice(index, 1);
                if (!tasks[selectedKey].length) delete tasks[selectedKey];
                saveTasks(tasks);
            });
            li.appendChild(del);
            taskList.appendChild(li);
        });
    }

    function refresh() {
        tasks = loadTasks();
        renderCalendar(currentDate);
        renderTasks();
    }

    window.addEventListener('storage', function (e) {
        if (e.key === TASKS_KEY) refresh();
    });
    window.addEventListener('pageshow', refresh);

    prevButton.addEventListener('click', function () {
        currentDate.setDate(1);
        currentDate.setMonth(currentDate.getMonth() - 1);
        renderCalendar(currentDate);
    });

    nextButton.addEventListener('click', function () {
        currentDate.setDate(1);
        currentDate.setMonth(currentDate.getMonth() + 1);
        renderCalendar(currentDate);
    });

    renderCalendar(currentDate);
    renderTasks();
});