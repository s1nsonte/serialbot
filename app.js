const tg = window.Telegram.WebApp;
tg.expand();

const user = tg.initDataUnsafe?.user;
if(!user){document.body.innerHTML="Open from Telegram";}

fetch(`/api/series?user_id=${user.id}`)
.then(r=>r.json())
.then(data=>{
    const app=document.getElementById("app");
    data.forEach(s=>{
        const d=document.createElement("div");
        d.className="card";
        d.innerHTML=`<img src="${s.poster}"><div class="title">${s.name}</div>`;
        app.appendChild(d);
    });
});
