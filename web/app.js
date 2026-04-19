const tg = window.Telegram.WebApp;
const userId = tg.initDataUnsafe?.user?.id;

const app = document.getElementById("app");

if (!userId) {
  app.innerHTML = "Открой через Telegram";
  throw new Error("no user");
}

loadSeries();


// ================= LIST =================
async function loadSeries() {
  const res = await fetch(`/api/series?user_id=${userId}`);
  const data = await res.json();

  app.innerHTML = `
    <div class="grid">
      ${data.map(renderCard).join("")}
    </div>
  `;
}

function renderCard(s) {
  const progress = s.total ? Math.floor((s.watched / s.total) * 100) : 0;

  let seasonsInfo = "";

  if (s.seasons) {
    seasonsInfo = Object.entries(s.seasons)
      .map(([season, d]) => `Сезон ${season} — ${d.watched}/${d.total}`)
      .join("<br>");
  }

  return `
    <div class="card" onclick="openSeries(${s.id})">
      <img src="${s.poster}" class="poster"/>

      <div class="overlay">
        <h3>${s.name}</h3>

        <div class="progress">
          <div class="bar" style="width:${progress}%"></div>
        </div>

        <p>${s.watched}/${s.total}</p>

        <div class="seasons-info">${seasonsInfo}</div>

        <button class="btn">Подробнее</button>
      </div>
    </div>
  `;
}


// ================= DETAIL =================
async function openSeries(id) {
  const res = await fetch(`/api/series_detail?series_id=${id}&user_id=${userId}`);
  const s = await res.json();

  const watchedSet = new Set(s.watched.map(e => `${e[0]}-${e[1]}`));

  let html = "";

  for (let season in s.episodes) {
    const eps = s.episodes[season];

    let watchedCount = 0;
    eps.forEach(e => {
      if (watchedSet.has(`${season}-${e.episode}`)) watchedCount++;
    });

    const progress = Math.floor((watchedCount / eps.length) * 100);

    html += `
      <div class="season">
        <h3>Сезон ${season}</h3>

        <div class="progress">
          <div class="bar" style="width:${progress}%"></div>
        </div>

        <p>${watchedCount}/${eps.length}</p>

        <div class="episodes">
          ${eps.map(e => renderEpisode(id, season, e, watchedSet)).join("")}
        </div>
      </div>
    `;
  }

  app.innerHTML = `
    <div class="hero" style="background-image:url('${s.poster}')">
      <div class="hero-overlay">
        <h2>${s.name}</h2>
        <button class="back" onclick="loadSeries()">Назад</button>
      </div>
    </div>

    ${html}
  `;
}


// ================= EPISODE =================
function renderEpisode(seriesId, season, ep, watchedSet) {
  const watched = watchedSet.has(`${season}-${ep.episode}`);

  return `
    <div class="episode ${watched ? "watched" : ""}"
         onclick="toggleEpisode(${seriesId}, ${season}, ${ep.episode})">

      ${ep.episode}
      <div class="date">${ep.air_date || ""}</div>

    </div>
  `;
}


// ================= TOGGLE =================
async function toggleEpisode(seriesId, season, episode) {
  await fetch("/api/toggle_episode", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      user_id: userId,
      series_id: seriesId,
      season,
      episode
    })
  });

  openSeries(seriesId);
}
