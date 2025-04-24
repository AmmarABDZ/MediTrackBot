import telebot
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

current_users = {}

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Welcome! Enter your pharmacist license number.")

@bot.message_handler(func=lambda m: m.chat.id not in current_users)
def auth_pharmacist(message):
    license_number = message.text.strip()
    cur.execute("SELECT * FROM pharmacists WHERE license_number = %s", (license_number,))
    result = cur.fetchone()
    if result:
        cur.execute("UPDATE pharmacists SET telegram_id = %s WHERE license_number = %s",
                    (message.chat.id, license_number))
        conn.commit()
        current_users[message.chat.id] = result
        bot.send_message(message.chat.id, "Logged in successfully.")
    else:
        bot.send_message(message.chat.id, "License not found. Access denied.")

@bot.message_handler(commands=['dispense'])
def dispense(message):
    if message.chat.id not in current_users:
        return bot.send_message(message.chat.id, "You must be logged in.")
    msg = bot.send_message(message.chat.id, "Enter patient national ID:")
    bot.register_next_step_handler(msg, get_drug_name)

def get_drug_name(message):
    patient_id = message.text.strip()
    cur.execute("SELECT id FROM patients WHERE national_id = %s", (patient_id,))
    patient = cur.fetchone()
    if not patient:
        cur.execute("INSERT INTO patients (national_id) VALUES (%s) RETURNING id", (patient_id,))
        patient_id_db = cur.fetchone()[0]
    else:
        patient_id_db = patient[0]
    msg = bot.send_message(message.chat.id, "Enter drug name:")
    bot.register_next_step_handler(msg, lambda m: save_prescription(m, patient_id_db))

def save_prescription(message, patient_id_db):
    drug = message.text.strip()
    pharmacist = current_users[message.chat.id]
    cur.execute("INSERT INTO prescriptions (patient_id, pharmacist_id, drug_name) VALUES (%s, %s, %s)",
                (patient_id_db, pharmacist[0], drug))
    conn.commit()
    bot.send_message(message.chat.id, f"Prescription for {drug} saved.")

@bot.message_handler(commands=['check'])
def check(message):
    if message.chat.id not in current_users:
        return bot.send_message(message.chat.id, "You must be logged in.")
    msg = bot.send_message(message.chat.id, "Enter patient national ID:")
    bot.register_next_step_handler(msg, send_history)

def send_history(message):
    patient_id = message.text.strip()
    cur.execute("SELECT id FROM patients WHERE national_id = %s", (patient_id,))
    patient = cur.fetchone()
    if not patient:
        return bot.send_message(message.chat.id, "No history found.")
    patient_id_db = patient[0]
    cur.execute("SELECT drug_name, prescription_date FROM prescriptions WHERE patient_id = %s ORDER BY prescription_date DESC LIMIT 5", (patient_id_db,))
    records = cur.fetchall()
    if not records:
        bot.send_message(message.chat.id, "No history found.")
    else:
        history = "\n".join([f"{r[0]} - {r[1].strftime('%Y-%m-%d')}" for r in records])
        bot.send_message(message.chat.id, f"Recent prescriptions:\n{history}")

@bot.message_handler(commands=['logout'])
def logout(message):
    current_users.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Logged out.")

bot.infinity_polling()
