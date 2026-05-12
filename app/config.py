from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    photo_root: Path = Path("/photos")
    data_dir: Path = Path("/data")

    allowed_extensions: str = ".jpg,.jpeg,.png,.heic,.heif,.webp,.bmp,.tif,.tiff"
    scan_interval: int = 3600

    face_model: str = "buffalo_sc"
    auto_match_threshold: float = 0.62
    suggest_threshold: float = 0.45
    min_face_size: int = 50

    thumb_size: int = 480
    face_thumb_size: int = 160

    api_key: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "photo_recognition.db"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def faces_dir(self) -> Path:
        return self.data_dir / "faces"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}


settings = Settings()

for d in (settings.data_dir, settings.thumbs_dir, settings.faces_dir, settings.models_dir):
    d.mkdir(parents=True, exist_ok=True)
