Skip to content
s1nsonte
serialbot
Repository navigation
Code
Issues
Pull requests
Actions
Projects
Wiki
Security and quality
Insights
Settings
Files
Go to file
t
T
static
app.js
style.css
web
app.js
index.html
series.html
series.js
style.css
Dockerfile
README.md
bot.py
requirements.txt
serialbot/web
/
app.js
in
main

Edit

Preview
Indent mode

Spaces
Indent size

2
Line wrap mode

No wrap
Editing app.js file contents
  1
  2
  3
  4
  5
  6
  7
  8
  9
 10
 11
 12
 13
 14
 15
 16
 17
 18
 19
 20
 21
 22
 23
 24
 25
 26
 27
 28
 29
 30
 31
 32
 33
 34
 35
 36
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

Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
 
