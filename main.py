import os
import yfinance as yf
import pandas as pd
import asyncio
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import io
import threading
import requests

from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes
)

# =========================
# Render 保活伺服器
# =========================
def run_dummy_server():

    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"NeoTycoon is Awake!")

    port = int(os.environ.get("PORT", 8080))

    try:
        server = HTTPServer(("0.0.0.0", port), SimpleHandler)
        server.serve_forever()

    except Exception as e:
        print("Dummy Server Error:", e)


threading.Thread(
    target=run_dummy_server,
    daemon=True
).start()


# =========================
# 畫圖功能
# =========================
def generate_custom_chart(df, symbol):

    try:
        plt.figure(figsize=(10, 5))

        plt.style.use("bmh")

        plt.plot(
            df.index,
            df["Close"],
            linewidth=2
        )

        plt.title(f"{symbol} Trend")

        plt.tight_layout()

        buf = io.BytesIO()

        plt.savefig(buf, format="png")

        buf.seek(0)

        plt.close()

        return buf

    except Exception as e:
        print("Chart Error:", e)
        return None


# =========================
# 股票分析核心
# =========================
def get_detailed_analysis(symbol):

    try:

        original_input = symbol.upper().strip()

        # 特殊代號修正
        if original_input == "BTC":
            original_input = "BTC-USD"

        if original_input == "SNP":
            original_input = "SPY"

        symbol = original_input

        is_tw = ".TW" in symbol

        df = pd.DataFrame()

        name = symbol

        # ====================================
        # 美股 / ETF / Crypto
        # ====================================
        if not is_tw:

            # Stooq 代碼
            if "-USD" in symbol:
                stooq_code = symbol.replace("-USD", "USD").upper() + ".CC"
            else:
                stooq_code = f"{symbol}.US"

            csv_url = f"https://stooq.com/q/d/l/?s={stooq_code}&i=d"

            # ---------------------------
            # 先嘗試 Stooq
            # ---------------------------
            try:

                headers = {
                    "User-Agent": "Mozilla/5.0"
                }

                response = requests.get(
                    csv_url,
                    headers=headers,
                    timeout=15
                )

                if (
                    response.status_code == 200
                    and "Close" in response.text
                ):

                    stooq_df = pd.read_csv(
                        io.StringIO(response.text)
                    )

                    if not stooq_df.empty:

                        stooq_df["Date"] = pd.to_datetime(
                            stooq_df["Date"]
                        )

                        stooq_df.set_index(
                            "Date",
                            inplace=True
                        )

                        df = stooq_df.sort_index(
                            ascending=True
                        ).copy()

                        print("✅ 使用 Stooq 成功")

            except Exception as e:
                print("❌ Stooq 失敗:", e)

            # ---------------------------
            # Stooq 失敗 -> Yahoo 備援
            # ---------------------------
            if df.empty:

                try:

                    print("⚠️ 改用 Yahoo Finance")

                    ticker = yf.Ticker(symbol)

                    df = ticker.history(period="3y")

                    if not df.empty:

                        try:
                            raw_name = ticker.info.get("shortName")
                            if raw_name:
                                name = str(raw_name)

                        except:
                            pass

                except Exception as e:

                    return (
                        f"❌ 無法取得美股 {symbol} 資料\n錯誤：{e}",
                        None,
                        None
                    )

        # ====================================
        # 台股
        # ====================================
        else:

            try:

                ticker = yf.Ticker(symbol)

                df = ticker.history(period="3y")

                try:

                    raw_name = ticker.info.get("shortName")

                    if raw_name:
                        name = str(raw_name)

                except:
                    pass

            except Exception as e:

                return (
                    f"❌ 找不到台股 {symbol}\n錯誤：{e}",
                    None,
                    None
                )

        # ====================================
        # 防呆
        # ====================================
        if df.empty or len(df) < 10:

            return (
                f"❌ 找不到 {symbol} 的歷史資料",
                None,
                None
            )

        # ====================================
        # 價格
        # ====================================
        curr_price = float(df["Close"].iloc[-1])

        if is_tw:
            p_twd = curr_price
            p_usd = curr_price / 32
        else:
            p_usd = curr_price
            p_twd = curr_price * 32

        # ====================================
        # 報酬率
        # ====================================
        data_len = len(df)

        idx_252 = min(252, data_len - 1)
        idx_504 = min(504, data_len - 1)

        ret_2025 = (
            (
                df["Close"].iloc[-1]
                / df["Close"].iloc[-idx_252]
            ) - 1
        ) * 100

        ret_2024 = (
            (
                df["Close"].iloc[-idx_252]
                / df["Close"].iloc[-idx_504]
            ) - 1
        ) * 100

        # ====================================
        # 均線
        # ====================================
        df["SMA60"] = df["Close"].rolling(
            window=min(60, data_len)
        ).mean()

        df["SMA240"] = df["Close"].rolling(
            window=min(240, data_len)
        ).mean()

        l60 = df["SMA60"].iloc[-1]
        l240 = df["SMA240"].iloc[-1]

        if pd.isna(l60) or pd.isna(l240):

            status = "🟡 觀察"
            advice = "歷史數據不足"

            forecast = "無法預估"

        elif curr_price > l60 and l60 > l240:

            status = "✅ 持有"
            advice = "多頭排列"

            forecast = "+10% ~ +25%"

        elif curr_price > l240:

            status = "🟡 觀察"
            advice = "震盪整理"

            forecast = "-5% ~ +5%"

        else:

            status = "❌ 減碼"
            advice = "趨勢轉弱"

            forecast = "-10% ~ +2%"

        # ====================================
        # 報告
        # ====================================
        report = (
            f"💰 <b>【NeoTycoon 報告】</b>\n"
            f"----------------------\n"
            f"名稱：{name}\n"
            f"美金：${p_usd:,.2f}\n"
            f"台幣：NT${p_twd:,.0f}\n"
            f"2025 報酬：{ret_2025:+.2f}%\n"
            f"2024 報酬：{ret_2024:+.2f}%\n"
            f"未來一年預估：{forecast}\n"
            f"----------------------\n"
            f"持有建議：<b>{status}</b>\n"
            f"具體行動：{advice}"
        )

        # ====================================
        # 按鈕
        # ====================================
        clean_sym = (
            symbol
            .replace(".TW", "")
            .replace("-USD", "")
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "TradingView",
                    url=f"https://www.tradingview.com/symbols/{clean_sym}/"
                )
            ],

            [
                InlineKeyboardButton(
                    "Yahoo Finance",
                    url=f"https://finance.yahoo.com/quote/{symbol}"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(keyboard)

        # ====================================
        # 圖片
        # ====================================
        img = generate_custom_chart(df, symbol)

        return report, markup, img

    except Exception as e:

        return (
            f"⚠️ 分析錯誤：{e}",
            None,
            None
        )


# =========================
# Telegram 訊息處理
# =========================
async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text.strip()

    if not text.lower().startswith("@nt"):
        return

    cmd = text[3:].strip()

    # 打招呼
    if cmd.lower() in ["hi", "hello", "你好"]:

        await update.message.reply_text(
            "👋 NeoTycoon 已上線"
        )

        return

    # 推薦名單
    if cmd == "建議":

        top_list = [
            "NVDA",
            "SPY",
            "TSLA",
            "META",
            "AAPL",
            "MSFT",
            "AMD",
            "AMZN",
            "2330.TW"
        ]

        text_out = "\n".join([
            f"{i+1}. <b>{code}</b>"
            for i, code in enumerate(top_list)
        ])

        rec = (
            f"🏆 <b>推薦名單</b>\n"
            f"----------------------\n"
            f"{text_out}\n"
            f"----------------------\n"
            f"輸入：<code>@nt SPY</code>"
        )

        await update.message.reply_text(
            rec,
            parse_mode="HTML"
        )

        return

    # 開始分析
    wait_msg = await update.message.reply_text(
        f"🔍 正在分析 {cmd}..."
    )

    msg, markup, img = get_detailed_analysis(cmd)

    try:

        if img:

            await update.message.reply_photo(
                photo=img,
                caption=msg,
                reply_markup=markup,
                parse_mode="HTML"
            )

        else:

            await update.message.reply_text(
                msg,
                reply_markup=markup,
                parse_mode="HTML"
            )

    except Exception as e:

        await update.message.reply_text(
            f"❌ 傳送失敗：{e}"
        )

    # 刪除等待訊息
    try:

        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=wait_msg.message_id
        )

    except:
        pass


# =========================
# 主程式
# =========================
if __name__ == "__main__":

    TOKEN = os.getenv("TELEGRAM_TOKEN")

    if not TOKEN:

        print("❌ 沒有 TELEGRAM_TOKEN")

    else:

        print("🚀 NeoTycoon 啟動中")

        app = (
            ApplicationBuilder()
            .token(TOKEN)
            .build()
        )

        app.add_handler(
            MessageHandler(
                filters.TEXT & (~filters.COMMAND),
                handle_message
            )
        )

        app.run_polling()
