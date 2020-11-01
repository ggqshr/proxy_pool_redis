from queue import Empty, Full, PriorityQueue, Queue
from random import choices
from typing import Any
from dataclasses import dataclass, field
import logging
from time import sleep
from threading import Thread

logging.basicConfig(level=logging.INFO)

GET_IP_EVENT = 1
REPORT_BAD_EVENT = 2
REPORT_BAN_EVENT = 3


fake_ip = [
    "113.120.143.199:1111",
    "186.159.2.249:8888",
    "210.59.0.1:1112",
    "170.79.88.113:3333",
    "36.66.103.75:4444",
]


@dataclass(eq=True, repr=True, unsafe_hash=True)
class IpInfo:
    ip: str = field(default_factory=str, compare=True,hash=True)
    port: int = field(default_factory=int, compare=True,hash=True)

    def to_ip_str(self) -> str:
        return "%s:%s" % (self.ip, self.port)

    @classmethod
    def from_str(cls, ip_str: str):
        this_ip, this_port = ip_str.split(":")
        return cls(this_ip, this_port)


@dataclass(order=True, repr=True)
class IpQueueItem:
    weight: int
    ip_info: IpInfo = field(compare=False)


@dataclass(repr=True)
class EvnentQueueItem:
    event: int
    item: Any


class Pool:
    def __init__(self, pool_size, max_report_num, loop) -> None:
        self.max_report_num = max_report_num
        self.pool_size = pool_size
        self.ip_pool = PriorityQueue()
        self.event_pool = Queue()
        self.log = logging.getLogger()
        self.event_thread = Thread(target=self.start,daemon=True)
        self.event_thread.start()
        self.__event_control_queue = Queue(1,)
        self.__get_ip_queue = Queue(1,)
        self.ip_list: set[IpInfo] = set()

    def __get_process_ip(self):
        self.log.info("process ip")
        ips = self.__request_ip()
        for ip in ips:
            this_ip, this_port = ip.split(":")
            self.ip_pool.put(IpQueueItem(self.max_report_num,
                                               IpInfo(this_ip, int(this_port))))

    def __request_ip(self):
        self.log.info("get ip...")
        return choices(fake_ip, k=self.pool_size)

    def get_ip(self) -> str:
        
        while True:
            try:
                queue_item: IpQueueItem = self.ip_pool.get_nowait()

                if queue_item.weight == 0:
                    self.ip_list.add(queue_item.ip_info.to_ip_str())
                    continue

                ip_info = queue_item.ip_info

                if ip_info.to_ip_str() in self.ip_list:
                    continue

                self.ip_pool.put_nowait(queue_item)
                return ip_info.to_ip_str()
            except Empty:
                self.log.info("get empty")
                try:
                    self.__get_ip_queue.put_nowait("start to process")
                    self.ip_list.clear()
                except Full:
                    pass

    def report_ban(self, ip: IpInfo):
        self.log.info("report ban ip %s" % ip)
        self.event_pool.put_nowait(EvnentQueueItem(REPORT_BAN_EVENT, ip))

    def report_bad(self, ip: IpInfo):
        self.log.info("report bad ip %s" % ip)
        self.event_pool.put_nowait(EvnentQueueItem(REPORT_BAD_EVENT, ip))

    def __get_ip_event_handle(self):
        self.log.info("start get ip event handle")
        while self.__event_control_queue.empty():
            self.__get_ip_queue.get()
            self.__get_process_ip()
            if self.__get_ip_queue.full():
                sleep(2)
                self.log.info("clear the get ip queue")
                self.__get_ip_queue.get_nowait()
                if not self.__event_control_queue.empty():
                    break

    def __report_event_handle(self):
        ip_map_weight = dict()
        self.log.info("start report event handle")
        while self.__event_control_queue.empty():
            event_item = self.event_pool.get()
            self.log.info("process event %s" % event_item)
            if event_item.event == REPORT_BAD_EVENT:
                this_ip_weight = ip_map_weight.get(
                    event_item.item, self.max_report_num)
                this_ip_weight -= 1
                self.ip_pool.put(IpQueueItem(this_ip_weight, event_item.item))
                ip_map_weight[event_item.item] = ip_map_weight
            elif event_item.event == REPORT_BAN_EVENT:
                self.ip_pool.put(IpQueueItem(0, event_item.item))

    def event_handle(self):
        self.log.info("event handle start...")
        report_thread = Thread(target=self.__report_event_handle,daemon=True,)
        report_thread.start()
        get_ip_thread = Thread(target=self.__get_ip_event_handle,daemon=True)
        get_ip_thread.start()
        report_thread.join()
        get_ip_thread.join()

    def start(self):
        # self.loop.set_debug(True)
        self.event_handle()

    def close(self):
        self.__event_control_queue.put_nowait("close")
        self.event_thread.join()
