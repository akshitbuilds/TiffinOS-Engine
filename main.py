import os
import json
import telebot
import datetime
import re
from flask import Flask, request
from supabase import create_client
from groq import Groq
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)

# ---------------- CLIENT SETUP ----------------
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

bots = {}
user_context = {}

def get_bot(token):
    if token not in bots:
        bots[token] = telebot.TeleBot(token, threaded=True)
    return bots[token]


# ---------------- HEALTH ROUTE ----------------
@app.route("/")
def home():
    return "Karvi bot running", 200


# ---------------- MENU ----------------
def get_menu(vendor_id):

    try:
        res = supabase.table("menu")\
            .select("category,item_name,price")\
            .eq("vendor_id", vendor_id)\
            .execute().data

        if not res:
            return "Menu abhi available nahi hai."

        menu = {}
        msg = "📋 Today's Menu\n\n"

        for row in res:
            cat = row.get("category") or "Menu"
            name = row.get("item_name")
            price = row.get("price")

            if cat not in menu:
                menu[cat] = []

            menu[cat].append(f"{name} - ₹{price}")

        for cat, items in menu.items():
            msg += f"🍽 {cat}\n"
            for i in items:
                msg += f"• {i}\n"
            msg += "\n"

        return msg

    except Exception as e:
        print("Menu Error:", e)
        return "Menu load nahi ho pa raha."


# ---------------- ALERT SYSTEM ----------------
def send_smart_alerts(bot, vendor_id, owner_id, pincode, message_text, markup=None):

    try:
        pin = str(pincode).strip()

        kitchens = supabase.table("kitchens")\
            .select("manager_chat_id")\
            .eq("vendor_id", vendor_id)\
            .eq("pincode", pin)\
            .execute().data

        if kitchens:
            for k in kitchens:
                try:
                    bot.send_message(
                        int(float(k["manager_chat_id"])),
                        f"👨‍🍳 KITCHEN ALERT (PIN {pin})\n\n{message_text}",
                        reply_markup=markup
                    )
                except:
                    pass

        bot.send_message(
            int(float(owner_id)),
            f"👑 VENDOR ALERT\n\n{message_text}",
            reply_markup=markup
        )

    except Exception as e:
        print("Alert Error:", e)


# ---------------- WEBHOOK ----------------
@app.route("/webhook/<token>", methods=["POST"])
def handle_webhook(token):

    try:
        bot = get_bot(token)

        update = telebot.types.Update.de_json(
            request.get_data().decode("utf-8")
        )

        vendor_res = supabase.table("vendors")\
            .select("*")\
            .eq("bot_token", token)\
            .execute().data

        if not vendor_res:
            return "OK",200

        vendor = vendor_res[0]
        owner_id = str(vendor["owner_chat_id"])


# ---------------- CALLBACK BUTTONS ----------------
        if update.callback_query:

            cb = update.callback_query
            data = cb.data
            cust_id = data.split("_")[-1]

            if data.startswith("opt_acc"):

                bot.answer_callback_query(cb.id,"Order Accepted")
                bot.send_message(int(cust_id),"✅ Aapka order accept ho gaya hai.")

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("💬 Chat",callback_data=f"chat_btn_{cust_id}")
                )

                bot.edit_message_reply_markup(
                    chat_id=cb.message.chat.id,
                    message_id=cb.message.message_id,
                    reply_markup=markup
                )

            elif data.startswith("pause_ok"):

                bot.answer_callback_query(cb.id,"Pause Approved")
                bot.send_message(int(cust_id),"⏸️ Aapka tiffin successfully pause ho gaya hai.")

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("💬 Chat",callback_data=f"chat_btn_{cust_id}")
                )

                bot.edit_message_reply_markup(
                    chat_id=cb.message.chat.id,
                    message_id=cb.message.message_id,
                    reply_markup=markup
                )

            elif data.startswith("chat_btn"):

                bot.answer_callback_query(cb.id)

                bot.send_message(
                    cb.message.chat.id,
                    f"Customer ko message bhejne ke liye:\n\n/reply {cust_id} message"
                )

            return "OK",200


# ---------------- MESSAGE HANDLER ----------------
        if update.message and update.message.text:

            chat_id = str(update.message.chat.id)
            text = update.message.text
            text_lower = text.lower()

            ctx_key = f"{vendor['id']}_{chat_id}"


# ---------- START ----------
            if text == "/start":

                bot.send_message(
                    chat_id,
                    f"Namaste! 🙏\nWelcome to {vendor['vendor_name']}\n\n{get_menu(vendor['id'])}"
                )

                return "OK",200


# ---------- VENDOR REPLY ----------
            if text.startswith("/reply"):

                parts = text.split(maxsplit=2)

                if len(parts) >= 3:

                    target = parts[1]
                    msg = parts[2]

                    bot.send_message(int(target),f"💬 Vendor:\n{msg}")
                    bot.send_message(chat_id,"✅ Message Sent")

                    user_context[f"{vendor['id']}_{target}"]={
                        "paused_until":
                        datetime.datetime.now()+datetime.timedelta(minutes=30)
                    }

                return "OK",200


# ---------- HUMAN TAKEOVER ----------
            pause_time = user_context.get(ctx_key, {}).get("paused_until")

            if pause_time and datetime.datetime.now() < pause_time:

                bot.send_message(
                    int(owner_id),
                    f"📩 Customer Message ({chat_id})\n{text}"
                )

                return "OK",200


# ---------- PAUSE DETECTION ----------
            pause_match = re.search(
                r"pause.*(\d+).*march.*name\s*is\s*([a-zA-Z ]+).*number\s*is\s*(\d+)",
                text_lower
            )

            if pause_match:

                date = pause_match.group(1) + " March"
                name = pause_match.group(2).title()
                phone = pause_match.group(3)

                pause_buttons = InlineKeyboardMarkup()
                pause_buttons.add(
                    InlineKeyboardButton("✅ Approve Pause",callback_data=f"pause_ok_{chat_id}"),
                    InlineKeyboardButton("💬 Chat",callback_data=f"chat_btn_{chat_id}")
                )

                msg=f"""⏸️ PAUSE REQUEST

👤 Name: {name}
📞 Phone: {phone}
📅 Date: {date}

💬 Customer Message:
{text}

🆔 Customer ID: {chat_id}
"""

                send_smart_alerts(bot,vendor["id"],owner_id,"000000",msg,pause_buttons)

                bot.send_message(chat_id,"⏸️ Aapki pause request vendor ko bhej di gayi hai.")

                return "OK",200


# ---------- ORDER DETECTION ----------
            order_match = re.search(
                r"order\s*(\d+).*name\s*is\s*([a-zA-Z ]+).*number\s*is\s*(\d+).*address\s*is\s*(.*).*pincode\s*is\s*(\d+)",
                text_lower
            )

            if order_match:

                qty = order_match.group(1)
                name = order_match.group(2).title()
                phone = order_match.group(3)
                address = order_match.group(4)
                pincode = order_match.group(5)

                item="Tiffinos special thali"

                order_buttons = InlineKeyboardMarkup()
                order_buttons.add(
                    InlineKeyboardButton("✅ Accept Order",callback_data=f"opt_acc_{chat_id}"),
                    InlineKeyboardButton("💬 Chat",callback_data=f"chat_btn_{chat_id}")
                )

                msg=f"""🍱 NEW ORDER

👤 {name}
📞 {phone}
📍 {address}
📮 PIN {pincode}

📝 {qty} x {item}
"""

                send_smart_alerts(bot,vendor["id"],owner_id,pincode,msg,order_buttons)

                bot.send_message(chat_id,"Dhanyawad! Order note ho gaya hai ✅")

                return "OK",200


# ---------- AI AUTO REPLY ----------
            try:

                menu_text = get_menu(vendor['id'])

                ai = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {
                            "role":"system",
                            "content":f"""
You are a tiffin assistant for {vendor['vendor_name']}.

MENU:
{menu_text}

Rules:
- Only answer using the menu above.
- If customer asks for item not in menu say:
"Sorry, woh item hamare menu mein available nahi hai."
- Never invent items.
"""
                        },
                        {"role":"user","content":text}
                    ]
                )

                reply = ai.choices[0].message.content

                if reply:
                    bot.send_message(chat_id,reply)

            except:
                pass


# ---------- ALSO NOTIFY VENDOR ----------
            try:
                bot.send_message(
                    int(owner_id),
                    f"📩 Customer Message ({chat_id})\n{text}"
                )
            except:
                pass

        return "OK",200

    except Exception as e:
        print("Server Error:",e)
        return "OK",200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT",5000))
    )