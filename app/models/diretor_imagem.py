from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class DiretorImagem(Base):
    __tablename__ = "diretores_imagem"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    nome = Column(String(255), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)  # TASK 15: Soft delete

    # v3.2 — vincula o cadastro do diretor a um usuário com login, para que o
    # próprio diretor de imagem consiga acessar e preencher os seus relatórios.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True)

    user = relationship("User", foreign_keys=[user_id])

    @property
    def user_email(self) -> str:
        return self.user.email if self.user else None
