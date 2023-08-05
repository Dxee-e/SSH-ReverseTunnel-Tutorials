import subprocess
import time
import yaml
import datetime
import requests
import os
import json

TEST_FLAG = True


class Config:
    """配置类"""

    def __init__(self, config_path=None, scheduler_path=None):
        # 配置文件
        if config_path is None:
            config_path = 'config.yaml' if not TEST_FLAG else 'config-test.yaml'
        with open(config_path, 'r') as f:
            self.cfg = yaml.safe_load(f)

        #调度数据
        if scheduler_path is None:
            self.scheduler_path = 'scheduler.json'
        if not os.path.exists(self.scheduler_path):
            data = {k//10: 0 for k in range(0, 24*60, 10)}
            with open(self.scheduler_path, 'w+', encoding='utf-8') as f:
                json.dump(data, f)
        with open(self.scheduler_path, 'r', encoding='utf-8') as f:
            self.scheduler_json = json.load(f)

    def write_json(self):
        with open(self.scheduler_path, 'w+', encoding='utf-8') as f:
            json.dump(self.scheduler_json, f)
    
    def read_json(self):
        with open(self.scheduler_path, 'r', encoding='utf-8') as f:
            self.scheduler_json = json.load(f)

    def get(self, cluster, key):
        return self.cfg[cluster][key]


class Scheduler:
    """调度程序，学习连接时间，减小资源占用"""

    def __init__(self):
        self.config = Config()
        self.proc = None # shell子进程

        self.start_minute = 0
        self.end_minute = 0

    def mainloop(self):
        while True:
            status = self.get_connect_status_from_cloud()
            if status == 'connect':
                if self.proc is None:
                    self.setup_connnect()
                else:   
                    time.sleep(self.config.get('general', 'keep-alive-interval'))
            elif status=='close':
                if self.proc is not None:
                    self.log_output('获取到云指令-关闭隧道')
                    self.close_connect()
            elif status=='exit':
                self.log_output('获取到云指令-程序终止')
                self.close_connect()
                exit(0)
            else:
                self.log_output('获取到云指令-未知')
                exit(1)

            self.sleep_until_next_get_status()


    def sleep_until_next_get_status(self):
        self.config.read_json()
        total = sum(self.config.scheduler_json.values())
        total = 1 if total==0 else total
        distribute = {k: v/total for k, v in self.config.scheduler_json.items()}
        now = datetime.datetime.now()
        cur_minute = now.hour*60 + now.minute
        dist = distribute[str(cur_minute//10)]
        sleep_time = 10*60 # max sleep 10min
        min_interval = 30 # s
        if dist >= 0.05:
            sleep_time = min_interval
        else:
            sleep_time = max((0.05-dist)/0.05*sleep_time, min_interval)
        time.sleep(sleep_time)


    def setup_connnect(self):
        """创建子进程，建立隧道"""
        command = 'ssh -o ConnectTimeout={timeout} -NTCR {reverse_port}:localhost:{server_port} {client_usr}@{client_ip} -p {client_port}'.format(
            timeout=self.config.get('general', 'connect-timeout'),
            reverse_port=self.config.get('client', 'reverse-tunnel-port'),
            server_port=self.config.get('server', 'ssh-port'),
            client_ip=self.config.get('client', 'public-ip'),
            client_usr=self.config.get('client', 'client-usr'),
            client_port=self.config.get('client', 'openssh-server-port'),
        )
        proc = subprocess.Popen(command.split(' '), stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        time.sleep(self.config.get('general', 'connect-timeout')+5)
        
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            if 'timed out' in stderr:
                self.log_output('超时，请检查客户端配置')
            else:
                self.log_output('未知错误:\nstdout:{}\nstderr:{}'.format(stdout, stderr))
        else:
            self.proc = proc
            self.log_output('隧道创建成功')

        now = datetime.datetime.now()
        self.start_minute = now.hour*60 + now.minute

    def close_connect(self):
        """关闭隧道子进程"""
        if self.proc is None:
            self.log_output('隧道未建立，跳过关闭操作')
            return

        self.proc.terminate()
        time.sleep(5) # 等5s结束进程
        if self.proc.poll() is None:
            self.log_output('隧道关闭失败，避免错误，程序终止')
            exit(1)

        self.log_output('隧道关闭成功')
        self.proc = None

        now = datetime.datetime.now()
        self.end_minute = now.hour*60 + now.minute
        if self.start_minute != self.end_minute:
            for i in range(self.start_minute//10, self.end_minute//10+1):
                self.config.scheduler_json[str(i)] += 1
            self.config.write_json()
            self.start_minute = self.end_minute = 0

    def log_output(self, message):
        """写日志"""
        with open('log.txt', 'a+') as f:
            f.write('[{}] {}\n'.format(datetime.datetime.now(), message))


    def get_connect_status_from_cloud(self):
        """从netcut网络剪切板中获取连接状态"""
        s = requests.Session()
        r = s.post(url='https://netcut.cn/api/note/auth/',
                   data={
                       'note_name': 'server-status-LVUwZkGZB53B',
                       'note_id': '5fe5ff56d11da73b',
                       'note_pwd': 'aMykw8Knh6MT'}).json()
        r = s.get(url='https://netcut.cn/api/note/data/?note_id={}&_={}'.format(r['data']['note_id'], r['req_id']),
                  data={
                      'note_name': 'server-status-LVUwZkGZB53B',
                      'note_id': '{}'.format(r['data']['note_id']),
                      'note_pwd': 'aMykw8Knh6MT',
                      'req_id': r['req_id']
                  }).json()
        status = r['data']['note_content']
        return status

if __name__ == '__main__':
    Scheduler().mainloop()
