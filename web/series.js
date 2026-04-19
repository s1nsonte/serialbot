const tg = window.Telegram.WebApp;
tg.expand();

const params = new URLSearchParams(window.location.search);
const id = params.get("id");

fetch(`/api/series/${id}`)
.then(r => r.json())
.then(data => {

    const app = document.getElementById("app");

    const seasons = data.seasons;
    const watched = new Set(
        data.watched.map(w => `${w[0]}-${w[1]}`)
    );

    Object.keys(seasons).forEach(season => {

        const seasonBlock = document.createElement("div");
        seasonBlock.className = "season-block";

        seasonBlock.innerHTML = `<h2>Сезон ${season}</h2>`;

        const row = document.createElement("div");
        row.className = "episodes-row";

        seasons[season].forEach(ep => {

            const key = `${season}-${ep.episode}`;
            const isWatched = watched.has(key);

            const card = document.createElement("div");
            card.className = "episode-card " + (isWatched ? "watched" : "");

            card.innerHTML = `
                <div class="ep-number">E${ep.episode}</div>
                <div class="ep-title">${ep.name}</div>
            `;

            card.onclick = async () => {
                await fetch("/api/toggle", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        series_id: id,
                        season: parseInt(season),
                        episode: ep.episode
                    })
                });

                card.classList.toggle("watched");
            };

            row.appendChild(card);
        });

        seasonBlock.appendChild(row);
        app.appendChild(seasonBlock);
    });
});
