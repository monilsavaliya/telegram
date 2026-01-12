import logging
import asyncio
import os
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from taxi_engine import TaxiEngine
from ride_card_renderer import RideCardRenderer

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Load Env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

from location_service import LocationService

# Init Engines
taxi_engine = TaxiEngine()
renderer = RideCardRenderer()
loc_service = LocationService()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = taxi_engine.reset_session(user_id)
    
    # Request Location Button
    kb = [[KeyboardButton("📍 Share Current Location", request_location=True)]]
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude
    
    state = taxi_engine.get_state(user_id)["state"]
    
    if state == "PICKUP":
        msg = taxi_engine.handle_pickup(user_id, lat=lat, lon=lon)
        # Ask for Drop (Text or Loc)
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
        
    elif state == "DROP":
        options = taxi_engine.handle_drop(user_id, lat=lat, lon=lon)
        text, markup = renderer.render_vehicle_options(options)
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = taxi_engine.get_state(user_id)["state"]
    
    if state == "PICKUP":
        # Text based pickup -> Resolve Address
        msg_wait = await update.message.reply_text("🔍 Searching location...")
        
        res = await loc_service.resolve_address(text)
        if res:
            # Found exact location
            msg = taxi_engine.handle_pickup(user_id, text=text, lat=res["lat"], lon=res["lon"], resolved_address=res["address"])
        else:
            # Fallback
            msg = taxi_engine.handle_pickup(user_id, text=text)

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_wait.message_id)
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    elif state == "DROP":
        # Text based drop -> Resolve Address
        msg_wait = await update.message.reply_text("🔍 Finding destination...")
        
        res = await loc_service.resolve_address(text)
        if res:
             options = taxi_engine.handle_drop(user_id, text=text, lat=res["lat"], lon=res["lon"], resolved_address=res["address"])
        else:
             options = taxi_engine.handle_drop(user_id, text=text)
             
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_wait.message_id)
        text_out, markup = renderer.render_vehicle_options(options)
        await update.message.reply_text(text_out, reply_markup=markup, parse_mode="Markdown")
        
    elif state == "WAITING_CONTACT":
        # Assume text is phone number
        msg = taxi_engine.handle_contact(user_id, text)
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    elif state == "WAITING_OTP":
        # Verify OTP
        result = taxi_engine.verify_otp(user_id, text)
        markup = None
        
        if result["status"] == "success":
             # Start Tracking Job
             card_text = renderer.render_driver_card(result["driver"])
             sent_msg = await update.message.reply_text(f"{card_text}\n\n📍 Driver is {taxi_engine.get_state(user_id)['data']['driver_dist']:.1f}km away.", parse_mode="Markdown")
             
             # Store Job Context
             context.job_queue.run_repeating(
                 callback=track_driver_callback, 
                 interval=5, 
                 first=2, 
                 chat_id=update.effective_chat.id,
                 name=str(user_id),
                 data={"user_id": user_id, "msg_id": sent_msg.message_id}
             )
        else:
             await update.message.reply_text(result["message"])

    else:
        # Fallback / IDLE state: Auto-start
        await start(update, context)

async def track_driver_callback(context: ContextTypes.DEFAULT_TYPE):
    """Updates the driver status message."""
    job = context.job
    user_id = job.data["user_id"]
    msg_id = job.data["msg_id"]
    
    dist, status_text, arrived = taxi_engine.get_driver_update(user_id)
    
    # Edit Message
    try:
        await context.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=msg_id,
            text=status_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        pass # Ignore "Message Not Modified" errors
        
    if arrived:
        job.schedule_removal()
        await context.bot.send_message(chat_id=job.chat_id, text="✅ **Trip Started!** Have a safe ride.")

async def handle_live_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'Live Location' updates from User."""
    if update.edited_message and update.edited_message.location:
        user_id = update.effective_user.id
        loc = update.edited_message.location
        # In a real app, we'd update pickup/drop or driver route here.
        # For now, just log/ack silently or print for demo.
        print(f"📍 User Moved: {loc.latitude}, {loc.longitude}")
        # update taxi_engine state if needed...

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    data = query.data
    if "book_taxi_" in data:
        vehicle_id = data.replace("book_taxi_", "")
        msg = taxi_engine.select_vehicle(user_id, vehicle_id)
        if msg:
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("❌ Error selecting vehicle.")

if __name__ == '__main__':
    if not TOKEN:
        print("❌ Error: TELEGRAM_TOKEN not found in .env")
        exit(1)
        
    print("🚖 Taxi Bot (Standalone) Starting...")
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION & (~filters.UpdateType.EDITED_MESSAGE), handle_location)) # Static Loc
    app.add_handler(MessageHandler(filters.LOCATION & filters.UpdateType.EDITED_MESSAGE, handle_live_location)) # Live Loc Update
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    app.run_polling()
