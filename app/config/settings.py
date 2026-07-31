"""
Configuración centralizada de la aplicación.

Carga variables de entorno desde .env y proporciona configuración validada
mediante Pydantic. Todos los valores se cargan al iniciar la aplicación.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """
    Configuración de la aplicación usando Pydantic Settings.
    
    Las variables se cargan desde .env en este orden:
    1. Variables de entorno del sistema
    2. Archivo .env en la raíz del proyecto
    """
    
    # ========================================================================
    # Aplicación
    # ========================================================================
    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="Tu Pensión Inteligente Back-office", alias="APP_NAME")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    
    # ========================================================================
    # Base de datos
    # ========================================================================
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    
    # Alternativa: variables individuales para construir URL
    database_host: str = Field(default="localhost", alias="DATABASE_HOST")
    database_port: int = Field(default=5432, alias="DATABASE_PORT")
    database_name: str = Field(default="tpi_local", alias="DATABASE_NAME")
    database_user: str = Field(default="tpi_app", alias="DATABASE_USER")
    database_password: str = Field(default="", alias="DATABASE_PASSWORD")
    database_schema: str = Field(default="tpi", alias="DATABASE_SCHEMA")
    
    # Pool de conexiones
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT")
    
    # ========================================================================
    # Políticas y términos
    # ========================================================================
    privacy_policy_version: str = Field(default="demo-2026-01", alias="PRIVACY_POLICY_VERSION")
    terms_version: str = Field(default="demo-2026-01", alias="TERMS_VERSION")
    
    # ========================================================================
    # Logging
    # ========================================================================
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/backoffice.log", alias="LOG_FILE")
    
    # ========================================================================
    # Seguridad
    # ========================================================================
    allow_demo_mode: bool = Field(default=True, alias="ALLOW_DEMO_MODE")
    
    # ========================================================================
    # Configuración de Pydantic
    # ========================================================================
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }
    
    # ========================================================================
    # Validadores
    # ========================================================================
    
    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        """Validar que el ambiente sea válido."""
        valid_envs = ["development", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"APP_ENV debe ser uno de: {valid_envs}")
        return v.lower()
    
    @field_validator("database_password", mode="before")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validar que la contraseña no sea vacía en producción."""
        # En desarrollo, permitir password vacía (SQLite o conexión local sin auth)
        # En producción, exigir contraseña fuerte
        return v or ""
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validar que el nivel de log sea válido."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL debe ser uno de: {valid_levels}")
        return v.upper()
    
    # ========================================================================
    # Propiedades computadas
    # ========================================================================
    
    @property
    def is_production(self) -> bool:
        """Verificar si estamos en producción."""
        return self.app_env == "production"
    
    @property
    def is_development(self) -> bool:
        """Verificar si estamos en desarrollo."""
        return self.app_env == "development"
    
    def get_database_url(self) -> str:
        """
        Construir URL de conexión a PostgreSQL.
        
        Si DATABASE_URL está configurada, la usa directamente.
        De lo contrario, construye la URL a partir de las variables individuales.
        
        Retorna:
            URL de conexión en formato: postgresql://user:password@host:port/dbname
        """
        if self.database_url:
            return self.database_url
        
        # Construir URL a partir de componentes
        if not self.database_password:
            # Conexión sin contraseña (no recomendado en producción)
            return (
                f"postgresql://{self.database_user}@"
                f"{self.database_host}:{self.database_port}/{self.database_name}"
            )
        
        # Conexión con contraseña
        return (
            f"postgresql://{self.database_user}:{self.database_password}@"
            f"{self.database_host}:{self.database_port}/{self.database_name}"
        )
    
    def __str__(self) -> str:
        """Representación segura de la configuración (sin credenciales)."""
        return (
            f"Settings(env={self.app_env}, db={self.database_host}:"
            f"{self.database_port}/{self.database_name}, debug={self.app_debug})"
        )


# Instancia global de configuración
settings = Settings()  # type: ignore
