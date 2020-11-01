from pool import IpPool

pool: IpPool = None


def setup_module():
    global pool
    pool = IpPool()


def test_base():
    pool.register_index("lp")
    this_ip = pool.get_ip("lp")
    print(this_ip)
    for i in range(10):
        pool.report_bad_ip('lp', this_ip)
    this_ip = pool.get_ip("lp")
    print(this_ip)
    pool.report_ban_ip('lp', this_ip)
    this_ip = pool.get_ip("lp")
    print(this_ip)


def teardown_module():
    pool.close()
