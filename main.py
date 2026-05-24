import os
import yfinance as yf
import pandas as pd
import asyncio
import matplotlib.pyplot as plt
import io
import warnings
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta

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

# 3. 核心分析 (回歸最初版：全部單純走 yfinance，加上防斷線重試機制)
def get_detailed_analysis(symbol):
    try:
        original_input = symbol.upper().strip()
        
        # 自動代號校正
        if original_input == "BTC": original_input = "BTC-USD"
        if original_input == "SNP": original_input = "SPY"
        
        symbol = original_input
        is_tw = ".TW" in symbol
        df = pd.DataFrame()
        name = symbol  
        
        # 使用最初版 yfinance 機制，加上重試防線
        ticker = yf.Ticker(symbol)
        
        # 嘗試抓取資料，如果失敗就多試幾次
        for attempt in range(3):
            try:
                df = ticker.history(period="3y")
                if not df.empty and len(df) >= 10:
                    break
            except:
                time.sleep(1) # 失敗了等一秒再試
                
        # 嘗試抓取股票名稱
        try:
            raw_name = ticker.info.get('shortName') or symbol
            name = str(raw_name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        except:
            name = symbol

        # 數據長度防呆檢查
        if df.empty or len(df) < 10: 
            return f"❌ 目前無法取得 {symbol} 的歷史數據，可能是網路繁忙，請稍後再試一次！", None, None

        curr_price = float(df['Close'].iloc[-1])
        p_usd = curr_price if not is_tw else curr_price / 32
        p_twd = curr_price * 32 if not is_tw else curr_price

        # 計算報酬率
        data_len = len(df)
        idx_252 = min(252, data_len - 1)
        idx_504 = min(504, data_len - 1)
        
        ret_2025 = ((df['Close'].iloc[-1] / df['Close'].iloc[-idx_252]) - 1) * 100 if data_len > idx_252 else 0
        ret_2024 = ((df['Close'].iloc[-idx_252] / df['Close'].iloc[-idx_504]) - 1) * 100 if data_len > idx_504 else 0

        # 計算均線策略
        df['SMA60'] = df['Close'].rolling(window=min(60, data_len)).mean()
        df['SMA240'] = df['Close'].rolling(window=min(240, data_len)).mean()
        l60, l240 = df['SMA60'].iloc[-1], df['SMA240'].iloc[-1]

        if pd.isna(l60) or pd.isna(l240):
            status, advice = "🟡 觀察", "歷史數據不足以計算長期均線，請謹慎操作"
            forecast = "無法預估"
        elif curr_price > l60 and l60 > l240: 
            status, advice = "✅ 要持有", "多頭排列強勢，建議抱緊"
            forecast = "+10% ~ +25%"
        elif curr_price > l240: 
            status, advice = "🟡 觀察", "季線附近震盪，暫不追高"
            forecast = "-5% ~ +5%"
        else: 
            status, advice = "❌ 賣出", "趨勢轉空，建議減碼"
            forecast = "-10% ~ +2%"
            
        # 最終排版
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

        img = generate_custom_chart(df, symbol)
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
            
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)
    except: pass

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
        app = ApplicationBuilder().token(TOKEN).build()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(set_bot_menu(app))
            else:
                loop.run_until_complete(set_bot_menu(app))
        except:
            pass

        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        print("🚀 NeoTycoon 正在運行中...")
        app.run_polling()
