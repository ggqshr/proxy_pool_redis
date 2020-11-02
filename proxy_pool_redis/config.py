from dataclasses import dataclass, field
import logging.config
import yaml
from pathlib import Path

this_path = Path(__file__)
log_path = this_path.parent.joinpath("log_config.yml")

with open(log_path, "r") as f:
    log_config = yaml.load(f, Loader=yaml.FullLoader)
logging.config.dictConfig(log_config)

@dataclass
class ConfigObj:
    redis_host: str = "116.56.140.193"
    redis_port: int = 6379
    redis_auth: str = "b7310"


config_obj = ConfigObj()
