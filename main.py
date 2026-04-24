import os
import yfinance as yf
import pandas as pd
import asyncio
import matplotlib.pyplot as plt
import io
import warnings
import threading
import requests  # 👈 就是這個！防封鎖的重要工具
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime

# ==========================================
# 1. 門牌伺服器 (給 Cron-job 敲門用的)
# ==========================================
def run_dummy_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"NeoTycoon is Awake!")
    
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        print(f"✅ 門牌伺服器成功啟動於 Port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"⚠️ 門牌啟動異常: {e}")

# 在背景默默啟動門牌
threading.Thread(target=run_dummy_server, daemon=True).start()

# ==========================================
# 2. 畫圖功能 (台股與比特幣專用)
# ==========================================
def generate_custom_chart(df, symbol):
    try:
        plt.figure(figsize=(10, 5))
        plt.style.use('bmh') 
        plt.plot(df.index, df['Close'], color='#1E77E4', linewidth=2)
        plt.title(f"{symbol} Trend Analysis", fontsize=14)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
    except:
        return None

# ==========================================
# 3. 核心分析大腦 (防封鎖面具 + 13勝策略)
# ==========================================
def get_detailed_analysis(symbol):
    try:
        original_input = symbol.upper()
        if original_input == "BTC": symbol = "BTC-USD"
        symbol = symbol.upper()
        
        # 戴上面具：偽裝成正常的電腦瀏覽器
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': '*/*'
        })
        
        ticker = yf.Ticker(symbol, session=session)
        df = ticker.history(period="3y")
        
        if df.empty: 
            return f"❌ 找不到 {symbol} 的資料，請確認代號是否正確。", None, None

        info = ticker.info
        name = info.get('shortName') or symbol
        curr_price = df['Close'].iloc[-1]
        
        is_tw = ".TW" in symbol
        p_usd = curr_price if not is_tw else curr_price / 32
        p_twd = curr_price * 32 if not is_tw else curr_price

        # 計算報酬率
        data_len = len(df)
        idx_252 = min(252, data_len - 1)
        ret_2025 = ((df['Close'].iloc[-1] / df['Close'].iloc[-idx_252]) - 1) * 100 if data_len > 1 else 0
        ret_2024 = ((df['Close'].iloc[-idx_252] / df['Close'].iloc[-min(504, data_len-1)]) - 1) * 100 if data_len > 252 else 0

        # 計算 13 勝策略
        df['SMA60'] = df['Close'].rolling(window=60).mean()
        df['SMA240'] = df['Close'].rolling(window=240).mean()
        l60 = df['SMA60'].iloc[-1]
        l240 = df['SMA240'].iloc[-1]

        if curr_price > l60 and l60 > l240:
            status, advice, est = "✅ 要持有", "多頭排列強勢，建議抱緊", "15%~25%"
        elif curr_price > l240:
            status, advice, est = "🟡 觀察", "季線附近震盪，暫不追高", "5%~10%"
        else:
            status, advice, est = "❌ 賣出", "趨勢轉空，建議減碼", "-5%~2%"
            
        # 產生報告 (對齊好，保證印得出來)
        report = (
            f"💰 <b>【NeoTycoon 報告】</b>\n"
            f"---------------------------\n"
            f"名稱：{name} ({symbol})\n"
            f"價格：美金 ${p_usd:,.2f} / 台幣 NT${p_twd:,.2f}\n"
            f"2025 報酬：{ret_2025:+.2f}%\n"
            f"2024 報酬：{ret_2024:+.2f}%\n"
            f"持有建議：{status}\n"
            f"具體行動：{advice}\n"
            f"---------------------------\n"
            f"詳細點下面連結看👇( ｡•̀_•́｡)👇"
        )
        
        clean_sym = symbol.replace(".TW", "").replace("-USD", "")
        keyboard = [
            [InlineKeyboardButton("TradingView 圖表", url=f"https://www.tradingview.com/symbols/{clean_sym}/")],
            [InlineKeyboardButton("Investopedia 知識", url=f"https://www.investopedia.com/search?q={clean_sym}")],
            [InlineKeyboardButton("Yahoo Finance", url=f"https://finance.yahoo.com/quote/{symbol}")]
        ]

        if is_tw or original_input == "BTC":
            img = generate_custom_chart(df, symbol)
        else:
            img = f"https://charts2.finviz.com/chart.ashx?t={clean_sym}&ty=c&ta=1&p=d"
            
        return report, InlineKeyboardMarkup(keyboard), img

    except Exception as e: 
        return f"⚠️ 分析時發生錯誤：{e}", None, None

# ==========================================
# 4. 接收器
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    
    if not text.lower().startswith("@nt"): return
    cmd = text[3:].strip()
    
    if cmd in ["你好", "哈囉", "hi", "hello"]:
        await update.message.reply_text("👋( ´ ▽ ` )嗨")
        return
        
    if cmd == "建議":
        rec = "🏆 <b>【NT 策略推薦 TOP 10】</b>\n\n1. NVDA\n2. 2330.TW\n3. TSLA\n4. META\n5. 2317.TW\n6. AAPL\n7. MSFT\n8. AMD\n9. AMZN\n10. 2454.TW"
        await update.message.reply_text(rec, parse_mode='HTML') 
        return

    wait_msg = await update.message.reply_text(f"🔍 正在幫你查 {cmd}，稍等一下...")
    msg, markup, img = get_detailed_analysis(cmd)
    
    try:
        if img:
            await update.message.reply_photo(photo=img, caption=msg, reply_markup=markup, parse_mode='HTML')
        else:
            await update.message.reply_text(msg, reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ 傳送失敗: {e}")
        
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

# ==========================================
# 5. 啟動開關
# ==========================================
if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    if not TOKEN:
        print("🚨 找不到 TELEGRAM_TOKEN！請回 Render 檢查設定。")
    else:
        print("🚀 Token 讀取成功！機器人開始運作...")
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        app.run_polling()