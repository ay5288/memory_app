import os, re, json, random, datetime, urllib.parse, requests
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, FollowEvent, TextMessage, LocationMessage, ImageMessage,
    TextSendMessage, FlexSendMessage, BubbleContainer, CarouselContainer,
    BoxComponent, TextComponent, ButtonComponent, URIAction, MessageAction
)

app = FastAPI()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

# ⚠️ 1. 請填入「兒時記憶與當兵同袍尋人資料庫」的 Google Apps Script /exec 網址
GOOGLE_SHEET_API = "https://script.google.com/macros/s/AKfycbz3dZ_h1X5pQxcDHhTBrbwdUFbaOo6ARrAWOBPMPVTgfKxfn0PmuxfH4G3D2z3xOXi8/exec"
# ⚠️ 2. 請填入這個尋人與記憶機器人的 LINE 官方帳號 ID（包含 @ 符號，例如 @123abcde）
LINE_BOT_BASIC_ID = "@356yvdwm"
# ⚠️ 3. 請填入這個機器人的 Render 公開網址（結尾不要加斜線）
RENDER_BASE_URL = "https://onrender.com"
# ⚠️ 4. 可填入您的 Notion 懷舊零食／復古遊戲機／底片相機推薦館網址（未填自動隱藏）
NOTION_RETRO_SHOP_URL = ""

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

MEMORY_PHOTO_CACHE = {}
MEMORY_WALL_ITEMS = [
    {"id": "", "category": "當兵同袍", "area": "成功嶺新訓 1852梯 · 1999年", "target": "尋找三連同梯弟兄「大頭」與班長", "story": "還記得夏夜在集合場邊喝小蜜蜂的冰綠豆湯、半夜一起站安全士官聊退伍後的夢想嗎？退伍二十多年了，好想找大家出來聚一聚！", "author": "1852梯老兵", "time": "軍旅置頂"},
    {"id": "", "category": "尋人啟事", "area": "新北市五股國小 · 1998屆", "target": "尋找六年三班班長陳小明", "story": "還記得畢業那天我們一起在操場榕樹下埋了玻璃彈珠嗎？希望有機會辦一場小學同學會！", "author": "六年三班同學", "time": "校園置頂"},
    {"id": "", "category": "感動故事", "area": "巷口柑仔店 · 1990年代", "target": "10元抽抽樂 ＆ 外婆的綠豆湯", "story": "每天放學拿著零用錢衝去雜貨店抽當當，回家總有一碗冰涼的綠豆湯等著我，那是人生最無憂無慮的時光。", "author": "五股老街孩子", "time": "懷舊置頂"}
]

NOSTALGIA_CARDS = [
    ("🎖️ 成功嶺大專集訓 ＆ 軍營小蜜蜂", "『報告班長！』當年頂著大太陽在操場踢正步，最期待休息哨音一響，衝向營站買一瓶冰鎮舒跑跟小蜜蜂肉粽！"),
    ("🎮 任天堂紅白機 ＆ 魂斗羅", "『上上下下左右左右BA！』當年跟鄰居朋友擠在電視機前輪流接關，一玩就是整個暑假下午。"),
    ("🐣 1997 電子雞（塔麻可吉）", "上課偷偷藏在抽屜裡按按鈕餵飯、清大便，深怕一不注意它就變成小天使飛走了！"),
    ("🍬 巷口柑仔店 5 元抽抽樂", "放學鐘聲一響就衝去雜貨店，花 5 塊錢戳洞抽綠豆糕、橡皮糖跟黏黏手。"),
    ("📺 晚上八點《灌籃高手》＆《七龍珠》", "每天準時守在電視前等片頭曲響起，隔天到學校全班都在模仿櫻木花道跟龜派氣功！"),
    ("📒 畢業紀念冊「百事可樂、一帆風順」", "小學畢業前夕大家互相傳閱畢業紀念冊，最流行在最後一頁寫上『勿忘我』跟『步步高升』！")
]
def call_sheet(payload: dict):
    try:
        r = requests.post(GOOGLE_SHEET_API, json=payload, timeout=12)
        return r.json()
    except Exception:
        return {}

def get_user_name(uid: str):
    try:
        return line_bot_api.get_profile(uid).display_name
    except Exception:
        return "時光旅人"

@app.get("/")
def root():
    return {"status": "Online", "service": "Childhood Memory & Reunion Glassmorphism App 2.0"}

@app.get("/mem_photo/{photo_id}")
def serve_memory_photo(photo_id: str):
    img_bytes = MEMORY_PHOTO_CACHE.get(photo_id)
    if not img_bytes:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(content=img_bytes, media_type="image/jpeg")

@app.post("/api/memory_post")
async def web_memory_post(
    category: str = Form("當兵同袍"),
    area: str = Form("台灣某個角落"),
    target: str = Form("兒時玩伴／同梯弟兄"),
    story: str = Form(""),
    author: str = Form("時光旅人"),
    files: list[UploadFile] = File(default=[])
):
    now_t = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
    saved_pid = ""
    for f in files:
        data = await f.read()
        if data:
            pid = f"mem_{int(datetime.datetime.utcnow().timestamp() * 1000)}_{len(MEMORY_PHOTO_CACHE)}"
            MEMORY_PHOTO_CACHE[pid] = data
            if not saved_pid:
                saved_pid = pid

    item = {
        "id": saved_pid,
        "category": category.strip() or "當兵同袍",
        "area": area.strip() or "台灣某個角落",
        "target": target.strip() or "兒時記憶",
        "story": story.strip() or "那段再也回不去的熱血與純真年代...",
        "author": author.strip() or "時光旅人",
        "time": now_t
    }
    MEMORY_WALL_ITEMS.insert(0, item)
    call_sheet({
        "action": "add_memory",
        "user_id": "web_app",
        "user_name": item["author"],
        "category": item["category"],
        "school_area": item["area"],
        "target_name": item["target"],
        "story": item["story"]
    })
    return RedirectResponse(url="/memory_app?posted=1", status_code=303)
@app.get("/memory_app", response_class=HTMLResponse)
def childhood_memory_glass_app(posted: str = ""):
    S = chr(47)
    items_json = json.dumps(MEMORY_WALL_ITEMS, ensure_ascii=False)
    bot_id_enc = urllib.parse.quote(LINE_BOT_BASIC_ID)
    toast_html = '<div class="toast">✨ 您的時光膠囊與尋人啟事已成功封存上牆！</div>' if posted == "1" else ""

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"/>
    <title>🕰️ 時光膠囊 · 兒時記憶與同袍尋人 App</title>
    <style>
      * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
      body {{ margin: 0; padding: 0 0 88px 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif; background: radial-gradient(circle at top right, #2B1E16, #0D0F14 55%); color: #F8F9FA; min-height: 100vh; }}
      .topbar {{ background: rgba(18, 20, 26, 0.85); backdrop-filter: blur(16px); padding: 15px 18px; position: sticky; top: 0; z-index: 100; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 183, 77, 0.22); }}
      .topbar h1 {{ margin: 0; font-size: 16px; font-weight: 800; letter-spacing: 0.5px; color: #FFE8CC; }}
      .badge-gold {{ font-size: 11px; background: linear-gradient(135deg, #F59F00, #E67700); color: #fff; padding: 4px 10px; border-radius: 20px; font-weight: 800; }}
      .wrap {{ max-width: 540px; margin: 0 auto; padding: 14px; }}
      .toast {{ background: rgba(18, 184, 134, 0.22); border: 1px solid #20C997; color: #96F2D7; padding: 12px; border-radius: 14px; font-size: 13px; font-weight: 700; margin-bottom: 12px; text-align: center; }}
      .search-bar {{ width: 100%; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); color: #fff; padding: 12px 16px; border-radius: 16px; font-size: 14px; margin-bottom: 10px; backdrop-filter: blur(10px); }}
      .chips {{ display: flex; gap: 8px; overflow-x: auto; padding-bottom: 12px; scrollbar-width: none; }}
      .chip {{ white-space: nowrap; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: #CED4DA; padding: 8px 14px; border-radius: 20px; font-size: 13px; font-weight: 700; cursor: pointer; }}
      .chip.active {{ background: linear-gradient(135deg, #F59F00, #F76707); border-color: #FFA94D; color: #fff; box-shadow: 0 4px 14px rgba(247, 103, 7, 0.35); }}
      .glass-card {{ background: rgba(26, 29, 38, 0.72); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 22px; padding: 16px; margin-bottom: 14px; box-shadow: 0 10px 28px rgba(0,0,0,0.4); }}
      .tag {{ display: inline-block; font-size: 11px; font-weight: 800; padding: 4px 10px; border-radius: 10px; background: rgba(255, 169, 77, 0.18); color: #FFC078; margin-bottom: 8px; }}
      .mem-img {{ width: 100%; max-height: 280px; object-fit: cover; border-radius: 14px; margin: 10px 0; cursor: zoom-in; border: 1px solid rgba(255,255,255,0.15); }}
      .btn-row {{ display: flex; gap: 8px; margin-top: 12px; }}
      .btn {{ flex: 1; text-align: center; text-decoration: none; padding: 11px 6px; border-radius: 12px; font-size: 13px; font-weight: 800; cursor: pointer; border: none; color: #fff; }}
      .btn-amber {{ background: linear-gradient(135deg, #F59F00, #F76707); }}
      .btn-glass {{ background: rgba(255,255,255,0.1); color: #FFE8CC; border: 1px solid rgba(255,255,255,0.16); }}
      .field {{ width: 100%; background: rgba(13, 15, 20, 0.8); border: 1px solid rgba(255,255,255,0.18); color: #fff; padding: 12px; border-radius: 12px; font-size: 14px; margin-top: 8px; }}
      .page {{ display: none; }}
      .page.active {{ display: block; }}
      .tabbar {{ position: fixed; bottom: 0; left: 0; right: 0; background: rgba(18, 20, 26, 0.92); backdrop-filter: blur(18px); border-top: 1px solid rgba(255,255,255,0.12); display: flex; padding: 8px 10px 14px; z-index: 120; }}
      .tab {{ flex: 1; text-align: center; color: #868E96; font-size: 12px; font-weight: 800; cursor: pointer; }}
      .tab.active {{ color: #FFA94D; }}
      .tab-cta {{ background: linear-gradient(135deg, #F59F00, #F76707); color: #fff; padding: 9px 14px; border-radius: 22px; font-size: 13px; box-shadow: 0 4px 12px rgba(247,103,7,0.4); }}
      #lightbox {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.94); z-index: 300; align-items: center; justify-content: center; }}
      #lightbox img {{ max-width: 94%; max-height: 88%; border-radius: 14px; }}
    </style></head><body>
    <div class="topbar"><h1>🕰️ 時光膠囊 · 尋人與記憶牆</h1><span class="badge-gold">玻璃擬態 Pro</span></div>
    <div id="page-wall" class="page active"><div class="wrap">
      {toast_html}
      <input id="kw-input" class="search-bar" placeholder="🔍 搜尋梯次、營區、國小、住處、同袍名字或故事..." oninput="applyFilter()"/>
      <div class="chips">
        <div class="chip active" onclick="setCat('all', this)">🌟 全部記憶</div>
        <div class="chip" onclick="setCat('當兵同袍', this)">🎖️ 當兵同袍</div>
        <div class="chip" onclick="setCat('尋人啟事', this)">🎓 同學與恩師</div>
        <div class="chip" onclick="setCat('兒時住處', this)">🏠 住處與學校</div>
        <div class="chip" onclick="setCat('感動故事', this)">❤️ 感動故事</div>
      </div>
      <div id="wall-list"></div>
    </div></div>

    <div id="page-post" class="page"><div class="wrap">
      <div class="glass-card">
        <div style="font-size:17px;font-weight:900;color:#FFD43B;margin-bottom:4px;">✍️ 封存兒時記憶 ＆ 發布尋人啟事</div>
        <div style="font-size:12px;color:#ADB5BD;line-height:1.5;">寫下當年的梯次營區、國小班級、老家住處或同袍綽號，讓記憶永遠發光：</div>
        <form action="{S}api{S}memory_post" method="post" enctype="multipart/form-data">
          <select name="category" class="field">
            <option value="當兵同袍">🎖️ 尋找當兵同袍（梯次／營區／連隊）</option>
            <option value="尋人啟事">🎓 尋找兒時同學／恩師／鄰居</option>
            <option value="兒時住處">🏠 兒時住處／學校／舊地重遊</option>
            <option value="感動故事">❤️ 感動人心的童年與軍旅故事</option>
          </select>
          <input name="area" class="field" placeholder="📍 梯次營區／學校／住處（如：成功嶺1852梯 或 五股國小）" required/>
          <input name="target" class="field" placeholder="👤 尋找的人事物（如：尋找同梯大頭／六年三班班長）" required/>
          <textarea name="story" class="field" rows="4" placeholder="📝 寫下那段感動人的故事、共同回憶或特徵線索..." required></textarea>
          <input name="author" class="field" placeholder="✍️ 您的稱呼或當年綽號（選填）"/>
          <label class="btn btn-glass" style="display:block;margin-top:10px;">📸 上傳泛黃老照片／軍旅合照（可多選）<input type="file" name="files" accept="image/*" multiple style="display:none;" onchange="document.getElementById('f-tip').innerText='✅ 已選擇 '+this.files.length+' 張珍貴照片'"/></label>
          <div id="f-tip" style="font-size:12px;color:#63E6BE;margin-top:6px;text-align:center;"></div>
          <button type="submit" class="btn btn-amber" style="width:100%;margin-top:12px;padding:14px;">🚀 立即封存並發布到時光牆</button>
        </form>
      </div>
    </div></div>

    <div class="tabbar">
      <div class="tab active" onclick="switchPage('wall', this)">🕰️ 時光記憶牆</div>
      <div class="tab" onclick="switchPage('post', this)"><span class="tab-cta">➕ 發布尋人／故事</span></div>
    </div>

    <div id="lightbox" onclick="this.style.display='none'"><img id="lb-img" src=""/></div>
    <script>
      const DATA = {items_json};
      let curCat = 'all';
      function setCat(c, el) {{
        curCat = c;
        document.querySelectorAll('.chip').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        applyFilter();
      }}
      function applyFilter() {{
        const kw = document.getElementById('kw-input').value.trim().toLowerCase();
        const filtered = DATA.filter(x => {{
          const okCat = (curCat === 'all') || (x.category === curCat);
          const okKw = !kw || (x.area + x.target + x.story + x.category).toLowerCase().includes(kw);
          return okCat && okKw;
        }});
        const box = document.getElementById('wall-list');
        if (!filtered.length) {{
          box.innerHTML = '<div class="glass-card" style="text-align:center;color:#ADB5BD;">目前沒有符合的記憶，點擊下方「➕ 發布尋人／故事」成為第一位時光旅人！</div>';
          return;
        }}
        box.innerHTML = filtered.map(x => {{
          const imgHtml = x.id ? `<img class="mem-img" src="{S}mem_photo{S}${{x.id}}" onclick="openLb('{S}mem_photo{S}${{x.id}}')"/>` : '';
          const mapU = `https:{S}{S}://google.com{S}?q=${{encodeURIComponent(x.area)}}`;
          const clueU = `https:{S}{S}line.me{S}R{S}oaMessage{S}{bot_id_enc}{S}?${{encodeURIComponent('提供線索:' + x.target + ' -> ')}}`;
          return `<div class="glass-card">
            <span class="tag">${{x.category}} · ${{x.area}}</span>
            <div style="font-size:17px;font-weight:900;color:#fff;">${{x.target}}</div>
            ${{imgHtml}}
            <div style="font-size:14px;color:#E9ECEF;line-height:1.65;margin-top:8px;">${{x.story}}</div>
            <div style="font-size:11px;color:#868E96;margin-top:8px;">🕰️ ${{x.time}} · 發布者：${{x.author || '時光旅人'}}</div>
            <div class="btn-row">
              <a class="btn btn-glass" href="${{mapU}}" target="_blank">🗺️ 重返舊地街景</a>
              <a class="btn btn-amber" href="${{clueU}}">🤝 我認識／提供線索</a>
            </div>
          </div>`;
        }}).join('');
      }}
      function switchPage(p, el) {{
        document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
        document.getElementById('page-' + p).classList.add('active');
        el.classList.add('active');
        window.scrollTo({{top:0, behavior:'smooth'}});
      }}
      function openLb(src) {{ document.getElementById('lb-img').src = src; document.getElementById('lightbox').style.display = 'flex'; }}
      applyFilter();
    </script></body></html>"""
    return HTMLResponse(content=html)
def make_memory_app_card(total_cnt: int, my_cnt: int):
    S = chr(47)
    app_uri = f"{RENDER_BASE_URL}/memory_app?openExternalBrowser=1"
    army_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('尋同袍:')}"
    school_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('尋同學:')}"
    place_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('舊地重遊:')}"
    story_uri = f"https:{S}{S}line.me{S}R{S}oaMessage{S}{LINE_BOT_BASIC_ID}{S}?{urllib.parse.quote('寫故事:')}"
    share_txt = urllib.parse.quote(f"🕰️【時光膠囊 · 尋找兒時記憶人事物 ＆ 當兵同袍 App】\n找國小同學、當兵同梯弟兄、重返兒時住處街景、上傳泛黃老照片！\n📲 免費加入一起找回青春記憶：\nhttps:{S}{S}line.me{S}R{S}ti{S}p{S}{LINE_BOT_BASIC_ID}")
    share_uri = f"https:{S}{S}line.me{S}R{S}share?text={share_txt}"

    latest_lines = []
    for idx, it in enumerate(MEMORY_WALL_ITEMS[:3], 1):
        latest_lines.append(f"• [{it['category']}] {it['area']}\n  🔍 {it['target']}")
    wall_preview = "\n".join(latest_lines) if latest_lines else "（快來封存第一則兒時與軍旅記憶吧！）"

    bubble_1 = BubbleContainer(
        size="mega",
        header=BoxComponent(layout="vertical", background_color="#14161D", padding_all="16px", contents=[
            TextComponent(text="🕰️ 時光膠囊 · 兒時記憶與同袍尋人", weight="bold", size="md", color="#FFE8CC", wrap=True),
            TextComponent(text="找同學、找當兵同梯、老家住處與感動故事", size="xs", color="#FFA94D", weight="bold", wrap=True, margin="xs")
        ]),
        body=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
            BoxComponent(layout="horizontal", spacing="sm", contents=[
                BoxComponent(layout="vertical", background_color="#1A1B1E", corner_radius="12px", padding_all="10px", align_items="center", contents=[
                    TextComponent(text="🌟 全台記憶總數", size="xxs", color="#FFA94D", weight="bold"),
                    TextComponent(text=f"{max(total_cnt, len(MEMORY_WALL_ITEMS))} 則", size="sm", color="#FFFFFF", weight="bold", margin="xs")
                ]),
                BoxComponent(layout="vertical", background_color="#1A1B1E", corner_radius="12px", padding_all="10px", align_items="center", contents=[
                    TextComponent(text="✍️ 我封存的記憶", size="xxs", color="#63E6BE", weight="bold"),
                    TextComponent(text=f"{my_cnt} 則", size="sm", color="#FFFFFF", weight="bold", margin="xs")
                ])
            ]),
            BoxComponent(layout="vertical", background_color="#FFF9DB", corner_radius="14px", padding_all="12px", contents=[
                TextComponent(text="📜 最新時光牆尋人動態：", size="xs", color="#E67700", weight="bold"),
                TextComponent(text=wall_preview, size="xs", color="#212529", wrap=True, margin="xs")
            ])
        ]),
        footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
            ButtonComponent(style="primary", color="#F76707", height="sm", action=URIAction(label="✨ 開啟全螢幕玻璃擬態時光牆 App", uri=app_uri)),
            BoxComponent(layout="horizontal", spacing="sm", contents=[
                ButtonComponent(style="primary", color="#1A1B1E", height="sm", action=URIAction(label="🎖️ 找當兵同袍", uri=army_uri)),
                ButtonComponent(style="secondary", height="sm", action=URIAction(label="🎓 找同學恩師", uri=school_uri))
            ]),
            BoxComponent(layout="horizontal", spacing="sm", contents=[
                ButtonComponent(style="secondary", height="sm", action=URIAction(label="🏠 舊地重遊", uri=place_uri)),
                ButtonComponent(style="primary", color="#12B886", height="sm", action=URIAction(label="❤️ 寫感動故事", uri=story_uri))
            ])
        ])
    )

    tools_btns = [
        BoxComponent(layout="horizontal", spacing="sm", contents=[
            ButtonComponent(style="primary", color="#F76707", height="sm", action=MessageAction(label="🎲 懷舊時光機抽卡", text="懷舊抽卡")),
            ButtonComponent(style="secondary", height="sm", action=URIAction(label="📸 上傳老照片", uri=app_uri))
        ]),
        BoxComponent(layout="horizontal", spacing="sm", contents=[
            ButtonComponent(style="secondary", height="sm", action=URIAction(label="🎖️ 登錄梯次營區", uri=army_uri)),
            ButtonComponent(style="secondary", height="sm", action=URIAction(label="🏫 登錄母校班級", uri=school_uri))
        ]),
        ButtonComponent(style="primary", color="#228BE6", height="sm", action=URIAction(label="📤 轉傳同學會／軍旅群組一起尋人", uri=share_uri))
    ]
    if NOTION_RETRO_SHOP_URL.startswith("http"):
        tools_btns.append(ButtonComponent(style="secondary", height="sm", action=URIAction(label="🍬 台灣懷舊零食／紅白機嚴選館", uri=NOTION_RETRO_SHOP_URL)))

    bubble_2 = BubbleContainer(
        size="mega",
        header=BoxComponent(layout="vertical", background_color="#14161D", padding_all="16px", contents=[
            TextComponent(text="🎲 童年懷舊百寶箱 ＆ 群組尋人", weight="bold", size="md", color="#FFE8CC", wrap=True),
            TextComponent(text="70～90年代回憶抽卡、老照片上傳、一鍵轉傳", size="xs", color="#63E6BE", weight="bold", wrap=True, margin="xs")
        ]),
        body=BoxComponent(layout="vertical", spacing="xs", background_color="#FFFFFF", contents=[
            TextComponent(text="👈 向左滑動返回「時光記憶牆主畫面」", size="xxs", color="#868E96", weight="bold")
        ]),
        footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=tools_btns)
    )
    return CarouselContainer(contents=[bubble_1, bubble_2])
@app.post("/callback")
async def callback(request: Request):
    sig = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), sig)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"

@handler.add(FollowEvent)
def on_follow(event):
    uid = event.source.user_id
    uname = get_user_name(uid)
    st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
    card = make_memory_app_card(st.get("total_count", 3), st.get("my_count", 0))
    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="時光膠囊 · 兒時記憶與同袍尋人 App 已啟動", contents=card))

@handler.add(MessageEvent, message=ImageMessage)
def on_image(event):
    uid = event.source.user_id
    uname = get_user_name(uid)
    try:
        msg_content = line_bot_api.get_message_content(event.message.id)
        img_bytes = b"".join(chunk for chunk in msg_content.iter_content())
        pid = f"line_{int(datetime.datetime.utcnow().timestamp() * 1000)}_{len(MEMORY_PHOTO_CACHE)}"
        MEMORY_PHOTO_CACHE[pid] = img_bytes
        now_t = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
        MEMORY_WALL_ITEMS.insert(0, {
            "id": pid,
            "category": "感動故事",
            "area": "LINE 珍貴老照片上傳",
            "target": f"{uname} 分享的泛黃記憶照片",
            "story": "這張照片承載著最珍貴的童年與青春時光，歡迎認識的朋友一起來相認！",
            "author": uname,
            "time": now_t
        })
        app_uri = f"{RENDER_BASE_URL}/memory_app?openExternalBrowser=1"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📸 已將您的珍貴老照片封存到「全螢幕玻璃擬態時光牆」囉！\n點擊下方網址立即欣賞與補充文字故事：\n{app_uri}"))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📸 照片已收到！小提示：{str(e)[:60]}"))

@handler.add(MessageEvent, message=LocationMessage)
def on_location(event):
    S = chr(47)
    addr = event.message.address or f"({round(event.message.latitude, 4)}, {round(event.message.longitude, 4)})"
    host = "maps." + "google.com"
    map_u = f"https:{S}{S}{host}{S}?q={urllib.parse.quote(addr)}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🏠 已為您定位兒時記憶地標：【{addr}】\n點擊開啟現代街景對照，看看小時候常去的街角現在變成什麼樣子了：\n{map_u}"))

@handler.add(MessageEvent, message=TextMessage)
def on_text(event):
    uid = event.source.user_id
    uname = get_user_name(uid)
    txt = event.message.text.strip()

    try:
        # 1. 尋找當兵同袍（格式：尋同袍:成功嶺1852梯 找班長大頭）
        if txt.startswith("尋同袍:") or txt.startswith("尋同袍："):
            raw = txt[4:].strip()
            if not raw:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🎖️ 請在「尋同袍:」後面輸入梯次、營區與同袍名字喔！\n例如：尋同袍:成功嶺1852梯三連 尋找同梯大頭與陳班長"))
                return
            parts = raw.split(" ", 1)
            area_str = parts.pop(0)
            target_str = parts.pop(0) if parts else "尋找當年同梯弟兄與長官"
            now_t = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
            MEMORY_WALL_ITEMS.insert(0, {"id": "", "category": "當兵同袍", "area": area_str, "target": target_str, "story": f"當年一起在【{area_str}】流汗操課的同梯弟兄們，退伍多年好想再聚聚！", "author": uname, "time": now_t})
            call_sheet({"action": "add_memory", "user_id": uid, "user_name": uname, "category": "當兵同袍", "school_area": area_str, "target_name": target_str, "story": raw})
            app_uri = f"{RENDER_BASE_URL}/memory_app?openExternalBrowser=1"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎖️ 已為您發布「軍旅同袍尋人啟事」！\n• 梯次營區：{area_str}\n• 尋找對象：{target_str}\n✨ 立即在全螢幕玻璃擬態時光牆查看：\n{app_uri}"))
            return

        # 2. 尋找兒時同學／恩師（格式：尋同學:五股國小1998屆 尋找六年三班陳小明）
        if txt.startswith("尋同學:") or txt.startswith("尋同學："):
            raw = txt[4:].strip()
            if not raw:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🎓 請在「尋同學:」後面輸入學校年份與同學名字喔！\n例如：尋同學:五股國小1998屆 尋找六年三班陳小明"))
                return
            parts = raw.split(" ", 1)
            area_str = parts.pop(0)
            target_str = parts.pop(0) if parts else "尋找當年同班同學與恩師"
            now_t = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
            MEMORY_WALL_ITEMS.insert(0, {"id": "", "category": "尋人啟事", "area": area_str, "target": target_str, "story": f"還記得在【{area_str}】一起下課衝操場的純真時光嗎？希望找回失聯的同學！", "author": uname, "time": now_t})
            call_sheet({"action": "add_memory", "user_id": uid, "user_name": uname, "category": "尋人啟事", "school_area": area_str, "target_name": target_str, "story": raw})
            app_uri = f"{RENDER_BASE_URL}/memory_app?openExternalBrowser=1"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎓 已為您發布「同窗／恩師尋人啟事」！\n• 母校屆別：{area_str}\n• 尋找對象：{target_str}\n✨ 立即在全螢幕玻璃擬態時光牆查看：\n{app_uri}"))
            return
        # 3. 兒時住處／學校舊地重遊（格式：舊地重遊:新北市五股區成泰路）
        if txt.startswith("舊地重遊:") or txt.startswith("舊地重遊："):
            S = chr(47)
            place = txt[5:].strip()
            if not place:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🏠 請在「舊地重遊:」後面輸入小時候的住處、學校或營區地名喔！\n例如：舊地重遊:新北市五股區五股國小"))
                return
            now_t = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
            MEMORY_WALL_ITEMS.insert(0, {"id": "", "category": "兒時住處", "area": place, "target": f"重返童年記憶地標：{place}", "story": f"好想再回去看看【{place}】現在的模樣，那些在街角奔跑的下午彷彿就在昨天。", "author": uname, "time": now_t})
            call_sheet({"action": "add_memory", "user_id": uid, "user_name": uname, "category": "兒時住處", "school_area": place, "target_name": place, "story": f"舊地重遊：{place}"})
            host = "maps." + "google.com"
            map_u = f"https:{S}{S}{host}{S}?q={urllib.parse.quote(place)}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🏠 已將【{place}】收錄至兒時住處記憶牆！\n🗺️ 點擊下方連結立即開啟現代街景對照：\n{map_u}"))
            return

        # 4. 封存感動人心的故事（格式：寫故事:那年夏天外婆騎腳踏車載我...）
        if txt.startswith("寫故事:") or txt.startswith("寫故事："):
            story_txt = txt[4:].strip()
            if not story_txt:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❤️ 請在「寫故事:」後面寫下那段感動您的童年或軍旅回憶喔！"))
                return
            now_t = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M")
            MEMORY_WALL_ITEMS.insert(0, {"id": "", "category": "感動故事", "area": "珍貴人生記憶", "target": f"{uname} 的時光故事", "story": story_txt, "author": uname, "time": now_t})
            call_sheet({"action": "add_memory", "user_id": uid, "user_name": uname, "category": "感動故事", "school_area": "珍貴人生記憶", "target_name": f"{uname} 的時光故事", "story": story_txt})
            app_uri = f"{RENDER_BASE_URL}/memory_app?openExternalBrowser=1"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❤️ 您的感動故事已永久封存到時光牆！\n✨ 立即前往全螢幕玻璃擬態時光牆欣賞：\n{app_uri}"))
            return

        # 5. 同梯弟兄／同班同學提供線索認領（格式：提供線索:尋找同梯大頭 -> 我也是1852梯三連的！）
        if txt.startswith("提供線索:") or txt.startswith("提供線索："):
            clue_txt = txt[5:].strip()
            call_sheet({"action": "add_clue", "user_id": uid, "user_name": uname, "clue_text": clue_txt})
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🤝 感謝熱心相認！您的線索「{clue_txt}」已成功送達時光資料庫，系統已為您登記為熱心線索提供者！"))
            return

        # 6. 70～90 年代懷舊時光機抽卡
        if txt in ["懷舊抽卡", "時光機", "抽卡"]:
            title, desc = random.choice(NOSTALGIA_CARDS)
            retro_card = BubbleContainer(
                size="mega",
                header=BoxComponent(layout="vertical", background_color="#14161D", padding_all="14px", contents=[
                    TextComponent(text="🎲 70～90年代懷舊時光機抽卡", weight="bold", size="md", color="#FFE8CC", wrap=True)
                ]),
                body=BoxComponent(layout="vertical", spacing="sm", background_color="#FFF9DB", contents=[
                    TextComponent(text=title, size="md", weight="bold", color="#E67700", wrap=True),
                    TextComponent(text=desc, size="xs", color="#212529", wrap=True)
                ]),
                footer=BoxComponent(layout="vertical", spacing="sm", background_color="#FFFFFF", contents=[
                    ButtonComponent(style="primary", color="#F76707", height="sm", action=MessageAction(label="🎲 再抽一張童年回憶", text="懷舊抽卡")),
                    ButtonComponent(style="secondary", height="sm", action=MessageAction(label="📊 返回時光記憶牆主畫面", text="時光牆"))
                ])
            )
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"懷舊抽卡：{title}", contents=retro_card))
            return

        # 7. 預設顯示暗夜琥珀流光雙卡輪播主畫面
        st = call_sheet({"action": "status", "user_id": uid, "user_name": uname})
        card = make_memory_app_card(st.get("total_count", len(MEMORY_WALL_ITEMS)), st.get("my_count", 0))
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="時光膠囊 · 兒時記憶與同袍尋人 App", contents=card))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🕰️ 系統小提示：{str(e)[:60]}（請輸入「時光牆」刷新畫面）"))
