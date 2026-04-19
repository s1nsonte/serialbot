const tg = window.Telegram.WebApp;
tg.expand();

const user = tg.initDataUnsafe?.user;

if (!user) {
    document.body.innerHTML = "Open from Telegram";
}

let currentSeries = null;

// ================= LOAD SERIES =================
async function loadSeries() {
    const res = await fetch(`/api/series?user_id=${user.id}`);
    const data = await res.json();

    const app = document.getElementById("app");
    app.innerHTML = "";

    data.forEach(s => {
        const card = document.createElement("div");
        card.className = "card";

        card.innerHTML = `
            <img src="${s.poster}" />
            <div class="title">${s.name}</div>
            <div class="meta">${buildSeasonsInfo(s)}</div>
            <div class="progress">
                <div class="bar" style="width:${calcProgress(s)}%"></div>
            </div>
            <button onclick="openSeries(${s.id})">Подробнее</button>
        `;

        app.appendChild(card);
    });
}

// ================= META =================
function buildSeasonsInfo(s) {
    if (!s.episodes) return "";

    let text = "";
    for (let season in s.episodes) {
        text += `С${season}: ${s.episodes[season]} серий<br>`;
    }
    return text;
}

function calcProgress(s) {
    if (!s.episodes) return 0;

    let total = 0;
    let watched = 0;

    for (let season in s.episodes) {
        total += s.episodes[season];
    }

    if (s.watched) {
        watched = s.watched.length;
    }

    return total ? (watched / total) * 100 : 0;
}

// ================= OPEN SERIES =================
async function openSeries(id) {
    const res = await fetch(`/api/series_detail?series_id=${id}`);
    const s = await res.json();

    currentSeries = s;

    const app = document.getElementById("app");
    app.innerHTML = "";

    // HEADER (Netflix style)
    const header = document.createElement("div");
    header.className = "hero";

    header.innerHTML = `
        <img src="${s.poster}" class="hero-img"/>
        <div class="hero-overlay"></div>
        <div class="hero-info">
            <h2>${s.name}</h2>
            <button onclick="back()">← Назад</button>
        </div>
    `;

    app.appendChild(header);

    // SEASONS
    const seasonsBlock = document.createElement("div");
    seasonsBlock.className = "seasons";

    Object.keys(s.episodes).forEach(season => {
        const seasonDiv = document.createElement("div");
        seasonDiv.className = "season";

        seasonDiv.innerHTML = `<h3>Сезон ${season}</h3>`;

        const episodesRow = document.createElement("div");
        episodesRow.className = "episodes-row";

        for (let i = 1; i <= s.episodes[season]; i++) {
            const ep = document.createElement("div");

            const isWatched = s.watched?.some(
                w => w.season == season && w.episode == i
            );

            ep.className = "episode " + (isWatched ? "watched" : "");

            ep.innerHTML = `
                <div class="ep-num">E${i}</div>
            `;

            ep.onclick = () => toggleEpisode(season, i, ep);

            episodesRow.appendChild(ep);
        }

        seasonDiv.appendChild(episodesRow);
        seasonsBlock.appendChild(seasonDiv);
    });

    app.appendChild(seasonsBlock);
}

// ================= TOGGLE =================
async function toggleEpisode(season, episode, el) {
    const res = await fetch("/api/toggle_episode", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            series_id: currentSeries.id,
            season,
            episode
        })
    });

    const data = await res.json();

    if (data.watched) {
        el.classList.add("watched");
    } else {
        el.classList.remove("watched");
    }
}

// ================= BACK =================
function back() {
    loadSeries();
}

// ================= START =================
loadSeries();
