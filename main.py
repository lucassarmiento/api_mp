from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from database import Base, engine, SessionLocal
from models import Empresa, Evento
import logging
import time
import requests
import os
import json
from datetime import datetime

# Zona horaria Argentina
try:
    from zoneinfo import ZoneInfo
    AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    from datetime import timezone, timedelta
    AR_TZ = timezone(timedelta(hours=-3))

app = FastAPI()

log = logging.getLogger("webhook")

MP_TOKEN = os.getenv("MP_TOKEN")  # Token leido de variable de entorno

max_retries = 10
wait_seconds = 3

# ---- Inicialización de la base ----
for attempt in range(max_retries):
    try:
        print(f"🔄 Intentando conectar a la base de datos (intento {attempt + 1})...")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=engine)
        print("✅ Conexión exitosa y tablas creadas.")
        break
    except OperationalError:
        print(f"⚠️ Error de conexión, reintentando en {wait_seconds} segundos...")
        time.sleep(wait_seconds)
    except Exception as e:
        print("❌ Error inesperado durante la creación de tablas:", str(e))
        log.error("❌ Error creando tablas:", exc_info=e)
        break
else:
    print("❌ No se pudo conectar a la base después de varios intentos.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Funciones auxiliares ----
def obtener_payment_id(data: dict, request: Request = None):
    """
    Extrae el payment_id desde el payload o desde query params
    """
    if isinstance(data, dict):
        if data.get("topic") == "payment" and "id" in data:
            return str(data["id"])
        if data.get("type") == "payment" and "data" in data:
            return str(data["data"].get("id"))
        if data.get("topic") == "payment" and "resource" in data:
            return str(data["resource"])

    if request:
        args = request.query_params
        if args.get("topic") == "payment" and args.get("id"):
            return args.get("id")
        if args.get("type") == "payment" and args.get("data.id"):
            return args.get("data.id")
        if args.get("topic") == "payment" and args.get("resource"):
            return args.get("resource")

    return None


def get_payment_info(payment_id: str):
    """Consulta a MercadoPago para obtener info del pago"""
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
        print(f"[ERROR] No se pudo consultar pago: {payment_id}, status={resp.status_code}")
        return {
            "external_reference": None,
            "evento_json": "{}",
            "status": None,
            "merchant_order_id": None,
            "payment_id": payment_id
        }


# ---- Rutas principales ----
@app.post("/webhook/mp/{empresa_id}")
async def webhook_mp(empresa_id: str, request: Request):
    payload = await request.json()

    evento_id = payload.get("id")
    action = payload.get("action")
    type_ = payload.get("type")
    date_created = payload.get("date_created")

    # Sacar orden_id del payload
    orden_id = None
    if "data" in payload and isinstance(payload["data"], dict):
        orden_id = payload["data"].get("id")
    elif "resource" in payload:
        orden_id = payload["resource"].split("/")[-1]

    db = next(get_db())
    try:
        empresa = db.query(Empresa).filter_by(nombre=empresa_id).first()
        if not empresa:
            empresa = Empresa(nombre=empresa_id)
            db.add(empresa)
            db.commit()
            db.refresh(empresa)

        # Verificar si ya existe un evento con ese payment_id o merchant_order_id
        if orden_id:
            existente = db.query(Evento).filter(
                and_(
                    Evento.empresa_id == empresa.id,
                    or_(
                        Evento.payment_id == str(orden_id),
                        Evento.merchant_order_id == str(orden_id)
                    )
                )
            ).first()
            if existente:
                return {"status": "duplicado", "orden_id": orden_id}

        # Extraer payment_id
        payment_id = obtener_payment_id(payload, request)

        # Consultar detalles del pago si hay payment_id
        payment_status = None
        merchant_order_id = None
        external_reference = None
        if payment_id:
            payment_info = get_payment_info(payment_id)
            payment_status = payment_info["status"]
            merchant_order_id = payment_info["merchant_order_id"]
            external_reference = payment_info["external_reference"]

        # Fecha a grabar
        if type_ == "merchant_order":
            fecha_evento = datetime.now(AR_TZ).isoformat()
        else:
            fecha_evento = date_created

        # Crear nuevo evento
        nuevo_evento = Evento(
            orden_id=str(orden_id) if orden_id else None,
            evento_id=str(evento_id) if evento_id else None,
            action=action,
            type=type_,
            date_created=fecha_evento,
            payment_id=payment_id,
            status=payment_status,
            merchant_order_id=merchant_order_id if type_ == "payment" else (str(orden_id) if type_ == "merchant_order" else None),
            external_reference=external_reference,
            contenido=payload,
            empresa_id=empresa.id
        )
        db.add(nuevo_evento)
        db.commit()
        return {"status": "ok", "empresa": empresa.nombre, "evento_id": evento_id, "orden_id": orden_id}
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error interno de base de datos")


@app.get("/webhook/resultados/{empresa_id}/{order_id}")
def get_resultado(empresa_id: str, order_id: str):
    db = next(get_db())
    empresa = db.query(Empresa).filter_by(nombre=empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    evento = db.query(Evento).filter_by(empresa_id=empresa.id, orden_id=order_id).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return JSONResponse(content=evento.contenido)
