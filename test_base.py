from proxy_pool_redis.pool import IpPool
from time import sleep

pool: IpPool = None


def setup_module():
    global pool
    pool = IpPool()


def test_base():
    index = "lp"
    pool.register_index(index)
    for i in range(10):
        this_ip = pool.get_ip(index)
        print(this_ip)
        if i < 3:
            pool.report_ban_ip(index,this_ip)
    print("sleep 10s....")
    sleep(10)
    for i in range(10):
        this_ip = pool.get_ip(index)
        print(this_ip)
        if i < 3:
            pool.report_ban_ip(index,this_ip)


def teardown_module():
    pool.close()
