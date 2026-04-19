let userId = null;

if (window.Telegram?.WebApp) {
    const tg = window.Telegram.WebApp;
    tg.expand();
    userId = tg.initDataUnsafe?.user?.id;
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
                <img src="${s.poster}">
                <div class="title">${s.name}</div>
                <button onclick="openSeries(${s.id})">Подробнее</button>
            `;

            card.onclick = () => openSeries(s.id);

            app.appendChild(card);
        });
    });
}

// ================= ОТКРЫТЬ =================
function openSeries(id) {
    fetch(`/api/series_detail?series_id=${id}`)
    .then(r => r.json())
    .then(data => {

        app.innerHTML = `
            <div class="back">← Назад</div>
            <img class="poster" src="${data.poster}">
            <h2>${data.name}</h2>
            <div id="seasons"></div>
        `;

        document.querySelector(".back").onclick = loadSeries;

        const container = document.getElementById("seasons");

        Object.keys(data.seasons).forEach(season => {

            const seasonBlock = document.createElement("div");
            seasonBlock.className = "season";

            seasonBlock.innerHTML = `<h3>Сезон ${season}</h3>`;

            data.seasons[season].forEach(ep => {
                const el = document.createElement("div");
                el.className = "episode";

                if (ep.watched) el.classList.add("watched");
                if (!ep.released) el.classList.add("locked");

                el.innerText = `E${ep.episode}`;

                if (ep.released) {
                    el.onclick = () => mark(id, season, ep.episode, el);
                }

                seasonBlock.appendChild(el);
            });

            container.appendChild(seasonBlock);
        });
    });
}

// ================= MARK =================
function mark(seriesId, season, episode, el) {
    fetch("/api/mark", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            series_id: seriesId,
            season,
            episode
        })
    })
    .then(() => {
        el.classList.add("watched");
    });
}

loadSeries();
