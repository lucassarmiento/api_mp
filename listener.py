from flask import Flask, request, jsonify
import json
import requests
import pyodbc
from dotenv import load_dotenv
import os

# Cargar .env
load_dotenv()

app = Flask(__name__)

server   = os.getenv('SQL_SERVER')
database = os.getenv('SQL_DATABASE')
username = os.getenv('SQL_USER')
password = os.getenv('SQL_PASS')
driver   = os.getenv('SQL_DRIVER')
MP_TOKEN = os.getenv('ACCESS_TOKEN')

conn_str = (
    f"DRIVER={{{driver}}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={username};"
    f"PWD={password}"
)

def extract_merchant_order_id(resource_url):
    if resource_url and "merchant_orders/" in resource_url:
        return resource_url.split("merchant_orders/")[1].split("?")[0]
    if resource_url and resource_url.isdigit():
        return resource_url
    return None

def obtener_payment_id(data):
    if isinstance(data, dict):
        if data.get("topic") == "payment" and "id" in data:
            return str(data["id"])
        if data.get("type") == "payment" and "data" in data:
            return str(data["data"].get("id"))
        if data.get("topic") == "payment" and "resource" in data:
            return str(data["resource"])
    args = request.args
    if args:
        if args.get("topic") == "payment" and args.get("id"):
            return args.get("id")
        if args.get("type") == "payment" and args.get("data.id"):
            return args.get("data.id")
        if args.get("topic") == "payment" and args.get("resource"):
            return args.get("resource")
    return None

def get_payment_info(payment_id):
    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {"Authorization": f"Bearer {MP_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        merchant_order_id = None
        if "order" in data and isinstance(data["order"], dict):
            merchant_order_id = data["order"].get("id")
        return {
            "external_reference": data.get("external_reference"),
            "evento_json": json.dumps(data, ensure_ascii=False),
            "status": data.get("status"),
            "merchant_order_id": merchant_order_id,
            "payment_id": payment_id
        }
    else:
        print(f"[ERROR] No se pudo consultar pago: {payment_id}")
        return {
            "external_reference": None,
            "evento_json": "{}",
            "status": None,
            "merchant_order_id": None,
            "payment_id": payment_id
        }

def insertar_unico(consulta_existencia, params_existencia, consulta_insert, params_insert):
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SET ARITHABORT ON;")
        cursor.execute(consulta_existencia, params_existencia)
        row = cursor.fetchone()
        if row:
            print(f"[SKIP] Ya existe este evento en la base.")
        else:
            cursor.execute(consulta_insert, params_insert)
            conn.commit()
            print(f"[OK] Insertado.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Insertando en SQL: {e}")

@app.route("/webhook", methods=["POST"])
def mp_webhook():
    data = request.json
    payment_id = obtener_payment_id(data)
    merchant_order_id = None
    external_reference = None
    status = None

    # --- Caso merchant_order ---
    if data and data.get("topic") == "merchant_order" and "resource" in data:
        merchant_order_id = extract_merchant_order_id(data["resource"])
        status = "orden creada"
        evento_json = json.dumps(data, ensure_ascii=False)
        insertar_unico(
            "SELECT id FROM mp_pagos WHERE merchant_order_id = ? AND payment_id IS NULL",
            (merchant_order_id,),
            """
            INSERT INTO mp_pagos (payment_id, merchant_order_id, fecha, external_reference, status, evento_json)
            VALUES (?, ?, GETDATE(), ?, ?, ?)
            """,
            (None, merchant_order_id, None, status, evento_json)
        )

    # --- Caso payment ---
    if payment_id:
        info = get_payment_info(payment_id)
        merchant_order_id = info.get("merchant_order_id")
        external_reference = info.get("external_reference")
        evento_json = info.get("evento_json")
        status = info.get("status")
        insertar_unico(
            "SELECT id FROM mp_pagos WHERE payment_id = ?",
            (payment_id,),
            """
            INSERT INTO mp_pagos (payment_id, merchant_order_id, fecha, external_reference, status, evento_json)
            VALUES (?, ?, GETDATE(), ?, ?, ?)
            """,
            (payment_id, merchant_order_id, external_reference, status, evento_json)
        )

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(port=8001)
