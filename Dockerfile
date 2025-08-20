# Imagen base de Python 3.11
FROM python:3.11

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Copiar dependencias y instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Exponer el puerto de FastAPI
EXPOSE 10000

# Comando de inicio con Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
