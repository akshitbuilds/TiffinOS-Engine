import os
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Secret keys load karein
load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

# 2. Supabase Client Setup
supabase: Client = create_client(url, key)

# 3. INSERT Function: Naya item daalne ke liye
def add_item_to_db(item_name, price):
    response = supabase.table("menu").insert({"item_name": item_name, "price": price}).execute()
    print(f"✅ Item '{item_name}' added to Database!")                
    return response

# 4. SELECT Function: Saara data nikalne ke liye
def fetch_menu():
    response = supabase.table("menu").select("*").execute()
    data = response.data
    print("\n📋 Current Menu from DB:")
    for item in data:
        print(f"🍽️ {item['item_name']} - ₹{item['price']}")
    return data

# --- Testing the functions ---
# Uncomment the line below to add an item
add_item_to_db("Veg Thali", 100)

# Fetch and print the menu
fetch_menu()