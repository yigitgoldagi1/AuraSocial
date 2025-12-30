import uvicorn
import json
import sqlite3
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Dict

app = FastAPI()

# --- VERİTABANI KURULUMU ---
def veri_tabani_kur():
    conn = sqlite3.connect('sosyal.db')
    c = conn.cursor()
    # Kullanıcı bilgileri tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS kullanicilar 
                 (username TEXT PRIMARY KEY, bio TEXT, foto TEXT)''')
    # Hikayeler tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS hikayeler 
                 (username TEXT, mesaj TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

veri_tabani_kur()

# Aktif kullanıcıları takip etmek için sözlük
active_users: Dict[str, WebSocket] = {}

@app.get("/")
async def get():
    # Ana sayfa olarak index.html dosyasını gönderir
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/profil-guncelle")
async def profil_guncelle(data: dict):
    conn = sqlite3.connect('sosyal.db')
    c = conn.cursor()
    c.execute("UPDATE kullanicilar SET bio = ?, foto = ? WHERE username = ?", 
              (data.get("bio"), data.get("foto"), data.get("username")))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/kesfet")
async def kesfet():
    conn = sqlite3.connect('sosyal.db')
    c = conn.cursor()
    c.execute("SELECT username, bio, foto FROM kullanicilar")
    data = [{"username": r[0], "bio": r[1], "foto": r[2]} for r in c.fetchall()]
    conn.close()
    return data

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    active_users[username] = websocket
    
    # Yeni giren kullanıcıyı veritabanına ekle
    conn = sqlite3.connect('sosyal.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO kullanicilar (username, bio, foto) VALUES (?, ?, ?)", 
              (username, "Aura Social'a hoş geldin!", ""))
    conn.commit()
    conn.close()

    try:
        while True:
            data = await websocket.receive_text()
            paket = json.loads(data)
            
            # --- DM (ÖZEL MESAJ) MANTIĞI ---
            if paket.get("tip") == "dm":
                hedef = paket.get("hedef")
                mesaj_paketi = json.dumps({
                    "user": username, 
                    "text": paket["text"], 
                    "is_dm": True
                })
                # Mesajı hedefe gönder
                if hedef in active_users:
                    await active_users[hedef].send_text(mesaj_paketi)
                # Mesajı gönderene (kendine) de geri gönder
                await websocket.send_text(mesaj_paketi)
            
            # --- GENEL SOHBET MANTIĞI ---
            else:
                for user, conn_ws in active_users.items():
                    await conn_ws.send_text(json.dumps({
                        "user": username, 
                        "text": paket["text"], 
                        "is_dm": False
                    }))
    except WebSocketDisconnect:
        if username in active_users:
            del active_users[username]

# --- SUNUCU ÇALIŞTIRMA (BULUT UYUMLU) ---
if __name__ == "__main__":
    # Render veya Heroku gibi servisler 'PORT' çevresel değişkenini kullanır.
    # Eğer bulunamazsa varsayılan olarak 8000 portunu açar.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)