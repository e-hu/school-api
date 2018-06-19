import re
import requests
import inspect
import logging
from bs4 import BeautifulSoup, SoupStrainer

from school_api.client.api.base import BaseSchoolApi
from school_api.client.utils import NullClass

logger = logging.getLogger(__name__)


def _is_api_endpoint(obj):
    return isinstance(obj, BaseSchoolApi)


class BaseSchoolClient(object):

    use_proxy = False
    school_url = [
        {
            # 学生
            'SCORE_URL': '/xscj_gc.aspx?xh=',
            'INFO_URL': '/xsgrxx.aspx?gnmkdm=N121501&xh=',
            'SCHEDULE_URL': ['/xskbcx.aspx?gnmkdm=N121603&xh=', '/tjkbcx.aspx?gnmkdm=N121601&xh=']
        }, {
            # 教师
            'INFO_URL': '/lw_jsxx.aspx?gnmkdm=N122502&zgh=',
            'SCHEDULE_URL': ['', '/jstjkbcx.aspx?gnmkdm=N122303&zgh=']
        }, {
            # 部门
            'SCHEDULE_URL': ['']
        }
    ]


class BaseUserClient(object):
    """docstring for BaseUserClient"""

    _http = requests.Session()

    def __new__(cls, *args, **kwargs):
        self = super(BaseUserClient, cls).__new__(cls)
        api_endpoints = inspect.getmembers(self, _is_api_endpoint)
        for name, api in api_endpoints:
            api_cls = type(api)
            api = api_cls(self)
            setattr(self, name, api)
        return self

    def __init__(self):
        self._http.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/62.0.3202.89 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
        })

    def _request(self, method, url_or_endpoint, **kwargs):
        if self.school.use_proxy:
            base_url = self.school.lan_url
            kwargs['proxies'] = self.proxies
        else:
            base_url = self.school.url
        if not url_or_endpoint.startswith(('http://', 'https://')):
            url = '{base}{endpoint}'.format(
                base=base_url,
                endpoint=url_or_endpoint
            )
        else:
            url = url_or_endpoint

        res = self._http.request(
            method=method,
            url=url,
            **kwargs
        )
        return res

    def get(self, url, **kwargs):
        return self._request(
            method='GET',
            url_or_endpoint=url,
            **kwargs
        )

    def post(self, url, **kwargs):
        return self._request(
            method='POST',
            url_or_endpoint=url,
            **kwargs
        )

    def get_view_state(self, url_suffix, **kwargs):
        res = self.get(url_suffix, allow_redirects=False, **kwargs)
        if res.status_code != 200:
            return None
        return self.get_view_state_from_html(res.text)

    def get_view_state_from_html(self, html):
        pre_soup = BeautifulSoup(html, "html.parser")
        view_state = pre_soup.find(
            attrs={"name": "__VIEWSTATE"})['value']
        return view_state

    def update_headers(self, headers_dict):
        self._http.headers.update(headers_dict)

    def _login(self, **kwargs):
        view_state = self.get_view_state(self.school.login_url_suffix, **kwargs)
        payload = {
            '__VIEWSTATE': view_state,
            'TextBox1': self.account.encode('gb2312'),
            'TextBox2': self.passwd,
            'RadioButtonList1': self.school._login_types[self.user_type].encode('gb2312'),
            'Button1': u' 登 录 '.encode('gb2312')
        }
        self.update_headers({'Referer': self.school.url+self.school.login_url_suffix})
        res = self.post(self.school.login_url_suffix, data=payload,
                        allow_redirects=False, **kwargs)
        return res

    def get_login(self, **kwargs):
        try:
            res = self._login(**kwargs)
        except requests.exceptions.Timeout:
            # 使用内网代理
            if self.school.proxies and self.school.lan_url:
                self.use_proxy = True
                return self._login(**kwargs)
            return NullClass('user_login: {} {}'.format(self.school.url, '请求超时'))

        # 登录成功之后，教务系统会返回 302 跳转
        if not res.status_code == 302:
            page_soup = BeautifulSoup(res.text, "html.parser", parse_only=SoupStrainer("script"))
            tip = re.findall(r'[^()\']+', page_soup.getText())[1]
            self = NullClass(tip)
        return self
