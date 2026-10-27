from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    dry_run: bool = True
    db_path: str = 'orders.sqlite3'
    mapping_path: str = 'data/plu_mapping.json'
    uber_client_id: str = ''
    uber_client_secret: str = ''
    uber_scopes: str = 'eats.order eats.store.orders.read'
    auto_accept_uber: bool = False
    enable_uber_decisions: bool = False
    admin_token: str = ''
    uber_store_id: str = ''
    mplus_wsdl: str = ''
    mplus_username: str = ''
    mplus_password: str = ''
    mplus_branch: int = 1
    mplus_relation: int = 1
    mplus_employee: int = 1
    mplus_vat_code: int = 2
    mplus_vat_method: str = 'VAT-METHOD-INCLUSIVE'
    mplus_delivery_method: str = ''
