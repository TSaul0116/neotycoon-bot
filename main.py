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

# --- 💎 核心修復：騙過 Render 的「門牌」系統 ---
def run_dummy_server():
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"NeoTycoon is Live!")
    
    # 這裡會讀取 Render 分配的 Port，如果沒有就用 8080
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"✅ 門牌伺服器已啟動於 Port {port}")
    server.serve_forever()

# --- 基礎設定 ---
warnings.filterwarnings("ignore")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "6419138408")

def generate_custom_chart(df, symbol):
    """畫出大表哥風格的趨勢圖"""
    try:
        plt.figure(figsize=(10, 5))
        plt.style.use('bmh') 
        plt.plot(df.index, df['Close'], color='#1E77E4', linewidth=2, label='Price')
        low_val = df['Close'].min()
        plt.axhspan(low_val, low_val * 1.05, color='green', alpha=0.15)
        plt.title(f"{symbol} Trend Analysis", fontsize=14)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
    except Exception as e:
        print(f"⚠️ 畫圖出錯: {e}")
        return None

def get_detailed_analysis(symbol):
    try:
        original_input = symbol.upper()
        if original_input == "BTC": symbol = "BTC-USD"
        
        symbol = symbol.upper()
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        if df.empty: return f"❌ 找不到 {symbol}", None, None

        info = ticker.info
        name = info.get('shortName') or info.get('longName') or symbol
        curr_price = df['Close'].iloc[-1]
        
        is_tw = ".TW" in symbol
        p_usd = curr_price if not is_tw else curr_price / 32
        p_twd = curr_price * 32 if not is_tw else curr_price

        # 13勝策略邏輯 (季線/年線判斷)
        df['SMA60'] = df['Close'].rolling(window=60).mean()
        df['SMA240'] = df['Close'].rolling(window=240).mean()
        last_60 = df['SMA60'].iloc[-1]
        last_240 = df['SMA240'].iloc[-1]

        if curr_price > last_60 and last_60 > last_240:
            status, advice, t_advice = "✅ 要持有", "多頭排列強勢，建議抱緊", "6-12個月"
        elif curr_price > last_240:
            status, advice, t_advice = "🟡 觀察", "季線附近震盪，暫不追高", "短期觀望"
        else:
            status, advice, t_advice = "❌ 賣出", "趨勢轉空，建議減碼", "立即離場"

        report = (
            f"💰 <b>【NeoTycoon 報告】</b>\n"
            f"---------------------------\n"
            f"名稱：{name} ({symbol})\n"
            f"美金價格：${p_usd:,.2f}\n"
            f"台幣價格：NT${p_twd:,.2f}\n"
            f"---------------------------\n"
            f"持有建議：{status}\n"
            f"具體行動：{advice}\n"
            f"---------------------------\n"
            f"詳細點下面連結自己看👇( ｡•̀_•́｡)👇"
        )
        
        clean_sym = symbol.replace(".TW", "").replace("-USD", "")
        keyboard = [
            [InlineKeyboardButton("TradingView 圖表", url=f"https://www.tradingview.com/symbols/{clean_sym}/")],
            [InlineKeyboardButton("Yahoo 商品代號查詢", url=f"https://finance.yahoo.com/quote/{symbol}")]
        ]

        # 判斷要抓 Finviz 帥圖還是自己畫
        if is_tw or original_input == "BTC":
            img = generate_custom_chart(df, symbol)
        else:
            img = f"https://charts2.finviz.com/chart.ashx?t={clean_sym}&ty=c&ta=1&p=d"

        return report, InlineKeyboardMarkup(keyboard), img

    except Exception as e:
        return f"⚠️ 錯誤：{e}", None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    if not text.lower().startswith("@nt"): return
    cmd = text[3:].strip()
    
    if cmd:
        wait_msg = await update.message.reply_text(f"🔍 正在通靈 {cmd}...")
        msg, markup, img = get_detailed_analysis(cmd)
        if img:
            await update.message.reply_photo(photo=img, caption=msg, reply_markup=markup, parse_mode='HTML')
        else:
            await update.message.reply_text(msg, reply_markup=markup, parse_mode='HTML')
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

if __name__ == "__main__":
    # 🌟 重點：先啟動假門牌，再啟動機器人
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 機器人通靈中...")
    app.run_polling()