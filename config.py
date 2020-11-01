from dataclasses import dataclass, field
import logging.config
import yaml

with open("log_config.yml", "r") as f:
    log_config = yaml.load(f, Loader=yaml.FullLoader)
logging.config.dictConfig(log_config)

@dataclass
class ConfigObj:
    redis_host: str = "116.56.140.193"
    redis_port: int = 6379
    redis_auth: str = "b7310"


config_obj = ConfigObj()
