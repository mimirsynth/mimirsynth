from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)  # claim "sub" del OIDC
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # administrador de la instancia
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")  # nombre a mostrar elegido por la persona; vacío = el del proveedor de identidad
    picture_url: Mapped[str] = mapped_column(Text, default="")  # claim «picture» del proveedor de identidad
    avatar_ref: Mapped[str] = mapped_column(Text, default="")  # avatar subido (ruta relativa al almacén de ficheros)
    avatar_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)  # sube al «cerrar todas las sesiones»
    password_hash: Mapped[str] = mapped_column(Text, default="")  # argon2id; vacío = sin contraseña (solo entra por un proveedor externo)
    status: Mapped[str] = mapped_column(String(12), default="active")  # invited | active | disabled | deleted (anonimizado: conserva la historia de propuestas y auditoría)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)  # contraseña temporal puesta por un administrador
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    totp_secret: Mapped[str] = mapped_column(Text, default="")  # secreto TOTP sellado (secretbox); con totp_enabled falso es una alta a medias
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(5), default="")  # idioma elegido (es, en…); vacío = el de la instancia
    totp_last_step: Mapped[int] = mapped_column(Integer, default=0)  # último intervalo de 30 s aceptado: un código no se puede reutilizar


class Identity(Base):
    """Identidad externa (OIDC) vinculada a un usuario: una persona puede tener contraseña propia y además uno o varios proveedores."""
    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("provider", "sub"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="oidc")
    sub: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OidcProvider(Base):
    """Proveedor de identidad externo (OIDC). Cada uno trae su propia política de alta y de roles por grupo."""
    __tablename__ = "oidc_providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)  # va en las URLs de inicio de sesión y de retorno, y en identities.provider
    name: Mapped[str] = mapped_column(String(80))  # texto del botón de inicio de sesión
    issuer: Mapped[str] = mapped_column(Text, default="")
    client_id: Mapped[str] = mapped_column(Text, default="")
    client_secret: Mapped[str] = mapped_column(Text, default="")  # sellado (secretbox)
    scopes: Mapped[str] = mapped_column(String(255), default="openid profile email")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trust_unverified_email: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_provision: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_domains: Mapped[str] = mapped_column(Text, default="")  # dominios (coma) permitidos para el alta automática
    groups_claim: Mapped[str] = mapped_column(String(64), default="groups")
    admin_group: Mapped[str] = mapped_column(String(255), default="")
    group_roles: Mapped[str] = mapped_column(Text, default="")  # grupo=brain:rol, ...
    default_roles: Mapped[str] = mapped_column(Text, default="")  # brain:rol, ... que recibe una vez quien se da de alta solo (reader o contributor)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RoleGrant(Base):
    """Rol concedido por un grupo del proveedor de identidad. Permite retirarlo cuando la persona deja el grupo sin tocar nunca lo que dio un administrador a mano."""
    __tablename__ = "role_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    group: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(8))  # admin (administrador de la instancia) | member (rol en un brain)
    brain_id: Mapped[int | None] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="")  # rol concedido (member)
    previous_role: Mapped[str] = mapped_column(String(16), default="")  # rol que tenía antes (vacío = no era miembro)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RecoveryCode(Base):
    """Código de recuperación del doble factor: de un solo uso, se guarda solo el hash."""
    __tablename__ = "recovery_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Passkey(Base):
    """Llave de acceso (WebAuthn) de una cuenta: la clave pública y el contador; la privada nunca sale del autenticador."""
    __tablename__ = "passkeys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True)  # base64url
    public_key: Mapped[str] = mapped_column(Text)  # COSE, base64url
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(80), default="")
    transports: Mapped[list] = mapped_column(JSON, default=list)
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)  # sincronizada (gestor de contraseñas, nube del sistema)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserToken(Base):
    """Enlace de un solo uso para aceptar una invitación o restablecer la contraseña; se guarda solo el hash."""
    __tablename__ = "user_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(12))  # invite | reset
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Brain(Base):
    __tablename__ = "brains"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    graph_name: Mapped[str] = mapped_column(String(255))  # grafo en el GraphStore
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    secret_mode: Mapped[str] = mapped_column(String(8), default="mask", server_default="mask")  # mask | block | warn (ver secretguard)
    secret_allow: Mapped[str] = mapped_column(Text, default="", server_default="")  # excepciones del detector, una por línea
    retention: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # days per kind of data (#137); empty: the instance's
    members: Mapped[list["Membership"]] = relationship(back_populates="brain", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "brain_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    user: Mapped[User] = relationship()
    brain: Mapped[Brain] = relationship(back_populates="members")


class BrainGrant(Base):
    """Concesión de lectura: el brain de origen deja que el brain de destino lo consulte (solo lectura, acotada, revocable)."""
    __tablename__ = "brain_grants"
    __table_args__ = (UniqueConstraint("source_brain_id", "target_brain_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"))
    target_brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(8), default="both")  # graph (hechos y episodios) | docs (documentos) | both
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[Brain] = relationship(foreign_keys=[source_brain_id])
    target: Mapped[Brain] = relationship(foreign_keys=[target_brain_id])


class Audit(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    brain_id: Mapped[int | None] = mapped_column(ForeignKey("brains.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class RateHit(Base):
    """Intento registrado por el limitador de peticiones (compartido entre procesos y reinicios)."""
    __tablename__ = "rate_hits"
    __table_args__ = (Index("ix_rate_hits_key_at", "key", "at"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AppSetting(Base):
    """Ajuste de la instancia editable desde Administración → Ajustes. Solo guarda lo que se ha cambiado: sin fila, manda el valor por defecto (variable de entorno o valor de fábrica)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)  # {"v": valor}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ApiToken(Base):
    """Token de API para agentes y MCP: acotado a un brain y con rol máximo; se guarda solo el hash."""
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))  # tope; el efectivo es min(rol del usuario, este)
    prefix: Mapped[str] = mapped_column(String(12))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    news_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # última llamada a `whats_new` sin fecha (MCP)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # empty: never expires (#133)
    scopes: Mapped[list | None] = mapped_column(JSON, nullable=True)  # recall | documents | propose; empty: all of them
    replaced_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # the token that took its place when it was rotated
    expiry_warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship()


class Proposal(Base):
    """Aportación pendiente de entrar al grafo (cuarentena). pending -> approved|rejected; approved -> ingested|failed."""
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="text")  # text | message | json
    source_description: Mapped[str] = mapped_column(String(255), default="")
    reference_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)  # 0..1 declarada por el autor/agente
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")  # nota escrita por el revisor humano
    review_kind: Mapped[str] = mapped_column(String(16), default="")  # human | direct (curador al enviar) | decider
    decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # detalle del triaje del decisor
    ingest_error: Mapped[str] = mapped_column(Text, default="")
    ingest_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # tipos usados y relaciones fuera de la ontología
    secret_findings: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{rule, start, end, action}] sobre el texto guardado; nunca el valor
    kind: Mapped[str] = mapped_column(String(16), default="memory", server_default="memory")  # memory | correction (#109)
    correction: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the correction of a fact: see corrections.py
    episode_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # its text went with the retention period (#137)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    author: Mapped[User] = relationship(foreign_keys=[author_id])


class LlmEngine(Base):
    """Motor LLM (endpoint OpenAI-compatible) usado para extraer hechos al ingerir. La clave se guarda cifrada."""
    __tablename__ = "llm_engines"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(255))
    small_model: Mapped[str] = mapped_column(String(255), default="")
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmbeddingEngine(Base):
    """Motor de embeddings (endpoint OpenAI-compatible). Modelo y dimensión son inmutables: los vectores guardados dependen de ellos."""
    __tablename__ = "embedding_engines"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(255))
    dim: Mapped[int] = mapped_column()
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DecisionEngine(Base):
    """Decisor: modelo de decisión cerrada (elige una opción etiquetada con letra y da probabilidades por logprobs)."""
    __tablename__ = "decision_engines"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(255))
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    threshold: Mapped[float] = mapped_column(default=0.8)  # confianza mínima para actuar sin revisión humana
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BrainOntology(Base):
    """Ontología de un brain: tipos de entidad y de relación (y su mapa) que guían la extracción al ingerir."""
    __tablename__ = "brain_ontologies"
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class DocSource(Base):
    """Fuente de la memoria documental de un brain (subidas, directorio de archivos, wiki)."""
    __tablename__ = "doc_sources"
    __table_args__ = (UniqueConstraint("brain_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # upload | directory | wiki
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # los secretos van cifrados con secretbox
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)  # minutos; vacío = solo manual
    status: Mapped[str] = mapped_column(String(16), default="idle")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    """Documento indexado. El original vive en el almacén de ficheros; aquí solo su referencia y metadatos (los trozos y vectores, en doc_chunks)."""
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("doc_sources.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), default="")
    filename: Mapped[str] = mapped_column(String(500), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    mime: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    norm_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # huella del texto extraído (duplicados, #117)
    storage_ref: Mapped[str] = mapped_column(Text, default="")  # ruta del original relativa al almacén
    text_ref: Mapped[str] = mapped_column(Text, default="")  # ruta del texto normalizado (sobre el que apuntan char_start/char_end)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending | indexing | active | error | deleted
    error: Mapped[str] = mapped_column(Text, default="")
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VocabAlias(Base):
    """Alias de vocabulario por brain: variante -> canónico (kind='relation'). No destructivo: se aplica al leer."""
    __tablename__ = "vocab_aliases"
    __table_args__ = (UniqueConstraint("brain_id", "kind", "alias"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="relation")
    alias: Mapped[str] = mapped_column(String(200))
    canonical: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class VocabOp(Base):
    """Cambio de vocabulario aplicado (tipos de entidad). Guarda lo necesario para deshacerlo."""
    __tablename__ = "vocab_ops"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # type.create | type.edit | type.delete | type.rename | type.merge
    summary: Mapped[str] = mapped_column(String(300), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="applied")  # applied | reverted
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RetypeSuggestion(Base):
    """Propuesta de cambio de tipo de una entidad del grafo (corrector de tipos con decisor). Reversible: guarda el tipo anterior."""
    __tablename__ = "retype_suggestions"
    __table_args__ = (UniqueConstraint("brain_id", "entity_uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    entity_uuid: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    current_type: Mapped[str] = mapped_column(String(64), default="")
    suggested_type: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending | doubtful | same | applied | rejected | reverted
    previous_type: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(200), default="")  # por qué es dudosa (status=doubtful)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    """Trabajo en segundo plano (ingesta, indexación, reescaneo…). Registro central: estado, progreso, salida y reintentos."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int | None] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)  # queued | running | done | failed | cancelled
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(300), default="")  # paso actual
    log: Mapped[list] = mapped_column(JSON, default=list)  # últimas líneas [{t, msg}]
    error: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)  # intentos dentro de la ejecución (reintentos por límite de tasa, etc.)
    retry_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocRoot(Base):
    """Carpeta del servidor autorizada como raíz de fuentes de documentos (siempre bajo MIMIRSYNTH_DOC_ROOTS_BASE, montada en solo lectura)."""
    __tablename__ = "doc_roots"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    path: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NotifyChannel(Base):
    """Canal de salida de las notificaciones (email, ntfy, Gotify, webhook, Telegram). Lo configura el administrador de la instancia; el secreto va sellado."""
    __tablename__ = "notify_channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # email | ntfy | gotify | webhook | telegram
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # lo que no es secreto: URL, tema, destinatarios…
    secret: Mapped[str] = mapped_column(Text, default="")  # token / clave HMAC, sellado con secretbox
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_severity: Mapped[str] = mapped_column(String(8), default="warning")  # info | warning | critical
    events: Mapped[list] = mapped_column(JSON, default=list)  # eventos que recibe; vacío = todos
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):
    """Aviso del sistema: aparece en la campana de la interfaz y se envía por los canales. Un problema que se repite se agrupa en una sola fila."""
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_event_key", "event", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    event: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(8), default="warning")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    brain_id: Mapped[int | None] = mapped_column(ForeignKey("brains.id", ondelete="SET NULL"), nullable=True)
    key: Mapped[str] = mapped_column(String(120), default="")  # identifica el problema concreto (p. ej. el motor o la fuente) para agrupar y para resolverlo
    count: Mapped[int] = mapped_column(Integer, default=1)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotifyDelivery(Base):
    """Envío de un aviso por un canal, con reintentos."""
    __tablename__ = "notify_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("notify_channels.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="alert")  # alert | recovery
    status: Mapped[str] = mapped_column(String(8), default="pending")  # pending | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    next_try_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    notification: Mapped[Notification] = relationship()
    channel: Mapped[NotifyChannel] = relationship()


class NotifyRead(Base):
    """Hasta qué aviso ha leído cada persona (la campana cuenta los posteriores)."""
    __tablename__ = "notify_reads"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_id: Mapped[int] = mapped_column(Integer, default=0)


class RefQuery(Base):
    """Consulta de referencia (#115): una pregunta del brain con lo que su recall debe traer y lo que no, para medir la calidad del
    recall antes y después de cambiar el umbral, el modelo de embeddings o el decisor."""
    __tablename__ = "ref_queries"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    expect: Mapped[list] = mapped_column(JSON, default=list)  # [{text, kind}] que deben aparecer; kind: any | fact | chunk | doc
    avoid: Mapped[list] = mapped_column(JSON, default=list)   # [{text, kind}] que no deben aparecer (falsos positivos conocidos)
    docs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # la sección de documentos debe salir (True), no salir (False) o da igual
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RefRun(Base):
    """Una ejecución de las consultas de referencia de un brain, con sus parámetros (vacíos = los ajustes en vigor) y el resultado."""
    __tablename__ = "ref_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued | running | done | error
    reason: Mapped[str] = mapped_column(String(32), default="manual")  # manual | embedding.switched
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # min_sim, docs, facts, chunks: lo que se simula
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConflictDismissal(Base):
    """A group of possible contradictions a curator marked as «not a contradiction» (#113 follow-up). It stays hidden while its
    facts are the same ones; a new fact in the group shows it again."""
    __tablename__ = "conflict_dismissals"
    id: Mapped[int] = mapped_column(primary_key=True)
    brain_id: Mapped[int] = mapped_column(ForeignKey("brains.id", ondelete="CASCADE"), index=True)
    source_uuid: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(255), default="")
    relation: Mapped[str] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(255), default="Entity")
    facts: Mapped[list] = mapped_column(JSON, default=list)  # uuids of the facts the curator looked at
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
