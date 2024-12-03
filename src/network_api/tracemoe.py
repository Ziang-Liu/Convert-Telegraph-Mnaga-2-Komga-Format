from typing import Optional
from urllib.parse import quote_plus

from fake_useragent import UserAgent
from httpx import AsyncClient, Proxy


class TraceMoeApi:
    def __init__(self, proxy: Optional[Proxy] = None, cf_proxy: Optional[str] = None):
        def construct(endpoint: str) -> str:
            _base = "https://api.trace.moe"
            return f'{cf_proxy}/{_base}/{endpoint}' if cf_proxy else f'{_base}/{endpoint}'

        endpoints = {
            "📄": "search",
            "🔗": "search?url={}",
            "🔗-⬛": "search?cutBorders&url={}",
            "🔗+📺": "search?anilistInfo&url={}"
        }

        self._search_file = construct(endpoints["📄"])
        self._search_url = construct(endpoints["🔗"])
        self._search_url_cut_border = construct(endpoints["🔗-⬛"])
        self._search_url_anilist = construct(endpoints["🔗+📺"])
        self._proxy = proxy

    async def _search(self, call: str, url: str = None, data: bytes = None):
        headers = {"User-Agent": UserAgent().random}
        if url:
            headers["Content-Type"] = "application/octet-stream"

        async with AsyncClient(proxy = self._proxy, headers = headers) as client:
            if url:
                resp = await client.get(call.format(quote_plus(url)))
            else:
                resp = await client.post(call, data = data)

            resp.raise_for_status()
            result = resp.json()
            if result.get("error"):
                raise Exception(result["error"])

            return result.get("result")

    async def search(self, *arg: str | bytes):
        """
        搜索方法，根据传入的参数类型和值进行不同类型的搜索

        Args:
            *arg: 可变参数，支持 str 和 bytes 类型, 当第一个参数为 str 时，第二个参数可选 "cut_boarder" 或 "anilist"

        Returns:
            搜索结果

        Raises:
            ValueError: 如果传入的参数类型或值不正确

        Examples:
            >>> api = TraceMoeApi()
            >>> api.search("https://example.com/image.jpg")
            >>> api.search("https://example.com/image.jpg", "cut_boarder")
            >>> api.search(b"image_data")
        """
        if len(arg) == 2 and isinstance(arg[1], str):
            if arg[1] == 'cut_boarder':
                return await self._search(self._search_url_cut_border, arg[0])
            elif arg[1] == 'anilist':
                return await self._search(self._search_url_anilist, arg[0])
            else:
                raise ValueError("Invalid argument")
        elif len(arg) == 1 and isinstance(arg[0], str):
            return await self._search(self._search_url, arg[0])
        elif len(arg) == 1 and isinstance(arg[0], bytes):
            return await self._search(self._search_file, arg[0])
        else:
            raise ValueError("Invalid argument")
