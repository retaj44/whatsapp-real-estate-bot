import os
import sqlite3
import requests
from flask import Flask, request, make_response

app = Flask(__name__)

VERIFY_TOKEN = "my_custom_secure_verify_token_123"
WHATSAPP_TOKEN = "EAAZA9dewPp6cBSHGcLjSevu0za3FBWdV9Ya8WZAR51Brmu2Vi4D2qA7yMzkeG92XjCm11VBQBxSenv5hBBeA1o89ZAFrtmdwzRhGqgZBAGHBXDs9XrbYoGOZA0ceqdaI0WKwCpVPJbfd7QeAPcqCVoYPyZCDZCGhX1KRyNIpoZBK0mw8WSVQ14ZAgIO2KVYU63FK8YnlgrMZCNPWgiQTz9bktNDI5pBt08SGZB5V8BKvW6dUxxnuM5fsoWfULXof9O3smz9hxR4mKwVRj9LdmtwstAwg8oizQZDZD"
PHONE_NUMBER_ID = "115440459776666"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ضع_مفتاح_OPENAI_هنا")

# ==========================================
# 🛠️ دمج قواعد البيانات
# ==========================================
def get_all_properties_context():
    """استخراج العقارات المتاحة لإعطائها كخلفية للذكاء الاصطناعي"""
    try:
        conn = sqlite3.connect('real_estate.db')
        cursor = conn.cursor()
        cursor.execute("SELECT title, type, city, district, price, rooms, space_sqm FROM properties WHERE status = 'متاح'")
        results = cursor.fetchall()
        conn.close()

        if not results:
            return "لا توجد عقارات مسجلة حالياً."

        context = "العقارات المتاحة حالياً في القاعدة:\n"
        for p in results:
            context += f"- {p[0]} ({p[1]}) في {p[2]} - حي {p[3]} | السعر: {p[4]:,} ريال | الغرف: {p[5]} | المساحة: {p[6]} م²\n"
        return context
    except Exception as e:
        print("❌ Error reading DB:", e)
        return ""

def save_chat_history(phone_number, role, content):
    """حفظ سجل المحادثة"""
    try:
        conn = sqlite3.connect('real_estate.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO conversation_history (phone_number, role, content) VALUES (?, ?, ?)",
                       (phone_number, role, content))
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ Error saving history:", e)

# ==========================================
# 🌐 المسارات و الـ Webhooks
# ==========================================
@app.route('/', methods=['GET'])
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("✅ WEBHOOK_VERIFIED SUCCESS!")
        response = make_response(challenge, 200)
        response.headers['ngrok-skip-browser-warning'] = 'true'
        return response
    return "Verification failed", 403

@app.route('/', methods=['POST'])
@app.route('/webhook', methods=['POST'])
def webhook_listener():
    data = request.get_json()
    try:
        entry = data.get('entry', [])[0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages = value.get('messages', [])

        if messages:
            message = messages[0]
            from_number = message.get('from')
            message_body = message.get('text', {}).get('body', '')

            print(f"\n📱 Message from {from_number}: {message_body}")
            
            # حفظ رسالة العميل
            save_chat_history(from_number, 'user', message_body)

            # توليد الرد بالاستعانة بالـ DB
            ai_reply = generate_ai_response(message_body)
            print(f"🤖 AI Response: {ai_reply}")

            # حفظ رد الـ AI
            save_chat_history(from_number, 'assistant', ai_reply)

            # إرسال الرد للواتساب
            send_whatsapp_message(from_number, ai_reply)

    except Exception as e:
        print(f"⚠️ Error processing webhook: {e}")

    return "EVENT_RECEIVED", 200

# ==========================================
# 🤖 توليد الرد والتواصل مع Meta
# ==========================================
def generate_ai_response(user_message):
    db_context = get_all_properties_context()
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = f"""
    أنت مساعد عقاري ذكي ومحترف في السوق السعودي.
    اعتمد في إجابتك على قراءة القائمة التالية من العقارات المتاحة فقط وإعطاء تفاصيلها للعميل عند الطلب:
    
    {db_context}
    
    إذا طلب العميل عقاراً غير موجود بالقائمة، أبلغه بلباقة بعدم توفره حالياً واعرض عليه خيارات قريبة.
    """

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return "أهلاً بك! كيف يمكنني مساعدتك في طلباتك العقارية اليوم؟"
    except Exception as e:
        print("❌ OpenAI Exception:", e)
        return "أهلاً بك! يسعدني خدمتك."

def send_whatsapp_message(recipient_number, message_text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "text",
        "text": {"body": message_text}
    }
    response = requests.post(url, json=payload, headers=headers)
    print("📤 Send Message Status:", response.status_code)
    return response.json()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)