from logging import Logger
import redis
from .config import config_obj
import logging
from random import choices, random
from redis.lock import Lock
import re

logger = logging.getLogger("pool.pool")

fake_ip = [
    "113.120.143.199:1111",
    "186.159.2.249:8888",
    "210.59.0.1:1112",
    "170.79.88.113:3333",
    "36.66.103.75:4444",
    "36.66.104.75:4444",
    "36.66.105.75:4444",
    "36.66.106.75:4444",
    "36.66.107.75:4444",
    "36.66.108.75:4444",
]

ip_reg = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}$")


class IpPool:

    IP_POOP_KEY_NAME = "IP_POOL:POOL"
    IP_INDEX_PREFIX = "INDEX"
    DEFAULT_REPORT_NUM = 10
    DEFAULT_POOLSIZE = 3
    request_ip_span_time = 10

    def __init__(self, log_level=logging.DEBUG) -> None:
        logger.debug(
            f"init pool with host={config_obj.redis_host},port={config_obj.redis_port}")
        self.__redis_pool = redis.ConnectionPool(
            host=config_obj.redis_host, port=config_obj.redis_port, password=config_obj.redis_auth, decode_responses=True)
        self.client = redis.Redis(
            connection_pool=self.__redis_pool)
        self.request_ip_lock: Lock = self.client.lock(
            "request_ip_time_span", timeout=self.request_ip_span_time)
        logger.setLevel(log_level)

    def _load_ip(self):
        logger.debug("loading ip from source...")
        return choices(fake_ip, k=3)

    def register_index(self, index, pool_size=None, report_num=None):
        """
        注册index的一些初始信息，包括:
        1. 对应index的pool_size
        2. 对应index的report_num
        """
        pool_size = pool_size if pool_size is not None else self.DEFAULT_POOLSIZE
        report_num = report_num if report_num is not None else self.DEFAULT_REPORT_NUM

        index_pool_size_name = self.get_index_pool_size_name(index)
        index_report_num_name = self.get_index_report_number_name(index)

        logger.debug("register %s with %s = %s %s = %s", index,
                     index_pool_size_name, pool_size, index_report_num_name, report_num)
        self.client.mset({
            index_pool_size_name: pool_size,
            index_report_num_name: report_num,
        })
        self.__set_expire_date(index_pool_size_name)
        self.__set_expire_date(index_report_num_name)

    def load_proxy_from_source(self):
        if self.request_ip_lock.acquire(blocking=False):
            ips = self._load_ip()
            logger.debug("loading ips: %s save to %s" %
                         (ips, self.IP_POOP_KEY_NAME))
            self.client.sadd(self.IP_POOP_KEY_NAME, *ips)

    def __init_index_pool(self, index):
        logger.debug("exec init program %s", index)
        if not self.client.scard(self.IP_POOP_KEY_NAME):  # 如果主代理池不存在或者为空，则加载代理ip资源
            self.load_proxy_from_source()

        self.__supplement_proxy_from_main_pool(index)

    def get_ip(self, index):
        format_index = self.get_index_pool_name(index)
        logger.debug("index after format is %s" % format_index)
        if not self.client.scard(format_index):
            logger.debug(
                "index %s not exists,exec supplement program", format_index)
            self.__init_index_pool(index)
        return self.client.srandmember(format_index)

    def _report_ban_ip(self, index, ip):
        """
        这里ip指的是ip的字符串，形如ip:port
        """
        logger.debug("report %s %s should be ban", index, ip)
        assert ip is not None and re.match(
            ip_reg, ip) is not None, "ip is None or ip format error ip=%s" % ip
        index_pool_name = self.get_index_pool_name(index)
        index_ban_name = self.get_index_ban_pool_name(index)
        index_order_name = self.get_index_orderset_name(index)

        # 从index对应的set删除ip
        logger.debug("for %s move %s from %s to %s", index,
                     ip, index_pool_name, index_ban_name)
        self.client.smove(index_pool_name, index_ban_name, ip)

        # 将用于记录report的集合删除对应的记录
        logger.debug("for %s remove item from %s", index, index_order_name)
        self.client.zrem(index_order_name, ip)

        if not self.client.scard(index_pool_name):  # 如果删除之后对应index的pool为空，则进行补充
            self.__supplement_index(index)

    def _report_bad_ip(self, index, ip):
        """
        报告质量有问题的ip，有可能是偶然的原因造成的连接失败，
        如果ip被报告的次数过多，则会将ip直接删除，达到需要删除的次数和index对应的report_num相关，默认为10
        """
        logger.debug("report %s %s is bad", index, ip)
        assert ip is not None and re.match(
            ip_reg, ip) is not None, "ip is None or ip format error ip=%s" % ip
        index_order_name = self.get_index_orderset_name(index)

        this_report_num = self.client.zincrby(index_order_name, -1, ip)
        logger.debug("%s %s current count is %s", index, ip, this_report_num)
        if this_report_num <= 0:
            self._report_ban_ip(index, ip)

    def __supplement_index(self, index):
        """
        如果index对应的pool中无ip可用，则从主pool补充，且如果主pool中无可用的，则更新主pool
        """

        index_ban_name = self.get_index_ban_pool_name(index)

        index_can_use_ip_set = self.client.sdiff(
            self.IP_POOP_KEY_NAME, index_ban_name)  # 计算主池中未在对应index的banip中的ip

        if len(index_can_use_ip_set) == 0:
            self.load_proxy_from_source()

        # 从main pool 中加载ip到指定index的池中，更新相应的集合等
        self.__supplement_proxy_from_main_pool(index)

    def __supplement_proxy_from_main_pool(self, index):
        """
        执行从main pool 加载ip到对应的index的池中的操作，包含以下的操作
        1.首先获取一些对应的属性，对应index的pool_size和report_num
        2.假设main_pool中必有对应的ip，先取main_pool不在对应index ban_pool中的ip，然后在随机取pool_size
        3.将拿到的Ip放入到对应index的pool中，并加入到对应index的orderset中，更新index的orderset过期时间
        """
        index_pool_name = self.get_index_pool_name(index)
        index_pool_size_name = self.get_index_pool_size_name(index)
        index_report_num_name = self.get_index_report_number_name(index)
        index_ban_pool_name = self.get_index_ban_pool_name(index)

        index_pool_size, index_report_num = self.client.mget(
            index_pool_size_name, index_report_num_name)

        if index_pool_size is None:
            index_pool_size = self.DEFAULT_POOLSIZE

        if index_report_num is None:
            index_report_num = self.DEFAULT_REPORT_NUM

        logger.debug("%s pool_size and report_num is %s %s",
                     index, index_pool_size, index_report_num)

        random_ips: list[str] = None

        logger.debug("supplement proxy ip for %s ", index)

        this_ips_list = list(self.client.sdiff(
            self.IP_POOP_KEY_NAME, index_ban_pool_name))
        random_ips = choices(this_ips_list, k=min(
            int(index_pool_size), len(this_ips_list)))

        logger.debug("get %s random ip from pool %s",
                     len(random_ips), random_ips)

        if len(random_ips) == 0:
            logger.info("There are no qualified resources in main pool!")
            self.load_proxy_from_source()
            return

        self.client.sadd(index_pool_name, *random_ips)  # 将ip放到index对应的set中

        # 设置用于记录bad report的order set
        report_dict = {
            ip: index_report_num
            for ip in random_ips
        }
        logger.debug("report dict is %s", report_dict)
        index_order_name = self.get_index_orderset_name(index)
        logger.debug("add report_dict to orderset %s", index_order_name)
        self.client.zadd(index_order_name, report_dict)
        logger.debug("set expire date for %s", index_order_name)
        self.__set_expire_date(index_order_name)

    def get_index_pool_name(self, index):
        """
        根据index获取对应索引的可用代理池
        """
        return "%s:%s:pool" % (self.IP_INDEX_PREFIX, index)

    def get_index_ban_pool_name(self, index):
        return "%s:%s:ban_pool" % (self.IP_INDEX_PREFIX, index)

    def get_index_pool_size_name(self, index):
        return "%s:%s:pool_size" % (self.IP_INDEX_PREFIX, index)

    def get_index_report_number_name(self, index):
        return "%s:%s:report_number" % (self.IP_INDEX_PREFIX, index)

    def get_index_orderset_name(self, index):
        return "%s:%s:report_pool" % (self.IP_INDEX_PREFIX, index)

    def __set_expire_date(self, name, time=86400):
        """
        用于设置key的过期时间，默认是一天 60 * 60 * 24
        """
        logger.debug("set %s expire date after %s seconds", name, time)
        self.client.expire(name, time)

    def close(self):
        logger.info("shutdown pool...")
        self.__redis_pool.disconnect()

    def start(self):
        """
        代理池的初始化逻辑，这里没有默认实现，后续继承的子类可以自己实现对应的逻辑
        """
        pass
