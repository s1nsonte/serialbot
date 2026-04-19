let userId = null;

// Проверяем Telegram
if (window.Telegram && window.Telegram.WebApp) {
    const tg = window.Telegram.WebApp;
    tg.expand();

    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        userId = tg.initDataUnsafe.user.id;
    }
}

// fallback (чтобы не ломалось)
if (!userId) {
    console.log("Нет Telegram user → используем тестовый ID");
    userId = 271898917; // ← поставь свой ID
}

console.log("USER ID:", userId);

// загрузка сериалов
fetch(`/api/series?user_id=${userId}`)
.then(r => r.json())
.then(data => {
    console.log("DATA:", data);

    const app = document.getElementById("app");

    if (!data.length) {
        app.innerHTML = "<div style='color:white'>Нет сериалов 😢</div>";
        return;
    }

    data.forEach(s => {
        const d = document.createElement("div");
        d.className = "card";

        d.innerHTML = `
            <img src="${s.poster || ''}">
            <div class="title">${s.name}</div>
        `;

        app.appendChild(d);
    });
})
.catch(e => {
    console.error("Ошибка:", e);
});
