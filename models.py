from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base

class Empresa(Base):
    __tablename__ = "empresas"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True)
    eventos = relationship("Evento", back_populates="empresa")


class Evento(Base):
    __tablename__ = "eventos"
    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(String, index=True)
    evento_id = Column(String, index=True)
    action = Column(String, index=True)
    type = Column(String, index=True)
    date_created = Column(String)
    payment_id = Column(String, index=True)
    merchant_order_id = Column(String, nullable=True)
    external_reference = Column(String, nullable=True)
    status = Column(String, nullable=True)
    contenido = Column(JSONB)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))
    empresa = relationship("Empresa", back_populates="eventos")

    # 🚨 Índices únicos
    __table_args__ = (
        UniqueConstraint("empresa_id", "merchant_order_id", name="uq_empresa_merchant_order"),
        UniqueConstraint("empresa_id", "payment_id", name="uq_empresa_payment"),
    )
