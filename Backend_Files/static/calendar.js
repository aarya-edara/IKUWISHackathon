document.addEventListener('DOMContentLoaded', function () {
    const monthYear = document.getElementById('month-year');
    const daysContainer = document.getElementById('days');
    const prevButton = document.getElementById('prev');
    const nextButton = document.getElementById('next');

    const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
    ];

    let currentDate = new Date();
    let today = new Date();

    // tasks scheduled by the task manager: { "2026-10-18": [{task, minutes, priority}, ...] }
    let schedule = {};

    function dateKey(d) {
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    function formatMinutes(m) {
        const h = Math.floor(m / 60);
        const mm = m % 60;
        return (h ? h + 'h' : '') + (mm ? (h ? ' ' : '') + mm + 'm' : '') || '0m';
    }

    function renderCalendar(date) {

        const year = date.getFullYear();
        const month = date.getMonth();
        const firstDay = (new Date(year, month, 1).getDay() + 6) % 7;
        const lastDay = new Date(year, month + 1, 0).getDate();

        monthYear.textContent = `${months[month]} ${year}`;

        daysContainer.innerHTML = '';

        // prev month dates

        const prevMonthLastDay = new Date(year, month, 0).getDate();
        for (let i = firstDay; i > 0; i--) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = prevMonthLastDay - i + 1;
            dayDiv.classList.add('fade');
            daysContainer.appendChild(dayDiv);
        }

        // current month dates

        for (let i = 1; i <= lastDay; i++) {
            const dayDiv = document.createElement('div');
            const key = dateKey(new Date(year, month, i));

            const dayNumber = document.createElement('span');
            dayNumber.textContent = i;
            dayDiv.appendChild(dayNumber);

            if (i === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
                dayDiv.classList.add('today');
            }

            // Show Google events that overlap this day.
            const dayStart = new Date(year, month, i);
            const dayEnd = new Date(year, month, i + 1);

            (window.googleEvents || []).forEach(function (event) {
                if (event.status === 'cancelled' || !event.start || !event.end) return;

                let overlaps;

                if (event.start.date) {
                    // All-day events: Google's end date is exclusive.
                    overlaps = event.start.date <= key && key < event.end.date;
                } else {
                    const start = new Date(event.start.dateTime);
                    const end = new Date(event.end.dateTime);
                    overlaps = start < dayEnd && end > dayStart;
                }

                if (overlaps) {
                    const eventDiv = document.createElement('div');
                    eventDiv.classList.add('google-event');
                    eventDiv.textContent = event.summary || '(No title)';
                    eventDiv.title = eventDiv.textContent;
                    dayDiv.appendChild(eventDiv);
                }
            });

            // Show tasks from the task manager.
            (schedule[key] || []).forEach(function (t) {
                const taskDiv = document.createElement('div');
                taskDiv.className = 'cal-task priority-' + t.priority;
                taskDiv.textContent = t.task + ' ' + formatMinutes(t.minutes);
                taskDiv.title = taskDiv.textContent + ' (' + t.priority + ')';
                dayDiv.appendChild(taskDiv);
            });

            daysContainer.appendChild(dayDiv);
        }

        // next month dates

        const nextMonthStartDay = (7 - (firstDay + lastDay) % 7) % 7;
        for (let i = 1; i <= nextMonthStartDay; i++) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = i;
            dayDiv.classList.add('fade');
            daysContainer.appendChild(dayDiv);
        }

    }

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

    fetch('/api/schedule', { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            schedule = data || {};
            renderCalendar(currentDate);
        })
        .catch(function (e) { console.error('Could not load schedule', e); });
});