# TiffinOS-Engine

Multi-vendor Telegram bot backend for tiffin (home-food) services. It answers customer menu questions with an LLM and routes orders and pause requests to the vendor with approve buttons.

## What it does
- One server serves many vendors. Each vendor has their own Telegram bot, found by bot token (`/webhook/<token>`).
- `/start` shows the vendor's menu, read from Supabase.
- Customer messages that don't match an order or pause pattern get an LLM reply (Groq, Llama 3.3 70B). The prompt contains the vendor's menu and tells the model not to invent items.
- Order and pause requests are detected with regex on a fixed message format. They are sent to the vendor, and to kitchen managers matched by pincode, with inline buttons (Accept Order, Approve Pause, Chat).
- Human takeover: the vendor replies with `/reply <customer_id> <message>`, which pauses the AI for that customer for 30 minutes.

## Stack
Python, Flask, pyTelegramBotAPI, Supabase, Groq API.

## Setup
1. `pip install -r requirements.txt`
2. Set environment variables (see `.env.example`): `SUPABASE_URL`, `SUPABASE_KEY`, `GROQ_API_KEY`.
3. Supabase tables used: `vendors` (id, vendor_name, bot_token, owner_chat_id), `menu` (vendor_id, category, item_name, price), `kitchens` (vendor_id, pincode, manager_chat_id).
4. Deploy `main.py` (Render or any host), set `RENDER_URL` in `onboard.py`, then run `python onboard.py` and enter a vendor's bot token to register the webhook.

## Known limitations
- Orders and pauses need a fixed phrasing (for example "order 2 … name is … number is … address is … pincode is …"). It is not free-form.
- The pause pattern currently supports only "March" dates, and a date capture bug is being fixed.
- Human-takeover state is in memory, so it resets on restart.
- Errors in the AI reply path are silently ignored.
- No tests. The order item is hardcoded.
