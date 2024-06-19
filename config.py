from os import environ, urandom
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = urandom(32)
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://{}:{}@{}:{}/{}".format(
        environ["SUPABASE_USER"],
        environ["SUPABASE_PASSWORD"],
        environ["SUPABASE_HOST"],
        environ["SUPABASE_PORT"],
        environ["SUPABASE_NAME"],
    )
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
