from http.cookies import SimpleCookie
from typing import Optional

import httpx

DEFAULT_CATE_URI = '/usercp.php?action=tracker'


class NexusPHPGenerator:
    """
    Nexus站点的适配文件生成器
    """

    def __init__(self, domain: str, cookie_str: str, user_agent: Optional[str] = None):
        self.domain = domain.rstrip('/')
        self.user_agent = user_agent
        self._set_cookie(cookie_str)

    def _set_cookie(self, cookie_str: str):
        if not cookie_str:
            return
        cookie = SimpleCookie(cookie_str)
        cookies = {}
        for key, morsel in cookie.items():
            cookies[key] = morsel.value
        self.cookies = cookies

    def _get_cate_page_source(self):
        res = httpx.get(
            f'{self.domain}{DEFAULT_CATE_URI}',
            cookies=self.cookies,
            headers={
                'User-Agent': self.user_agent
            },
            follow_redirects=True,
        )
        return res.text

    def start(self):
        cate_page_source = self._get_cate_page_source()
        # todo 对html页面内容分割后交给gpt识别，gpt有tokens限制
