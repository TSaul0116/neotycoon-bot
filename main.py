import os
import yfinance as yf
import pandas as pd
import asyncio
import matplotlib.pyplot as plt
import io
import warnings
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime

# --- 1. 門牌伺服器 (解決 Render 30 秒斷線問題) ---
def run_dummy_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"NeoTycoon is Live!")
    
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"✅ 門牌伺服器已啟動於 Port {port}")
    server.serve_forever()

# 背景啟動門牌系統
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- 2. 基礎設定 ---
warnings.filterwarnings("ignore")
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- 3. 畫圖功能 (WTI 風格) ---
def generate_custom_chart(df, symbol):
    try:
        plt.figure(figsize=(10, 5))
        plt.style.use('bmh') 
        plt.plot(df.index, df['Close'], color='#1E77E4', linewidth=2)
        plt.title(f"{symbol} Trend Analysis")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
    except:
        return None

# --- 4. 核心分析功能 (13勝策略 + 報酬計算) ---
def get_detailed_analysis(symbol):
    try:
        original_input = symbol.upper()
        if original_input == "BTC": symbol = "BTC-USD"
        
        symbol = symbol.upper()
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        
        if df.empty:
            return f"❌ 找不到 {symbol}，請檢查代碼是否正確 (例如 2330.TW)", None, None

        info = ticker.info
        name = info.get('shortName') or info.get('longName') or symbol
        curr_price = df['Close'].iloc[-1]
        
        is_tw = ".TW" in symbol
        p_usd = curr_price if not is_tw else curr_price / 32
        p_twd = curr_price * 32 if not is_tw else curr_price

        # 計算 2025 與 2024 年化報酬率
        data_len = len(df)
        idx_2025 = min(252, data_len - 1)
        ret_2025 = ((df['Close'].iloc[-1] / df['Close'].iloc[-idx_2025]) - 1) * 100 if data_len > 1 else 0
        ret_2024 = ((df['Close'].iloc[-idx_2025] / df['Close'].iloc[-min(504, data_len)]) - 1) * 100 if data_len > 252 else 0

        # --- 13勝策略邏輯 ---
        df['SMA60'] = df['Close'].rolling(window=60).mean()
        df['SMA240'] = df['Close'].rolling(window=240).mean()
        last_60 = df['SMA60'].iloc[-1]
        last_240 = df['SMA240'].iloc[-1]

        if curr_price > last_60 and last_60 > last_240:
            status, advice, est = "✅ 要持有", "多頭排列強勢，建議抱緊", "15%~25%"
        elif curr_price > last_240:
            status, advice, est = "🟡 觀察", "季線附近震盪，暫不追高", "5%~10%"
        else:
            status, advice, est = "❌ 賣出", "趨勢轉空，建議減碼", "-5%~2%"

        # --- 組合報告內容 ---
        report = (
            f"💰 <b>【NeoTycoon 報告】</b>\n"
            f"---------------------------\n"
            f"名稱：{name} ({symbol})\n"
            f"美金：${p_usd:,.2f} / 台幣：NT${p_twd:,.2f}\n"
            f"2025 報酬：{ret_2025:+.2f}%\n"
            f"2024 報酬：{ret_2024:+.2f}%\n"
            f"未來一年預計：{est}\n"
            f"---------------------------\n"
            f"持有建議：{status}\n"
            f"具體行動：{advice}\n"
            f"---------------------------\n"
            f"詳細點下面連結自己看👇( ｡•̀_•́｡)👇"
        )
        
        clean_sym = symbol.replace(".TW", "").replace("-USD", "")
        
        # 三個核心連結按鈕
        keyboard = [
            [InlineKeyboardButton("TradingView 圖表", url=f"https://www.tradingview.com/symbols/{clean_sym}/")],
            [InlineKeyboardButton("Investopedia 知識", url=f"https://www.investopedia.com/search?q={clean_sym}")],
            [InlineKeyboardButton("Yahoo 商品代號", url=f"https://finance.yahoo.com/quote/{symbol}")]
        ]

        # 判斷要用自繪圖還是 Finviz 帥圖
        if is_tw or original_input == "BTC":
            img = generate_custom_chart(df, symbol)
        else:
            img = f"https://charts2.finviz.com/chart.ashx?t={clean_sym}&ty=c&ta=1&p=d"

        return report, InlineKeyboardMarkup(keyboard), img

    except Exception as e:
        return f"⚠️ 錯誤：{e}", None, None

# --- 5. 訊息處理器 ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    
    # 指令必須以 @nt 開頭
    if not text.lower().startswith("@nt"): return
    cmd = text[3:].strip()
    
    # 💎 哈囉功能
    if cmd in ["你好", "哈囉", "hi", "hello", "你好啊"]:
        await update.message.reply_text("👋( ´ ▽ ` )嗨")
        return

    # 💎 推薦清單
    if cmd == "建議":
        rec = "🏆 <b>【NT 策略推薦 TOP 10】</b>\n\n1. NVDA\n2. 2330.TW\n3. TSLA\n4. META\n5. 2317.TW\n6. AAPL\n7. MSFT\n8. AMD\n9. AMZN\n10. 2454.TW"
        await update.message.reply_text(rec, parse_mode='HTML') 
        return

    # 💎 股票分析
    if cmd:
        wait_msg = await update.message.reply_text(f"🔍 正在通靈 {cmd}...")
        msg, markup, img = get_detailed_analysis(cmd)
        
        try:
            if img:
                await update.message.reply_photo(photo=img, caption=msg, reply_markup=markup, parse_mode='HTML')
            else:
                await update.message.reply_text(msg, reply_markup=markup, parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ 傳送失敗: {e}")
            
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

# --- 6. 啟動機器人 ---
if __name__ == "__main__":
    if not TOKEN:
        print("❌ 錯誤：找不到 TELEGRAM_TOKEN，請檢查 Render 環境變數設定。")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        print("🚀 機器人通靈中...")
        app.run_polling()