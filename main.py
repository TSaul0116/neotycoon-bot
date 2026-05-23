import os
import yfinance as yf
import pandas as pd
import asyncio
import matplotlib.pyplot as plt
import io
import warnings
import threading
import requests
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

# 3. 核心分析 (修復 Stooq 與隱藏地雷的全面完工版)
def get_detailed_analysis(symbol):
    try:
        original_input = symbol.upper()
        if original_input == "BTC": symbol = "BTC-USD"
        symbol = symbol.upper()
        
        is_tw = ".TW" in symbol
        df = pd.DataFrame()
        name = symbol  # 預設名稱為代號，防止去問 Yahoo 名字時被限流卡死
        
        # 🌟 第一重保險：美股/加密貨幣優先嘗試走 Stooq 機制
        if not is_tw:
            try:
                time.sleep(1) # 讓請求稍微緩衝 1 秒，假裝是人類
                import pandas_datareader.data as web
                
                # 轉換 Stooq 專用後綴
                if "-USD" in symbol:
                    stooq_symbol = symbol.replace("-USD", "USD").upper() + ".CC"
                else:
                    stooq_symbol = f"{symbol}.US"
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=3 * 365)
                
                # 從 Stooq 撈取資料
                stooq_df = web.DataReader(stooq_symbol, 'stooq', start_date, end_date)
                if stooq_df is not None and not stooq_df.empty:
                    # 🟢 修正核心 1：先複製數據，確保欄位統一名稱，再做時間正序排列
                    df = stooq_df.copy()
                    df.index.name = 'Date'
                    df = df.sort_index(ascending=True) # 由舊到新 (2023 -> 2026)
                    df = df.rename(columns={'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume'})
            except Exception as e:
                print(f"🔄 Stooq 抓取失敗，準備切換回 Yahoo 備用線: {e}")

        # 🌟 第二重保險：如果 Stooq 沒抓到，或者是台股，就走原來的 yfinance 路線
        if df.empty:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="3y")
                # 嘗試拿取 Yahoo 名字，失敗就用代號
                try:
                    raw_name = ticker.info.get('shortName') or symbol
                    name = str(raw_name).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                except:
                    pass
            except Exception as e:
                return f"❌ 找不到 {symbol} 或 Yahoo 財經正忙，錯誤：{e}", None, None
        
        # 🟢 修正核心 3：安全檢查，如果資料太少就拒絕分析，防止後面 iloc[-1] 崩潰
        if df.empty or len(df) < 10: 
            return f"❌ 找不到 {symbol} 的歷史數據或資料量不足", None, None

        curr_price = float(df['Close'].iloc[-1])
        p_usd = curr_price if not is_tw else curr_price / 32
        p_twd = curr_price * 32 if not is_tw else curr_price

        # 計算報酬率 (加上安全防呆，防止天數不夠)
        data_len = len(df)
        idx_252 = min(252, data_len - 1)
        idx_504 = min(504, data_len - 1)
        
        ret_2025 = ((df['Close'].iloc[-1] / df['Close'].iloc[-idx_252]) - 1) * 100 if data_len > idx_252 else 0
        ret_2024 = ((df['Close'].iloc[-idx_252] / df['Close'].iloc[-idx_504]) - 1) * 100 if data_len > idx_252 else 0

        # 計算均線策略
        df['SMA60'] = df['Close'].rolling(window=min(60, data_len)).mean()
        df['SMA240'] = df['Close'].rolling(window=min(240, data_len)).mean()
        l60, l240 = df['SMA60'].iloc[-1], df['SMA240'].iloc[-1]

        # 補足均線不存在時的防呆
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
            
        # ⭐ 最終排版
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
            
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)
    except: pass

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