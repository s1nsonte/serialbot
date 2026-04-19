const tg = window.Telegram.WebApp;
tg.expand();

// fallback если Telegram не передал user
let userId = null;

if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
    userId = tg.initDataUnsafe.user.id;
} else {
    // ВРЕМЕННЫЙ ФИКС (подставь свой ID)
    userId = 271898917;
}

fetch(`/api/series?user_id=${userId}`)
.then(r => r.json())
.then(data => {
    const app = document.getElementById("app");

    if (!data.length) {
        app.innerHTML = "<div style='color:white'>Нет сериалов 😢</div>";
        return;
    }

    data.forEach(s => {
        const d = document.createElement("div");
        d.className = "card";

        d.innerHTML = `
            <img src="${s.poster || ''}">
            <div class="title">${s.name}</div>
        `;

        app.appendChild(d);
    });
});
}

// ===== открыть сериал =====
function openSeries(id, name) {
    fetch(`/api/detail?id=${id}`)
    .then(r => r.json())
    .then(data => {
        const app = document.getElementById("app");
        app.innerHTML = "";

        // кнопка назад
        const back = document.createElement("div");
        back.className = "back";
        back.innerText = "← Назад";
        back.onclick = loadSeries;
        app.appendChild(back);

        const seasons = {};

        // группируем по сезонам
        data.forEach(ep => {
            if (!seasons[ep.season]) seasons[ep.season] = [];
            seasons[ep.season].push(ep);
        });

        // вывод
        Object.keys(seasons).forEach(seasonNum => {
            const block = document.createElement("div");
            block.className = "season";

            block.innerHTML = `<h2>Сезон ${seasonNum}</h2>`;

            seasons[seasonNum].forEach(ep => {
                const e = document.createElement("div");
                e.className = "episode";

                if (ep.watched) {
                    e.classList.add("watched");
                }

                e.innerHTML = `
                    <span>Серия ${ep.episode}</span>
                    <span>${ep.watched ? "✔" : "◻"}</span>
                `;

                // переключение просмотра
                e.onclick = () => {
                    fetch(`/api/watch?series_id=${id}&season=${ep.season}&episode=${ep.episode}`)
                    .then(() => {
                        e.classList.add("watched");
                        e.innerHTML = `
                            <span>Серия ${ep.episode}</span>
                            <span>✔</span>
                        `;
                    });
                };

                block.appendChild(e);
            });

            app.appendChild(block);
        });
    });
}

// старт
loadSeries();
