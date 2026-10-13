import os, sqlite3, secrets, logging, calendar
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMINS = {int(v) for v in os.getenv("ADMIN_IDS", "").split(",") if v.strip().isdigit()}
DB_PATH = os.getenv("DB_PATH", "lottery.db")
TZ = ZoneInfo("Africa/Addis_Ababa")
PLANS = {"daily": ("Daily", 100), "weekly": ("Weekly", 50), "monthly": ("Monthly", 50)}
logging.basicConfig(level=logging.INFO)
pending = {}

def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT, name TEXT, joined TEXT);
        CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan TEXT,
          draw_key TEXT, number TEXT, price INTEGER, status TEXT DEFAULT 'DEMO', created TEXT,
          UNIQUE(plan,draw_key,number));
        CREATE TABLE IF NOT EXISTS results(plan TEXT, draw_key TEXT, number TEXT, admin_id INTEGER, published TEXT,
          PRIMARY KEY(plan,draw_key));
        CREATE TABLE IF NOT EXISTS closures(plan TEXT, draw_key TEXT, PRIMARY KEY(plan,draw_key));
        """)

def now(): return datetime.now(TZ)
def key_for(plan, d=None):
    d = d or now()
    if plan == "daily": return d.strftime("%Y-%m-%d")
    if plan == "weekly":
        x = d.isocalendar()
        return f"{x.year}-W{x.week:02d}"
    return d.strftime("%Y-%m")

def next_time(plan, d=None):
    d = d or now()
    if plan == "daily":
        x = datetime.combine(d.date(), time(20), TZ)
        return x if x > d else x + timedelta(days=1)
    if plan == "weekly":
        days = (6 - d.weekday()) % 7
        x = datetime.combine(d.date()+timedelta(days=days), time(20), TZ)
        return x if x > d else x + timedelta(days=7)
    y, m = d.year, d.month
    last = calendar.monthrange(y,m)[1]
    x = datetime.combine(date(y,m,last), time(20), TZ)
    if x <= d:
        y, m = (y+1,1) if m == 12 else (y,m+1)
        x = datetime.combine(date(y,m,calendar.monthrange(y,m)[1]), time(20), TZ)
    return x

def closed(plan, key):
    with connect() as c: return c.execute("SELECT 1 FROM closures WHERE plan=? AND draw_key=?", (plan,key)).fetchone() is not None

def remember(u):
    with connect() as c:
        c.execute("INSERT INTO users VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,name=excluded.name",
                  (u.id, u.username or "", u.first_name or "", now().isoformat()))

def menu():
    return InlineKeyboardMarkup([
      [InlineKeyboardButton("🎟 Buy ticket", callback_data="buy")],
      [InlineKeyboardButton("📋 My tickets", callback_data="tickets"), InlineKeyboardButton("🏆 Results", callback_data="results")],
      [InlineKeyboardButton("⏳ Countdown", callback_data="countdown"), InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

def plans_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{name} — {price} ETB", callback_data=f"plan:{p}")]
      for p,(name,price) in PLANS.items()] + [[InlineKeyboardButton("⬅️ Main menu", callback_data="home")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remember(update.effective_user)
    await update.effective_message.reply_text(
      "🇪🇹 Ethio Lottery Bot — DEMO\\n\\nDaily 100 ETB · Weekly 50 ETB · Monthly 50 ETB\\n"
      "Choose a six-digit number or let the bot pick one.\\n\\n⚠️ No money is collected; payments are not connected.",
      reply_markup=menu())

async def buy_cmd(update, context): await update.effective_message.reply_text("Choose a draw:", reply_markup=plans_menu())
async def tickets_cmd(update, context): await show_tickets(update, edit=False)
async def results_cmd(update, context): await show_results(update, edit=False)
async def countdown_cmd(update, context): await show_countdown(update, edit=False)

async def show_tickets(update, edit):
    uid = update.effective_user.id
    with connect() as c:
        rows = c.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 25", (uid,)).fetchall()
        results = {(r["plan"],r["draw_key"]):r["number"] for r in c.execute("SELECT * FROM results")}
    if rows:
        lines = ["📋 Your ticket history"]
        for r in rows:
            win = results.get((r["plan"],r["draw_key"]))
            suffix = " — 🏆 MATCH" if win == r["number"] else (" — no match" if win else "")
            lines.append(f'{PLANS[r["plan"]][0]} {r["draw_key"]}: {r["number"]} · {r["price"]} ETB [{r["status"]}]{suffix}')
        text = "\\n".join(lines)
    else: text = "No tickets yet. Tap Buy ticket to create a demo ticket."
    if edit: await update.callback_query.edit_message_text(text, reply_markup=menu())
    else: await update.effective_message.reply_text(text, reply_markup=menu())

async def show_results(update, edit):
    with connect() as c: rows = c.execute("SELECT * FROM results ORDER BY published DESC LIMIT 20").fetchall()
    text = "🏆 Published results\\n" + "\\n".join(f'{PLANS[r["plan"]][0]} {r["draw_key"]}: {r["number"]}' for r in rows) if rows else "No results published yet."
    if edit: await update.callback_query.edit_message_text(text, reply_markup=menu())
    else: await update.effective_message.reply_text(text, reply_markup=menu())

async def show_countdown(update, edit):
    d = now()
    text = "⏳ Next cutoffs (Ethiopia time)\\n" + "\\n".join(
      f'{name}: {next_time(p,d).strftime("%d %b %Y, %H:%M")}' for p,(name,_) in PLANS.items())
    if edit: await update.callback_query.edit_message_text(text, reply_markup=menu())
    else: await update.effective_message.reply_text(text, reply_markup=menu())

async def create_ticket(update, plan, key, number):
    uid = update.effective_user.id
    if closed(plan,key):
        await update.effective_message.reply_text("This draw is closed. Please choose another draw.")
        return
    remember(update.effective_user)
    try:
        with connect() as c:
            c.execute("INSERT INTO tickets(user_id,plan,draw_key,number,price,status,created) VALUES(?,?,?,?,?,'DEMO',?)",
              (uid,plan,key,number,PLANS[plan][1],now().isoformat()))
    except sqlite3.IntegrityError:
        await update.effective_message.reply_text("That number is already taken for this draw. Try another number.")
        return
    pending.pop(uid,None)
    await update.effective_message.reply_text(
      f"✅ Demo ticket created\\nDraw: {PLANS[plan][0]} {key}\\nNumber: {number}\\nPrice: {PLANS[plan][1]} ETB (simulated)\\nNo payment taken.",
      reply_markup=menu())

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); data=q.data
    if data=="home": await q.edit_message_text("Ethio Lottery Bot — DEMO. Choose an option:", reply_markup=menu())
    elif data=="buy": await q.edit_message_text("Choose a draw:", reply_markup=plans_menu())
    elif data.startswith("plan:"):
        p=data.split(":")[1]; k=key_for(p)
        if closed(p,k): await q.edit_message_text("This draw is closed.", reply_markup=menu()); return
        pending[update.effective_user.id]={"plan":p,"key":k}
        await q.edit_message_text(f"{PLANS[p][0]} draw {k} · {PLANS[p][1]} ETB\\nChoose number selection:",
          reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Random number",callback_data="random")],
            [InlineKeyboardButton("🔢 Enter my number",callback_data="manual")],
            [InlineKeyboardButton("Cancel",callback_data="home")]]))
    elif data=="random":
        item=pending.get(update.effective_user.id)
        if not item: await q.edit_message_text("Start again with /buy."); return
        for _ in range(100):
            n=f"{secrets.randbelow(1_000_000):06d}"
            with connect() as c: exists=c.execute("SELECT 1 FROM tickets WHERE plan=? AND draw_key=? AND number=?",(item["plan"],item["key"],n)).fetchone()
            if not exists: break
        else: await q.edit_message_text("No number found. Try again."); return
        await create_ticket(update,item["plan"],item["key"],n)
    elif data=="manual":
        if update.effective_user.id not in pending: await q.edit_message_text("Start again with /buy."); return
        pending[update.effective_user.id]["manual"]=True
        await q.edit_message_text("Send exactly six digits, e.g. 004217.")
    elif data=="tickets": await show_tickets(update,True)
    elif data=="results": await show_results(update,True)
    elif data=="countdown": await show_countdown(update,True)
    elif data=="help": await q.edit_message_text("Buy a ticket, choose daily/weekly/monthly, then select a number. Demo only; no payments or prizes.",reply_markup=menu())

async def text_message(update, context):
    item=pending.get(update.effective_user.id,{})
    if not item.get("manual"): return
    n=update.message.text.strip()
    if len(n)!=6 or not n.isdigit():
        await update.message.reply_text("Please enter exactly six digits, e.g. 004217."); return
    await create_ticket(update,item["plan"],item["key"],n)

def admin(uid): return uid in ADMINS
async def admin_help(update,context):
    if not admin(update.effective_user.id): await update.message.reply_text("Admin only."); return
    await update.message.reply_text("Admin commands:\\n/result daily 123456\\n/close daily\\n/open daily\\n/stats")

async def result_cmd(update,context):
    if not admin(update.effective_user.id): await update.message.reply_text("Admin only."); return
    if len(context.args)!=2 or context.args[0] not in PLANS or len(context.args[1])!=6 or not context.args[1].isdigit():
        await update.message.reply_text("Use /result daily 123456 (valid plans: daily, weekly, monthly)."); return
    p,n=context.args[0],context.args[1]; k=key_for(p)
    with connect() as c:
        c.execute("INSERT INTO results VALUES(?,?,?,?,?) ON CONFLICT(plan,draw_key) DO UPDATE SET number=excluded.number,admin_id=excluded.admin_id,published=excluded.published",
          (p,k,n,update.effective_user.id,now().isoformat()))
        winners=c.execute("SELECT user_id FROM tickets WHERE plan=? AND draw_key=? AND number=?",(p,k,n)).fetchall()
    await update.message.reply_text(f"Published {PLANS[p][0]} result for {k}: {n}. Matching demo tickets: {len(winners)}.")
    for w in winners:
        try: await context.bot.send_message(w["user_id"],f"🏆 Your demo number {n} matches the {PLANS[p][0]} result. No prizes are paid by this demo.")
        except Exception: pass

async def close_open(update,context):
    if not admin(update.effective_user.id): await update.message.reply_text("Admin only."); return
    if len(context.args)!=1 or context.args[0] not in PLANS: await update.message.reply_text("Use /close daily or /open daily."); return
    action=update.message.text.split()[0].lstrip("/"); p=context.args[0]; k=key_for(p)
    with connect() as c:
        if action=="close": c.execute("INSERT OR IGNORE INTO closures VALUES(?,?)",(p,k))
        else: c.execute("DELETE FROM closures WHERE plan=? AND draw_key=?",(p,k))
    await update.message.reply_text(f"{PLANS[p][0]} draw {k}: {action}d.")

async def stats(update,context):
    if not admin(update.effective_user.id): await update.message.reply_text("Admin only."); return
    with connect() as c:
        users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        tickets=c.execute("SELECT COUNT(*) n FROM tickets").fetchone()["n"]
    await update.message.reply_text(f"Players: {users}\\nTickets: {tickets}\\nMode: DEMO")

def main():
    if not TOKEN: raise SystemExit("Set BOT_TOKEN environment variable. See README.md.")
    init()
    app=Application.builder().token(TOKEN).build()
    for cmd,fn in [("start",start),("help",admin_help),("buy",buy_cmd),("tickets",tickets_cmd),("results",results_cmd),("countdowns",countdown_cmd),("admin",admin_help),("result",result_cmd),("close",close_open),("open",close_open),("stats",stats)]:
        app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()
