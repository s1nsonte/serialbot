let userId = null;

if (window.Telegram && window.Telegram.WebApp) {
    const tg = window.Telegram.WebApp;
    tg.expand();

    if (tg.initDataUnsafe?.user) {
        userId = tg.initDataUnsafe.user.id;
    }
}

if (!userId) userId = 271898917;

const app = document.getElementById("app");

// ================= СПИСОК =================
function loadSeries() {
    fetch(`/api/series?user_id=${userId}`)
    .then(r => r.json())
    .then(data => {
        app.innerHTML = "";

        data.forEach(s => {
            const card = document.createElement("div");
            card.className = "card";

            card.innerHTML = `
                <img src="${s.poster || ''}">
                <div class="title">${s.name}</div>
                <button class="open">Открыть</button>
                <button class="delete">Удалить</button>
            `;

            card.querySelector(".open").onclick = () => openSeries(s.id);
            card.querySelector(".delete").onclick = () => deleteSeries(s.id);

            app.appendChild(card);
        });
    });
}

// ================= ОТКРЫТЬ СЕРИАЛ =================
function openSeries(id) {
    fetch(`/api/series_detail?series_id=${id}`)
    .then(r => r.json())
    .then(data => {
        app.innerHTML = `
            <div class="back">← Назад</div>
            <h2>${data.name}</h2>
            <img class="poster" src="${data.poster}">
            <div id="seasons"></div>
        `;

        document.querySelector(".back").onclick = loadSeries;

        const seasonsDiv = document.getElementById("seasons");

        Object.keys(data.episodes).forEach(season => {
            const total = data.episodes[season];
            const watched = data.watched[season] || [];

            const seasonDiv = document.createElement("div");
            seasonDiv.className = "season";

            seasonDiv.innerHTML = `<h3>Сезон ${season}</h3>`;

            for (let i = 1; i <= total; i++) {
                const ep = document.createElement("div");
                ep.className = "episode";

                if (watched.includes(i)) {
                    ep.classList.add("watched");
                }

                ep.innerText = `E${i}`;

                ep.onclick = () => {
                    markEpisode(id, season, i, ep);
                };

                seasonDiv.appendChild(ep);
            }

            seasonsDiv.appendChild(seasonDiv);
        });
    });
}

// ================= ОТМЕТКА =================
function markEpisode(seriesId, season, episode, el) {
    fetch("/api/mark", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({series_id: seriesId, season, episode})
    })
    .then(() => {
        el.classList.add("watched");
    });
}

// ================= УДАЛЕНИЕ =================
function deleteSeries(id) {
    if (!confirm("Удалить сериал?")) return;

    fetch("/api/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({series_id: id})
    })
    .then(() => loadSeries());
}

// старт
loadSeries();
