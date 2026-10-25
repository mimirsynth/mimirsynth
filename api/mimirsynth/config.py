"""Configuración (variables MIMIRSYNTH_*). El nombre visible vive solo aquí."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MIMIRSYNTH_", env_file=".env", extra="ignore")

    static_dir: str = ""  # directorio del build de la web; si existe se sirve en /
    cors_origins: str = "*"

    # Grafo (conector GraphStore: hoy FalkorDB)
    falkor_host: str = "localhost"
    falkor_port: int = 6379
    default_graph: str = "default"
    bootstrap_graphs: str = ""  # grafos existentes a adoptar como brains al arrancar: "docs:Docs,otro"

    # Embeddings (conector EmbeddingProvider: endpoint OpenAI-compatible). Deben coincidir con los de Graphiti.
    embedding_base_url: str = "http://localhost:11434/v1"
    embedding_model: str = "nomic-embed-text"
    embedding_api_key: str = ""
    embedding_dim: int = 768
    ingest_concurrency: int = 2  # llamadas simultáneas al LLM por ingesta (graphiti SEMAPHORE_LIMIT); bajo para respetar el límite de tasa del gateway
    ingest_retries: int = 4  # intentos si el LLM responde con límite de tasa
    llm_base_url: str = ""  # OpenAI-compatible; vacío = ingesta desactivada
    llm_api_key: str = ""
    llm_model: str = ""
    llm_small_model: str = ""  # opcional; por defecto llm_model
    jobs_keep_days: int = 60  # días que se conservan los trabajos terminados
    jobs_keep_scheduled_days: int = 7  # días que se conservan los reescaneos programados terminados sin incidencias (son ruido: uno cada pocos minutos por fuente)
    doc_store: str = "/data/documents"  # volumen con los originales de la memoria documental (la BD solo guarda referencias y trozos)
    doc_roots_base: str = "/sources"  # las raíces de fuentes de documentos solo pueden estar bajo esta carpeta (un único bind de solo lectura en el contenedor)
    doc_max_mb: int = 2048  # tamaño máximo de un fichero subido
    doc_part_mb: int = 64  # tamaño máximo de cada parte de una subida
    doc_text_max_mb: int = 100  # texto extraído máximo por documento
    doc_min_similarity: float = 0.66  # coseno mínimo para que un pasaje entre en el recall (calibrado con nomic-embed-text; depende del modelo de embeddings)
    doc_passages: int = 2  # pasajes documentales máximos en el recall
    doc_search_timeout: float = 0.6  # segundos máximos de la búsqueda documental dentro del recall
    index_sync_minutes: int = 10  # 0 = sin sincronización periódica del índice de texto

    # Plano de control
    database_url: str = "sqlite:///./mimirsynth.db"  # en producción: postgresql+psycopg://...

    # Identidad
    auth_mode: str = "local"  # local (cuentas propias, más OIDC si se configura) | off (solo desarrollo: sin login, todo el mundo es admin local)
    session_secret: str = "change-me"
    cookie_secure: bool = False
    public_url: str = ""  # URL pública para el redirect de OIDC, p. ej. https://mimirsynth.example.com
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid profile email"
    account_url: str = ""  # página de tu proveedor de identidad donde se gestionan contraseña, llaves de acceso y doble factor (se enlaza desde «Mi cuenta»)
    smtp_host: str = ""  # correo saliente (invitaciones y recuperación de contraseña); vacío = sin correo
    smtp_port: int = 587
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    password_min_length: int = 12
    login_max_attempts: int = 5  # intentos fallidos seguidos antes de bloquear la cuenta
    lockout_minutes: int = 15
    invite_days: int = 7  # validez de un enlace de invitación o recuperación
    oidc_trust_unverified_email: str = "no"
    oidc_auto_provision: str = "no"  # "yes": quien entra por OIDC con email verificado de un dominio permitido se da de alta solo
    oidc_allowed_domains: str = ""  # dominios (coma) permitidos para el alta automática
    oidc_groups_claim: str = "groups"  # claim del proveedor con los grupos de la persona
    oidc_admin_group: str = ""  # grupo cuyos miembros son administradores de la instancia
    oidc_group_roles: str = ""  # grupo=brain:rol, ... (p. ej. curadores=docs:curator)
    default_language: str = "es"  # idioma de la interfaz y de los correos cuando la persona no ha elegido uno
    require_2fa: str = "no"  # "yes": quien entra con contraseña debe activar el doble factor
    admin_emails: str = ""  # emails (coma) que son administradores de la instancia al iniciar sesión


settings = Settings()
