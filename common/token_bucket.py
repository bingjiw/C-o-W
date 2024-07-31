import threading
import time

# 炳注：
# 每分钟生产20个tokens的令牌，10分钟后，TokenBucket内有多少令牌？
# 令牌生成速率：每分钟20个令牌，即每秒生成 20 / 60 = 1/3 个令牌。
# 令牌桶容量：容量为20个令牌。
# 初始令牌数：初始令牌数为0。
# 在 _generate_tokens 方法中，令牌每秒生成一次，直到达到容量上限。

# 10分钟后，生成的令牌数量为： [ 20 \text{ tokens/min} \times 10 \text{ min} = 200 \text{ tokens} ]

# 由于令牌桶的容量为20个令牌，超过容量的令牌将被丢弃。因此，10分钟后，令牌桶内将有 20个令牌。

# 没有用掉的令牌会自动过期吗？
# 根据代码实现，令牌不会自动过期。只要令牌桶的容量没有达到上限，生成的令牌会一直累积到桶内。如果桶的容量达到了上限，多余的令牌将被丢弃。

# 总结：

# 10分钟后，令牌桶内有20个令牌。
# 没有用掉的令牌不会自动过期，但超过容量的令牌会被丢弃。

class TokenBucket:
    def __init__(self, tpm, timeout=None):
        self.capacity = int(tpm)  # 令牌桶容量
        self.tokens = 0  # 初始令牌数为0
        self.rate = int(tpm) / 60  # 令牌每秒生成速率
        self.timeout = timeout  # 等待令牌超时时间
        self.cond = threading.Condition()  # 条件变量
        self.is_running = True
        # 开启令牌生成线程
        threading.Thread(target=self._generate_tokens).start()

    def _generate_tokens(self):
        """生成令牌"""
        while self.is_running:
            with self.cond:
                if self.tokens < self.capacity:
                    self.tokens += 1
                self.cond.notify()  # 通知获取令牌的线程
            time.sleep(1 / self.rate)

    def get_token(self):
        """获取令牌"""
        with self.cond:
            while self.tokens <= 0:
                flag = self.cond.wait(self.timeout)
                if not flag:  # 超时
                    return False
            self.tokens -= 1
        return True

    def close(self):
        self.is_running = False


if __name__ == "__main__":
    token_bucket = TokenBucket(20, None)  # 创建一个每分钟生产20个tokens的令牌桶
    # token_bucket = TokenBucket(20, 0.1)
    for i in range(3):
        if token_bucket.get_token():
            print(f"第{i+1}次请求成功")
    token_bucket.close()
