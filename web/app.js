const tg = window.Telegram.WebApp;
tg.expand();

const user = tg.initDataUnsafe?.user;

if (!user) {
    document.body.innerHTML = "Открывай через Telegram";
}

const app = document.getElementById("app");

// ================= LOAD LIST =================
async function loadSeries() {
    const res = await fetch(`/api/series?user_id=${user.id}`);
    const data = await res.json();

    app.innerHTML = "";

    data.forEach(s => {
        const card = document.createElement("div");
        card.className = "card";

        card.innerHTML = `
            <img src="${s.poster}">
            <div class="overlay">
                <div class="title">${s.name}</div>
                <button onclick="openSeries(${s.id})">Подробнее</button>
            </div>
        `;

        app.appendChild(card);
    });
}

// ================= OPEN SERIES =================
async function openSeries(id) {
    const res = await fetch(`/api/series_detail?series_id=${id}`);
    const data = await res.json();

    app.innerHTML = `
        <div class="back" onclick="loadSeries()">← Назад</div>

        <div class="hero">
            <img src="${data.poster}">
            <div class="hero-title">${data.name}</div>
        </div>

        <div id="seasons"></div>

        <button class="delete" onclick="deleteSeries(${id})">Удалить сериал</button>
    `;

    const seasonsDiv = document.getElementById("seasons");

    data.seasons.forEach(season => {
        const total = season.total;
        const watched = season.watched.length;

        const percent = Math.floor((watched / total) * 100);

        const block = document.createElement("div");
        block.className = "season";

        block.innerHTML = `
            <div class="season-header">
                Сезон ${season.season}
                <span>${watched} / ${total}</span>
            </div>

            <div class="progress">
                <div class="bar" style="width:${percent}%"></div>
            </div>

            <div class="episodes" id="season-${season.season}"></div>
        `;

        seasonsDiv.appendChild(block);

        const epContainer = document.getElementById(`season-${season.season}`);

        for (let i = 1; i <= total; i++) {
            const ep = document.createElement("div");
            ep.className = "episode";

            if (season.watched.includes(i)) {
                ep.classList.add("watched");
            }

            ep.innerText = i;

            ep.onclick = async () => {
                await toggleEpisode(id, season.season, i);
                openSeries(id); // перерисовка
            };

            epContainer.appendChild(ep);
        }
    });
}

// ================= TOGGLE =================
async function toggleEpisode(series_id, season, episode) {
    await fetch("/api/toggle", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            series_id,
            season,
            episode
        })
    });
}

// ================= DELETE =================
async function deleteSeries(id) {
    if (!confirm("Удалить сериал?")) return;

    await fetch("/api/delete", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ series_id: id })
    });

    loadSeries();
}

// ================= START =================
loadSeries();
