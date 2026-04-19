const tg = window.Telegram.WebApp;
tg.expand();

const user = tg.initDataUnsafe?.user;

if (!user) {
    document.body.innerHTML = "Open from Telegram";
}

const API = "/api";

let currentSeries = null;

// ================= LOAD LIST =================
async function loadSeries() {
    const res = await fetch(`${API}/series?user_id=${user.id}`);
    const data = await res.json();

    const app = document.getElementById("app");
    app.innerHTML = "";

    data.forEach(s => {
        const total = Object.values(s.episodes || {}).reduce((a,b)=>a+b,0);

        const d = document.createElement("div");
        d.className = "card";

        d.innerHTML = `
            <img src="${s.poster}">
            <div class="card-body">
                <div class="title">${s.name}</div>
                <div class="progress">
                    <div class="bar" style="width:0%"></div>
                </div>
                <div class="meta">0 / ${total}</div>
                <button onclick="openSeries(${s.id})">Подробнее</button>
            </div>
        `;

        app.appendChild(d);
    });
}

// ================= OPEN SERIES =================
async function openSeries(id) {
    const res = await fetch(`${API}/series_detail?series_id=${id}`);
    const data = await res.json();

    currentSeries = data;

    renderSeries(data);
}

// ================= RENDER SERIES =================
function renderSeries(data) {
    const app = document.getElementById("app");

    const seasons = Object.keys(data.episodes).sort((a,b)=>a-b);

    app.innerHTML = `
        <div class="hero" style="background-image:url('${data.poster}')">
            <div class="overlay">
                <h1>${data.name}</h1>
                <div class="season-tabs">
                    ${seasons.map(s=>`<div onclick="selectSeason(${s})" id="tab-${s}">S${s}</div>`).join("")}
                </div>
                <div id="episodes"></div>
            </div>
        </div>
        <button class="back" onclick="loadSeries()">← Назад</button>
    `;

    selectSeason(seasons[0]);
}

// ================= SELECT SEASON =================
function selectSeason(season) {
    document.querySelectorAll(".season-tabs div").forEach(e=>e.classList.remove("active"));
    document.getElementById(`tab-${season}`).classList.add("active");

    const total = currentSeries.episodes[season];

    const watchedSet = new Set(
        currentSeries.watched.map(w => `${w[0]}-${w[1]}`)
    );

    const container = document.getElementById("episodes");

    container.innerHTML = `
        <div class="episodes">
            ${Array.from({length: total}, (_,i)=>{
                const ep = i+1;
                const key = `${season}-${ep}`;
                const watched = watchedSet.has(key);

                return `
                    <div class="ep ${watched ? "watched":""}"
                        onclick="toggle(${season},${ep})">
                        ${ep}
                    </div>
                `;
            }).join("")}
        </div>
    `;
}

// ================= TOGGLE =================
async function toggle(season, episode) {
    await fetch("/api/toggle", {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
            series_id: currentSeries.id,
            season,
            episode
        })
    });

    openSeries(currentSeries.id);
}

// INIT
loadSeries();
