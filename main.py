import yfinance as yf
import pandas as pd
import asyncio
import matplotlib.pyplot as plt
import io
import warnings
import os  # <--- 💎 關鍵：新增這行，讓程式會讀取系統保險箱
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime

# 基礎設定
warnings.filterwarnings("ignore")

# 💎 大表哥專屬保險箱 (改從環境變數讀取，不再寫死在代碼裡)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "6419138408")

def generate_custom_chart(df, symbol):
    """復刻大表哥提供的 WTI 風格圖表"""
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
        # BTC 自動轉換
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

        # 安全計算年化報酬
        data_len = len(df)
        idx_2025 = min(252, data_len - 1)
        ret_2025 = ((df['Close'].iloc[-1] / df['Close'].iloc[-idx_2025]) - 1) * 100 if data_len > 1 else 0
        if data_len > 504:
            ret_2024 = ((df['Close'].iloc[-252] / df['Close'].iloc[-504]) - 1) * 100
        elif data_len > 252:
            ret_2024 = ((df['Close'].iloc[-252] / df['Close'].iloc[0]) - 1) * 100
        else:
            ret_2024 = 0

        # 13勝策略
        df['SMA60'] = df['Close'].rolling(window=60).mean()
        df['SMA240'] = df['Close'].rolling(window=240).mean()
        last_60 = df['SMA60'].iloc[-1]
        last_240 = df['SMA240'].iloc[-1]

        if curr_price > last_60 and last_60 > last_240:
            status, advice, t_advice, est = "✅ 要持有", "多頭排列強勢，建議抱緊", "6-12個月", "15%~25%"
        elif curr_price > last_240:
            status, advice, t_advice, est = "🟡 觀察", "季線附近震盪，暫不追高", "短期觀望", "5%~10%"
        else:
            status, advice, t_advice, est = "❌ 賣出", "趨勢轉空，建議減碼", "立即離場", "-5%~2%"

        report = (
            f"💰 <b>【NeoTycoon 報告】</b>\n"
            f"---------------------------\n"
            f"名稱：{name} ({symbol})\n"
            f"美金價格：${p_usd:,.2f}\n"
            f"台幣價格：NT${p_twd:,.2f}\n"
            f"2025 年化報酬：{ret_2025:+.2f}%\n"
            f"2024 年化報酬：{ret_2024:+.2f}%\n"
            f"未來一年預計：{est}\n"
            f"---------------------------\n"
            f"持有建議：{status}\n"
            f"持有時間：{t_advice}\n"
            f"具體行動：{advice}\n"
            f"---------------------------\n"
            f"詳細點下面連結自己看👇( ｡•̀_•́｡)👇"
        )
        
        clean_sym = symbol.replace(".TW", "").replace("-USD", "")
        keyboard = [
            [InlineKeyboardButton("TradingView 圖表", url=f"https://www.tradingview.com/symbols/{clean_sym}/")],
            [InlineKeyboardButton("Investopedia 知識庫", url=f"https://www.investopedia.com/search?q={clean_sym}")],
            [InlineKeyboardButton("Yahoo 商品代號查詢", url=f"https://finance.yahoo.com/quote/{symbol}")]
        ]

        if is_tw or original_input == "BTC":
            img = generate_custom_chart(df, symbol)
        else:
            img = f"https://charts2.finviz.com/chart.ashx?t={clean_sym}&ty=c&ta=1&p=d"

        return report, InlineKeyboardMarkup(keyboard), img

    except Exception as e:
        return f"⚠️ 錯誤：{e}", None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.lower().startswith("@nt"): return
    cmd = text[3:].strip()
    
    if cmd in ["你好", "你好啊", "hi", "hello", "哈囉"]:
        await update.message.reply_text("👋( ´ ▽ ` )嗨")
        return

    if cmd == "建議":
        rec = "🏆 <b>【NT 策略推薦 TOP 10】</b>\n\n1. NVDA\n2. 2330.TW\n3. TSLA\n4. META\n5. 2317.TW\n6. AAPL\n7. MSFT\n8. AMD\n9. AMZN\n10. 2454.TW"
        await update.message.reply_text(rec, parse_mode='HTML') 
    elif cmd:
        wait_msg = await update.message.reply_text(f"🔍 正在通靈 {cmd}...")
        msg, markup, img = get_detailed_analysis(cmd)
        if img:
            await update.message.reply_photo(photo=img, caption=msg, reply_markup=markup, parse_mode='HTML')
        else:
            await update.message.reply_text(msg, reply_markup=markup, parse_mode='HTML')
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=wait_msg.message_id)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()