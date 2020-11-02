# proxy_pool_redis 使用redis作为后端存储的ip代理池
能够根据对应付费ip的请求Url加载对应的Proxy ip到池中，并能够提供多个应用使用，对应每个应用需要传入特定的应用名字做标示，可对特定的应用使用的Ip报告被ban,质量差的ip

## 使用方法
```python
from proxy_pool_redis import XunProxyPool

pool = XunProxyPool(api_url='xxx',name='crawl_name',redis_host='xx',redis_port=xx,redis_password='xx',report_num=10)
pool.start()

# 获取一个ip
ip = pool.get_ip()

# 报告ip已经被当前应用ban了
pool.report_ban_ip(ip)

# 报告当前ip的质量不好
# 如果报告的次数达到了report_num的值，则将该ip ban掉
pool.report_bad_ip(ip)
```