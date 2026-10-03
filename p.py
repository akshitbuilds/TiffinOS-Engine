import os
import json
import telebot
import datetime
from flask import Flask, request
from supabase import create_client
from groq import Groq
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)

# Clients Setup
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

bots = {}
user_context = {}

def get_bot(token):
    if token not in bots:
        bots[token] = telebot.TeleBot(token, threaded=False)
    return bots[token]


# ---------------- MENU ----------------
def get_menu(vendor_id):
    try:
        res = supabase.table("menu") \
            .select("category,item_name,price") \
            .eq("vendor_id", vendor_id) \
            .execute().data

        if not res:
            return "Menu abhi available nahi hai."

        menu = {}

        for row in res:
            cat = row.get("category") or "Menu"
            name = row.get("item_name") or "Item"
            price = row.get("price") or "0"

            if cat not in menu:
                menu[cat] = []

            menu[cat].append(f"{name} - ₹{price}")

        msg = "📋 Today's Menu\n\n"

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
        pin_str = str(pincode).strip()

        kitchens = supabase.table("kitchens") \
            .select("manager_chat_id") \
            .eq("vendor_id", vendor_id) \
            .eq("pincode", pin_str) \
            .execute().data

        if kitchens:
            for k in kitchens:
                try:
                    bot.send_message(
                        int(float(k['manager_chat_id'])),
                        f"👨‍🍳 KITCHEN ALERT (PIN {pin_str})\n\n{message_text}",
                        reply_markup=markup
                    )
                except:
                    pass

        try:
            bot.send_message(
                int(float(owner_id)),
                f"👑 VENDOR ALERT\n\n{message_text}",
                reply_markup=markup
            )
        except:
            pass

    except Exception as e:
        print("Alert Error:", e)


# ---------------- WEBHOOK ----------------
@app.route('/webhook/<token>', methods=['POST'])
def handle_webhook(token):

    try:
        bot = get_bot(token)

        update = telebot.types.Update.de_json(
            request.get_data().decode('utf-8')
        )

        vendor_res = supabase.table("vendors") \
            .select("*") \
            .eq("bot_token", token) \
            .execute().data

        if not vendor_res:
            return "OK", 200

        vendor = vendor_res[0]
        owner_id = str(vendor['owner_chat_id'])

        # ---------------- CALLBACK BUTTONS ----------------
        if update.callback_query:

            cb = update.callback_query
            chat_id = cb.message.chat.id
            cust_id = cb.data.split('_')[-1]

            if cb.data.startswith("opt_acc"):

                bot.answer_callback_query(cb.id, "Order Accepted!")

                try:
                    bot.send_message(
                        int(float(cust_id)),
                        "Aapka order accept ho gaya hai! ✅"
                    )
                except:
                    pass

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton(
                        "💬 Chat with Customer",
                        callback_data=f"chat_btn_{cust_id}"
                    )
                )

                bot.edit_message_text(
                    cb.message.text + "\n\n✅ Status: Accepted",
                    chat_id=chat_id,
                    message_id=cb.message.message_id,
                    reply_markup=markup
                )

            elif cb.data.startswith("chat_btn"):

                bot.answer_callback_query(cb.id)

                bot.send_message(
                    chat_id,
                    f"Reply bhejne ke liye:\n\n/reply {cust_id} [message]"
                )

            return "OK", 200


        # ---------------- MESSAGE ----------------
        if update.message and update.message.text:

            chat_id = str(update.message.chat.id)
            text = update.message.text
            ctx_key = f"{vendor['id']}_{chat_id}"


            # ---------------- MANUAL REPLY ----------------
            if text.startswith("/reply"):

                parts = text.split(maxsplit=2)

                if len(parts) >= 3:

                    target = parts[1]
                    target_ctx = f"{vendor['id']}_{target}"

                    bot.send_message(
                        int(float(target)),
                        f"💬 Manager Message:\n{parts[2]}"
                    )

                    user_context[target_ctx] = {
                        "paused_until":
                        datetime.datetime.now() +
                        datetime.timedelta(minutes=30)
                    }

                return "OK", 200


            # ---------------- START ----------------
            if text == "/start":

                bot.send_message(
                    chat_id,
                    f"Namaste! 🙏\n"
                    f"Welcome to {vendor['vendor_name']}\n\n"
                    f"{get_menu(vendor['id'])}\n"
                    "Aap order place kar sakte hain ya tiffin pause request bhej sakte hain."
                )

                return "OK", 200


            pause_time = user_context.get(ctx_key, {}).get("paused_until")

            if pause_time and datetime.datetime.now() < pause_time:

                bot.send_message(
                    int(float(owner_id)),
                    f"📩 Direct Message ({chat_id})\n{text}"
                )

                return "OK", 200


            # ---------------- AI TOOLS ----------------
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "place_order",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "details": {"type": "string"},
                                "address": {"type": "string"},
                                "name": {"type": "string"},
                                "phone": {"type": "string"},
                                "pincode": {"type": "string"}
                            },
                            "required": ["details","address","name","phone","pincode"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "pause_req",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string"},
                                "name": {"type": "string"},
                                "phone": {"type": "string"},
                                "pincode": {"type": "string"}
                            },
                            "required": ["date","name","phone","pincode"]
                        }
                    }
                }
            ]


            ai_res = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content":
                        f"You are Tiffin AI for {vendor['vendor_name']}. "
                        f"Menu: {get_menu(vendor['id'])}. "
                        "Use place_order only for food orders. "
                        "Use pause_req only when customer asks to pause tiffin."
                    },
                    {"role": "user", "content": text}
                ],
                tools=tools
            )

            ai_msg = ai_res.choices[0].message if ai_res.choices else None


            if ai_msg and ai_msg.tool_calls:

                for tool in ai_msg.tool_calls:

                    args = json.loads(tool.function.arguments)

                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("✅ Accept Order",callback_data=f"opt_acc_{chat_id}"),
                        InlineKeyboardButton("💬 Chat",callback_data=f"chat_btn_{chat_id}")
                    )


                    if tool.function.name == "place_order":

                        supabase.table("orders").insert({
                            "vendor_id": vendor["id"],
                            "customer_chat_id": chat_id,
                            "customer_name": args["name"],
                            "customer_phone": args["phone"],
                            "delivery_address": args["address"],
                            "order_details": args["details"],
                            "status": "pending",
                            "created_at": datetime.datetime.now().isoformat()
                        }).execute()


                        msg = (
                            f"🍱 NEW ORDER\n\n"
                            f"👤 {args['name']}\n"
                            f"📞 {args['phone']}\n"
                            f"📍 {args['address']}\n"
                            f"📮 PIN {args['pincode']}\n\n"
                            f"📝 {args['details']}"
                        )

                        send_smart_alerts(
                            bot,
                            vendor["id"],
                            owner_id,
                            args["pincode"],
                            msg,
                            markup
                        )

                        bot.send_message(chat_id,"Dhanyawad! Aapka order note ho gaya hai ✅")


                    elif tool.function.name == "pause_req":

                        msg = (
                            f"⏸️ PAUSE REQUEST\n\n"
                            f"👤 {args['name']}\n"
                            f"📞 {args['phone']}\n"
                            f"📅 Date {args['date']}\n"
                            f"📍 PIN {args['pincode']}"
                        )

                        send_smart_alerts(
                            bot,
                            vendor["id"],
                            owner_id,
                            args["pincode"],
                            msg,
                            markup
                        )

                        bot.send_message(chat_id,f"Aapka tiffin {args['date']} ke liye pause ho gaya hai 👍")


            else:

                bot.send_message(
                    int(float(owner_id)),
                    f"📩 Message ({chat_id})\n{text}"
                )

                bot.send_message(
                    chat_id,
                    ai_msg.content if ai_msg and ai_msg.content else "Kripya thoda aur details dein."
                )

        return "OK",200

    except Exception as e:
        print("Server Error:",e)
        return "OK",200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT",5000))
    )