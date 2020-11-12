import json
import logging
import uuid
from threading import Thread
from queue import Queue
from time import sleep

import requests

from .config import config_obj
from .pool import IpPool

REQUEST_SUCCESS = 0
REQUEST_TOO_QUICK = 1

logger = logging.getLogger("pool.xunpool")


class XunProxyPool(IpPool):
    def __init__(self, api_url=None, name=None, scan_timeout_ip=False, scan_time_span=300, pool_size=None,
                 reporta_num=None, redis_host=None, redis_port=None, redis_password=None, log_level=logging.DEBUG) -> None:
        """
        针对讯代理的代理池，需要传入请求ip的url，以及需要使用该代理池的应用程序名字（爬虫名字，比如爬虫爬取网站的缩写等）
        如果不传入name，则默认为uuid的前八个字符
        api_url: 请求可以获得ip资源的url
        name：使用该代理池的应用名字，可以用爬取目标网站的缩写等，如果不传入，则默认为uuid的前8位，每次都不一样
        scan_timeout_ip：是否扫描不可用的ip，并将其删除
        scan_time_span：扫描的时间间隔，默认为5分钟
        """
        config_obj.redis_host = redis_host if redis_host is not None else config_obj.redis_host
        config_obj.redis_port = redis_port if redis_port is not None else config_obj.redis_port
        config_obj.redis_auth = redis_password if redis_password is not None else config_obj.redis_auth

        if name is None:
            name = str(uuid.uuid4())[:8]
        self.name = name

        assert api_url is not None, "api_url不能为空"
        self.api_url = api_url
        logger.setLevel(log_level)

        super().__init__(log_level=log_level)

        self.register_index(name, pool_size, reporta_num)

        self.request_queue = Queue()
        self.ip_queue = Queue()
        self.get_ip_threading_running = True

        if scan_timeout_ip:
            self.scan_time_span = scan_time_span
            super()._scan_unavailable_ip_to_delete()

    def _load_ip(self):
        logger.info("load ip overload from xunproxy")
        flag = None
        res = None

        while flag != REQUEST_SUCCESS:
            logger.info("starting to requests ip = %s", self.api_url)
            res = requests.get(self.api_url).content.decode()  # 请求ip
            res = json.loads(res)  # 解析成字典
            if res['ERRORCODE'] == '0':
                logger.info("请求新的代理IP")
                flag = REQUEST_SUCCESS
            elif res['ERRORCODE'] in ["10036", "10038", "10055"]:
                logger.info("提取频率过高，sleep 10s")
                flag = REQUEST_TOO_QUICK
                sleep(10)
            elif res["ERRORCODE"] == "10032":
                logger.info("已达上限!!")
                raise ReachMaxException()

        ip_port_list = res['RESULT']
        ip_pool = set([f"{ll['ip']}:{ll['port']}" for ll in ip_port_list])
        return ip_pool

    def get_ip(self):
        self.request_queue.put_nowait("fetch proxy ip")
        this_ip = self.ip_queue.get(timeout=60)
        return this_ip

    def __get_ip(self):
        logger.debug("getting ip thread is starting...")
        while self.get_ip_threading_running:
            self.request_queue.get()
            this_ip = super().get_ip(self.name)
            while this_ip is None:
                this_ip = super().get_ip(self.name)
            self.ip_queue.put(this_ip)

    def report_bad_ip(self, ip):
        super()._report_bad_ip(self.name, ip)

    def report_ban_ip(self, ip):
        super()._report_ban_ip(self.name, ip)

    def start(self):
        logger.info("starting xunproxy pool")
        get_ip_thread = Thread(target=self.__get_ip, daemon=True)
        get_ip_thread.start()

    def close(self):
        super().close()
        self.get_ip_threading_running = False


class ReachMaxException(Exception):
    def __init__(self):
        pass
