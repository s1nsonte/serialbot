const tg = window.Telegram.WebApp;
const userId = tg.initDataUnsafe?.user?.id;

const app = document.getElementById("app");

if (!userId) {
  app.innerHTML = "<p>Открой через Telegram</p>";
  throw new Error("No user_id");
}

loadSeries();


// =========================
// 📺 СПИСОК СЕРИАЛОВ
// =========================
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

  return `
    <div class="card" onclick="openSeries(${s.id})">
      <img src="${s.poster}" class="poster"/>

      <div class="overlay">
        <h3>${s.name}</h3>

        <div class="progress">
          <div class="bar" style="width:${progress}%"></div>
        </div>

        <p>${s.watched} / ${s.total} просмотрено</p>

        <button class="btn">Подробнее</button>
      </div>
    </div>
  `;
}


// =========================
// 🎬 ДЕТАЛКА (Netflix)
// =========================
async function openSeries(id) {
  const res = await fetch(`/api/series_detail?series_id=${id}&user_id=${userId}`);
  const s = await res.json();

  const watchedSet = new Set(s.watched.map(e => `${e[0]}-${e[1]}`));

  let seasonsHTML = "";

  for (let season in s.episodes) {
    const episodes = s.episodes[season];

    let watchedCount = 0;
    episodes.forEach(e => {
      if (watchedSet.has(`${season}-${e}`)) watchedCount++;
    });

    const progress = Math.floor((watchedCount / episodes.length) * 100);

    seasonsHTML += `
      <div class="season">
        <h3>Сезон ${season}</h3>

        <div class="progress">
          <div class="bar" style="width:${progress}%"></div>
        </div>

        <p>${watchedCount} / ${episodes.length}</p>

        <div class="episodes">
          ${episodes.map(ep => renderEpisode(id, season, ep, watchedSet)).join("")}
        </div>
      </div>
    `;
  }

  app.innerHTML = `
    <div class="detail">

      <div class="hero" style="background-image:url('${s.poster}')">
        <div class="hero-overlay">
          <h1>${s.name}</h1>
          <button onclick="loadSeries()" class="back">← Назад</button>
        </div>
      </div>

      <div class="seasons">
        ${seasonsHTML}
      </div>

    </div>
  `;
}


// =========================
// 🎞️ ЭПИЗОД
// =========================
function renderEpisode(seriesId, season, ep, watchedSet) {
  const watched = watchedSet.has(`${season}-${ep}`);

  return `
    <div 
      class="episode ${watched ? "watched" : ""}"
      onclick="toggleEpisode(${seriesId}, ${season}, ${ep})"
    >
      ${ep}
    </div>
  `;
}


// =========================
// 🔄 TOGGLE СЕРИИ
// =========================
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
