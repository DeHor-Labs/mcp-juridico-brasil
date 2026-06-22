"""Configuracao de runtime do mcp-juridico-brasil."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracoes carregadas de variaveis de ambiente ou arquivo .env."""

    # Ambiente
    juridico_env: str = "development"
    juridico_log_level: str = "INFO"

    # HTTP
    juridico_cache_ttl: int = 300
    juridico_rate_limit: int = 5
    juridico_http_timeout: float = 30.0
    juridico_max_retries: int = 3

    # DataJud CNJ (Fase 1)
    # Chave publica divulgada pelo proprio CNJ na wiki oficial do DataJud.
    # Nao e credencial privada - qualquer usuario pode obte-la sem cadastro.
    # ATENCAO: as credenciais das Fases 3/4 (juridico_provider_api_key,
    # dje_client_id, dje_client_secret) sao PRIVADAS e NAO devem ter default.
    # Ao rotacionar, definir DATAJUD_API_KEY no ambiente e remover este default.
    datajud_api_key: str = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
    datajud_base_url: str = "https://api-publica.datajud.cnj.jus.br"

    # Provider comercial (Fase 3 - opcional)
    # Valores aceitos: "judit" | "escavador" | "trackjud" | "" (desabilitado)
    juridico_provider_comercial: str = ""
    juridico_provider_api_key: str = ""

    # Domicilio Judicial Eletronico (Fase 4 - opcional)
    dje_client_id: str = ""
    dje_client_secret: str = ""
    dje_behalf_of_cpf: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

__all__ = ["Settings", "settings"]
