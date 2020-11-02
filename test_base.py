from proxy_pool_redis.XunProxyPool import XunProxyPool
from proxy_pool_redis.pool import IpPool
from time import sleep

pool: IpPool = None


def setup_module():
    global pool
    pool = XunProxyPool(
        api_url="http://api.xdaili.cn/xdaili-api/greatRecharge/getGreatIp?spiderId=2eeedc14918546f087abcddafd5ee37d&orderno=YZ20196121637TQppQw&returnType=2&count=3", name="lp")
    pool.start()


def test_base():
    for i in range(10):
        this_ip = pool.get_ip()
        print(this_ip)
        if i < 3:
            pool.report_ban_ip(this_ip)
    print("sleep 10s....")
    sleep(10)
    for i in range(10):
        this_ip = pool.get_ip()
        print(this_ip)
        if i < 3:
            pool.report_ban_ip(this_ip)


def teardown_module():
    pool.close()
