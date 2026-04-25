import os
import yfinance as yf
import pandas as pd
import asyncio
import matplotlib.pyplot as plt
import io
import warnings
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime

# 1. 門牌伺服器 (保持 Render 醒著)
def run_dummy_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"NeoTycoon is Awake!")
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        server.serve_forever()
    except: pass

threading.Thread(target=run_dummy_server, daemon=True).start()

# 2. 畫圖功能
def generate_custom_chart(df, symbol):
    try:
        plt.figure(figsize=(10, 5))
        plt.style.use('bmh') 
        plt.plot(df.index, df['Close'], color='#1E77E4', linewidth=2)
        plt.title(f"{symbol} Trend")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
    except: return None

# 3. 核心分析
def get_detailed_analysis(symbol):
    try:
        original_input = symbol.upper()
        if original_input == "BTC": symbol = "BTC-USD"
        symbol = symbol.upper()
        
        # ⭐ 關鍵修正：讓 yfinance 自己處理通訊
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        
        if df.empty: return f"❌ 找不到 {symbol}", None, None

        # ⭐ 重要：過濾特殊字元，防止 Telegram HTML 解析錯誤
        raw_name = ticker.info.get('shortName') or symbol
        name = str(raw_name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        curr_price = df['Close'].iloc[-1]
        is_tw = ".TW" in symbol
        p_usd = curr_price if not is_tw else curr_price / 32
        p_twd = curr_price * 32 if not is_tw else curr_price

        # 計算報酬率
        data_len = len(df)
        idx_252 = min(252, data_len - 1)
        ret_2025 = ((df['Close'].iloc[-1] / df['Close'].iloc[-idx_252]) - 1) * 100
        ret_2024 = ((df['Close'].iloc[-idx_252] / df['Close'].iloc[-min(504, data_len-1)]) - 1) * 100 if data_len > 252 else 0

        # 計算均線策略
        df['SMA60'] = df['Close'].rolling(window=60).mean()
        df['SMA240'] = df['Close'].rolling(window=240).mean()
        l60, l240 = df['SMA60'].iloc[-1], df['SMA240'].iloc[-1]

        if curr_price > l60 and l60 > l240: 
            status, advice = "✅ 要持有", "多頭排列強勢，建議抱緊"
            forecast = "+10% ~ +25%"
        elif curr_price > l240: 
            status, advice = "🟡 觀察", "季線附近震盪，暫不追高"
            forecast = "-5% ~ +5%"
        else: 
            status, advice = "❌ 賣出", "趨勢轉空，建議減碼"
            forecast = "-10% ~ +2%"
            
        # ⭐ 最終排版：台幣下移、增加對齊感
        report = (
            f"💰 <b>【NeoTycoon 報告】</b>\n"
            f"---------------------------\n"
            f"名稱：{name}\n"
            f"美金：${p_usd:,.2f}\n"
            f"台幣：NT${p_twd:,.0f}\n"
            f"2025 報酬：{ret_2025:+.2f}%\n"
            f"2024 報酬：{ret_2024:+.2f}%\n"
            f"未來一年預計：{forecast}\n"
            f"---------------------------\n"
            f"持有建議：<b>{status}</b>\n"
            f"具體行動：{advice}\n"
            f"---------------------------\n"
            f"詳細點下面連結自己看👇( ｡•̀_•́｡)👇"
        )
        
        clean_sym = symbol.replace(".TW", "").replace("-USD", "")
        keyboard = [[InlineKeyboardButton("TradingView", url=f"https://www.tradingview.com/symbols/{clean_sym}/")],
                    [InlineKeyboardButton("Investopedia", url=f"https://www.investopedia.com/search?q={clean_sym}")],
                    [InlineKeyboardButton("Yahoo Finance", url=f"https://finance.yahoo.com/quote/{symbol}")]]

        img = generate_custom_chart(df, symbol) if (is_tw or original_input == "BTC") else f"https://charts2.finviz.com/chart.ashx?t={clean_sym}&ty=c&ta=1&p=d"
        return report, InlineKeyboardMarkup(keyboard), img
    except Exception as e: return f"⚠️ 分析錯誤：{e}", None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    if not text.lower().startswith("@nt"): return
    cmd = text[3:].strip()
    
    if cmd in ["你好", "哈囉", "hi"]:
        await update.message.reply_text("👋( ´ ▽ ` )嗨")
        return
    if cmd == "建議":
        top_list = ["NVDA", "2330.TW", "TSLA", "META", "2317.TW", "AAPL", "MSFT", "AMD", "AMZN", "2454.TW"]
        list_text = "\n".join([f"{i+1}. <b>{code}</b>" for i, code in enumerate(top_list)])
        rec = (
            f"🏆 <b>【NeoTycoon 策略推薦】</b>\n"
            f"---------------------------\n"
            f"{list_text}\n"
            f"---------------------------\n"
            f"💡 輸入 <code>@nt 代號</code> 即可分析"
        )
        await update.message.reply_text(rec, parse_mode='HTML')
        return
        
    wait_msg = await update.message.reply_text(f"🔍 正在通靈 {cmd}...")
    msg, markup, img = get_detailed_analysis(cmd)
    
    try:
        if img: await update.message.reply_photo(photo=img, caption=msg, reply_markup=markup, parse_mode='HTML')
        else: await update.message.reply_text(msg, reply_markup=markup, parse_mode='HTML')
    except:
        try:
            if img: await update.message.reply_photo(photo=img, caption=msg, reply_markup=markup)
            else: await update.message.reply_text(msg, reply_markup=markup)
        except Exception as final_e:
            await update.message.reply_text(f"❌ 傳送最終失敗：{final_e}")
            
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

# 4. 設定 Bot Menu 選單的功能函式
async def set_bot_menu(application):
    commands = [
        ("start", "🚀 啟動 NeoTycoon"),
        ("suggest", "🏆 查看推薦名單"),
        ("help", "❓ 使用說明")
    ]
    await application.bot.set_my_commands(commands)
    print("✅ Bot Menu 選單設定成功！")

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if TOKEN:
        # 初始化機器人
        app = ApplicationBuilder().token(TOKEN).build()
        
        # ⭐ 關鍵：啟動時同步執行「選單設定」
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(set_bot_menu(app))
            else:
                loop.run_until_complete(set_bot_menu(app))
        except:
            pass

        # 原有的訊息處理器
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        # 開始運行
        print("🚀 NeoTycoon 正在運行中...")
        app.run_polling()