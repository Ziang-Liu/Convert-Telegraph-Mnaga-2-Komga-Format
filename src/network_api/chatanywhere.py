import json
from typing import Optional, List, Dict

from httpx import Proxy, AsyncClient, HTTPStatusError, RequestError


class ChatAnywhereApi:
    def __init__(self, token: str, proxy: Optional[Proxy] = None, cf_proxy: Optional[str] = None):
        if not token:
            raise ValueError("未提供有效的 token")

        self._proxy = proxy
        self._token = token
        self._user_agent = 'Apifox/1.0.0 (https://apifox.com)'
        self._base_url = f'{cf_proxy}/https://api.chatanywhere.tech' if cf_proxy else 'https://api.chatanywhere.tech'

    async def _request(self, method: str, endpoint: str, payload: str = None, auth_type: int = 0) -> json:
        """
        发送 HTTP 请求到 API

        Args:
            method: HTTP 方法，支持 'GET' 和 'POST'
            endpoint: API 端点
            payload: 请求负载（可选）
            auth_type: 认证类型，0 为 'Bearer Token'，1 为 'Token'

        Returns:
            响应数据（JSON 格式）

        Raises:
            Exception: 如果请求失败
            ValueError: 如果方法无效
        """

        async def _handle_request(request_func) -> json:
            try:
                response = await request_func()
                response.raise_for_status()
                return response.json()
            except HTTPStatusError as e:
                raise Exception(f"HTTP 错误：{e.response.status_code} - {e.response.text}")
            except RequestError as e:
                raise Exception(f"请求错误：(URL: {e.request.url}, Headers: {e.request.headers})")
            except Exception as e:
                raise Exception(f"意外错误：{e}")

        headers = {
            'User-Agent': self._user_agent,
            'Content-Type': 'application/json'
        }

        if auth_type == 0:
            headers['Authorization'] = f'Bearer {self._token}'
        elif auth_type == 1:
            headers['Authorization'] = self._token

        async with AsyncClient(proxies = self._proxy, headers = headers) as client:
            if method == 'GET':
                return await _handle_request(lambda: client.get(f"{self._base_url}/{endpoint}"))
            elif method == 'POST':
                return await _handle_request(lambda: client.post(f"{self._base_url}/{endpoint}", content = payload))
            else:
                raise ValueError("无效的 HTTP 方法")

    async def list_model(self) -> List[Dict]:
        return (await self._request('GET', 'v1/models'))['data']

    async def chat(self, user_input: str, system_prompt: str, model_id: str = "gpt-3.5-turbo") -> dict:
        """
        发送用户输入和系统提示到聊天模型，并返回模型的响应

        Args:
            user_input (str): 用户输入的文本
            system_prompt (str): 系统提示的文本，用于指导模型的响应
            model_id (str): 使用的模型ID，默认为"gpt-3.5-turbo"

        Returns:
            包含模型响应的字典
        """
        payload = json.dumps({
            "model": f"{model_id}",
            "messages": [
                {"role": "system", "content": f"{system_prompt}"},
                {"role": "user", "content": f"{user_input}"}
            ]
        })

        response = await self._request('POST', 'v1/chat/completions', payload)

        return {'answers': response['choices'], 'usage': response['usage']}

    async def get_usage(
            self,
            model_id: str = "gpt-3.5-turbo",
            hours: int = 24
    ) -> List[Dict]:
        payload = json.dumps({
            "model": f"{model_id}%",
            "hours": hours
        })

        return await self._request('POST', 'v1/query/usage_details', payload, 1)
