from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host:     str = 'localhost'
    db_port:     int = 3306
    db_name:     str = 'robot_admin'
    db_user:     str = 'root'
    db_password: str = ''

    @property
    def database_url(self) -> str:
        return (
            f'mysql+pymysql://{self.db_user}:{self.db_password}'
            f'@{self.db_host}:{self.db_port}/{self.db_name}'
            f'?charset=utf8mb4'
        )

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


settings = Settings()
