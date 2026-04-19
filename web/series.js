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

        const seasonDiv = document.createElement("div");
        seasonDiv.className = "season";

        seasonDiv.innerHTML = `<h2>Сезон ${season}</h2>`;

        seasons[season].forEach(ep => {

            const key = `${season}-${ep.episode}`;
            const isWatched = watched.has(key);

            const epDiv = document.createElement("div");
            epDiv.className = "episode " + (isWatched ? "watched" : "");

            epDiv.innerHTML = `
                <span>Серия ${ep.episode}: ${ep.name}</span>
                <span>${isWatched ? "✔" : ""}</span>
            `;

            epDiv.onclick = async () => {
                await fetch("/api/toggle", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        series_id: id,
                        season: parseInt(season),
                        episode: ep.episode
                    })
                });

                epDiv.classList.toggle("watched");
                epDiv.querySelector("span:last-child").innerText =
                    epDiv.classList.contains("watched") ? "✔" : "";
            };

            seasonDiv.appendChild(epDiv);
        });

        app.appendChild(seasonDiv);
    });
});
