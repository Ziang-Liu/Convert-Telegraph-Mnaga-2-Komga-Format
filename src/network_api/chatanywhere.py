import json
from typing import Optional, List, Dict

from httpx import Proxy, URL, AsyncClient, HTTPStatusError, RequestError


class ChatAnywhereApi:
    def __init__(
            self,
            token: str | None = None,
            proxy: Optional[URL] | Optional[Proxy] | Optional[str] = None,
            cf_proxy: Optional[str] = None
    ) -> None:

        if not token:
            raise ValueError("No valid token provided.")

        self._proxy = proxy
        self._token = token
        self._user_agent = 'Apifox/1.0.0 (https://apifox.com)'
        self._base_url = f'{cf_proxy}/https://api.chatanywhere.tech' if cf_proxy else 'https://api.chatanywhere.tech'

    async def _request(self, method: str, endpoint: str, payload: str = None, auth_type: int = 0) -> json:
        """
        Make a request to the API
        :param method: Can be either 'GET' or 'POST'
        :param endpoint: Endpoint to call
        :param payload: Payload to send
        :param auth_type: Authentication type to use, 0 for 'Bearer Token', 1 for 'Token'
        """

        async def _handle_request(request_func) -> json:
            try:
                response = await request_func()
                response.raise_for_status()
                return response.json()
            except HTTPStatusError as e:
                raise Exception(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
            except RequestError as e:
                raise Exception(f"Request error occurred: (URL: {e.request.url}, Headers: {e.request.headers})")
            except Exception as e:
                raise Exception(f"An unexpected error occurred: {e}")

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
                raise ValueError("Invalid HTTP method")

    async def list_model(self) -> List[Dict]:
        return (await self._request('GET', 'v1/models'))['data']

    async def chat(
            self,
            user_input: Optional[str] = None,
            model_id: str = "gpt-3.5-turbo",
            system_prompt: Optional[str] = None
    ) -> dict:
        if not user_input:
            raise Exception("No user input provided.")

        system_prompt = "You are a helpful assistant." if not system_prompt else system_prompt

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
