import telebot

# CHANGE THIS after you get your Render URL
RENDER_URL = "https://your-new-app.onrender.com" 

def setup_bot(token):
    bot = telebot.TeleBot(token)
    webhook_url = f"{RENDER_URL}/webhook/{token}"
    
    bot.remove_webhook()
    success = bot.set_webhook(url=webhook_url)
    
    if success:
        print(f"✅ Webhook linked to: {webhook_url}")
    else:
        print("❌ Failed to set webhook.")

if __name__ == "__main__":
    token = input("Enter Vendor Bot Token: ")
    setup_bot(token)
