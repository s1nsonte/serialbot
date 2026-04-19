const tg = window.Telegram.WebApp;
tg.expand();

const user = tg.initDataUnsafe?.user;

if (!user) {
    document.body.innerHTML = "Open from Telegram";
}

const API = "";

// ================= LOAD SERIES =================

async function loadSeries() {
    const res = await fetch(`/api/series?user_id=${user.id}`);
    const data = await res.json();

    const app = document.getElementById("app");
    app.innerHTML = "";

    data.forEach(s => {
        const progress = s.total ? (s.progress / s.total) * 100 : 0;

        const div = document.createElement("div");
        div.className = "card";

        div.innerHTML = `
            <img src="${s.poster}">
            <div class="info">
                <div class="title">${s.name}</div>
                <div class="progress">
                    <div class="bar" style="width:${progress}%"></div>
                </div>
                <button onclick="openSeries(${s.id})">Подробнее</button>
            </div>
        `;

        app.appendChild(div);
    });
}

// ================= OPEN SERIES =================

async function openSeries(id) {
    const res = await fetch(`/api/series_detail?series_id=${id}`);
    const data = await res.json();

    const app = document.getElementById("app");

    app.innerHTML = `
        <div class="detail">
            <div class="hero" style="background-image:url('${data.poster}')">
                <div class="overlay">
                    <h1>${data.name}</h1>
                </div>
            </div>
            <div id="seasons"></div>
        </div>
    `;

    renderSeasons(data, id);
}

// ================= RENDER SEASONS =================

function renderSeasons(data, series_id) {
    const container = document.getElementById("seasons");
    container.innerHTML = "";

    Object.keys(data.seasons).forEach(season => {
        const episodes = data.seasons[season];

        const watched = episodes.filter(e => e.watched).length;
        const total = episodes.length;

        const div = document.createElement("div");
        div.className = "season";

        div.innerHTML = `
            <div class="season-header">
                <h2>Сезон ${season}</h2>
                <span>${watched} / ${total}</span>
            </div>

            <div class="episodes" id="season-${season}"></div>
        `;

        container.appendChild(div);

        const epContainer = div.querySelector(".episodes");

        episodes.forEach(ep => {
            const e = document.createElement("div");
            e.className = "episode " + (ep.watched ? "watched" : "");
            e.innerText = ep.episode;

            e.onclick = async () => {
                await fetch("/api/toggle_episode", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        series_id,
                        season: parseInt(season),
                        episode: ep.episode
                    })
                });

                openSeries(series_id);
            };

            epContainer.appendChild(e);
        });
    });
}

// ================= INIT =================

loadSeries();
