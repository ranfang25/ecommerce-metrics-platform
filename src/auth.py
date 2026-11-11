"""可复用用户已登录的官方gcloud CLI，不落盘访问令牌。"""
import subprocess
from datetime import datetime,timedelta
from google.auth.credentials import Credentials


class GcloudCredentials(Credentials):
    def __init__(self,executable):
        super().__init__()
        self.executable=executable

    def refresh(self,request):
        result=subprocess.run([self.executable,'auth','print-access-token','--quiet'],capture_output=True,text=True,encoding='utf-8')
        if result.returncode:
            raise RuntimeError('gcloud认证不可用，请先完成本机登录；'+result.stderr[-500:])
        self.token=result.stdout.strip()
        self.expiry=datetime.utcnow()+timedelta(minutes=45)
