import asyncio
from typing import Dict, Optional, List, Tuple

from PicImageSearch import Ascii2D, Iqdb, Google
from PicImageSearch import Network
from PicImageSearch.model import Ascii2DResponse, IqdbResponse, GoogleResponse
from fake_useragent import UserAgent
from httpx import Proxy
from httpx import URL, AsyncClient


def parse_cookies(cookies_str: Optional[str] = None) -> Dict[str, str]:
    cookies_dict: Dict[str, str] = {}

    if cookies_str:
        for line in cookies_str.split(";"):
            key, value = line.strip().split("=", 1)
            cookies_dict[key] = value

    return cookies_dict


class AggregationSearch:
    def __init__(self, proxy: Optional[Proxy] = None, cf_proxy: Optional[str] = None):
        self._proxy = proxy
        self._cf_proxy = cf_proxy
        self._media = b''

    async def get_media(self, url: str, cookies: Optional[str] = None) -> bytes:
        _url: URL = URL(url)
        headers: Dict[str, str] = {
            "User-Agent": UserAgent().random,
            "Referer": f"{_url.scheme}://{_url.host}/"
        }

        async with AsyncClient(
                headers = headers,
                cookies = parse_cookies(cookies),
                proxies = self._proxy,
                follow_redirects = True
        ) as client:
            resp = await client.get(_url)
            resp.raise_for_status()
            return resp.content

    @staticmethod
    async def _format(resp: Ascii2DResponse | GoogleResponse | IqdbResponse) -> List[Dict] | Dict:
        if isinstance(resp, Ascii2DResponse):
            result = []

            for i, r in enumerate(resp.raw):
                if not r.url_list or i == 0 or not r.url:
                    continue

                result.append({
                    "class": "ascii2d",
                    "detail": r.detail,
                    "thumbnail": r.thumbnail,
                    "url": r.url,
                    "url_list": r.url_list,
                    "title": r.title,
                    "author": r.author,
                    "author_url": r.author_url
                })

                if i == 3:
                    break

            return result
        elif isinstance(resp, GoogleResponse):
            if len(resp.raw) >= 3:
                r = resp.raw[2]
                return {
                    "class": "google",
                    "thumbnail": r.thumbnail,
                    "url": r.url,
                    "title": r.title
                }
        elif isinstance(resp, IqdbResponse):
            r = resp.raw[0]
            danbooru = [i for i in resp.raw if i.source == "Danbooru"]
            yandere = [i for i in resp.raw if i.source == "yande.re"]
            r = danbooru[0] if danbooru else yandere[0] if yandere else r

            if r.similarity >= 85.0:
                return {
                    "class": "iqdb",
                    "thumbnail": r.thumbnail,
                    "url": r.url,
                    "content": r.content,
                    "size": r.size,
                    "similarity": r.similarity,
                    "source": r.source,
                    "other_source": r.other_source
                }
        else:
            raise TypeError("Unsupported response type")

    async def _search(self, *args: str) -> Tuple[List[Dict], List[Dict]] | Dict:
        async with Network(proxies = self._proxy) as client:
            if not self._media:
                self._media = await self.get_media(args[0])

            if args[1] == "ascii2d":
                base_url = f'{self._cf_proxy}/https://ascii2d.net' if self._cf_proxy else 'https://ascii2d.net'
                ascii2d = Ascii2D(base_url = base_url, client = client)
                ascii2d_bovw = Ascii2D(base_url = base_url, bovw = True, client = client)
                resp, resp_bovw = await asyncio.gather(
                    ascii2d.search(file = self._media),
                    ascii2d_bovw.search(file = self._media)
                )
                if not resp.raw and not resp_bovw.raw:
                    raise ValueError(f"No Ascii2D search result for '{args[0]}'")

                return await asyncio.gather(
                    self._format(resp),
                    self._format(resp_bovw)
                )
            elif args[1] == "iqdb":
                base_url = f'{self._cf_proxy}/https://iqdb.org' if self._cf_proxy else 'https://iqdb.org'
                base_url_3d = f'{self._cf_proxy}/https://3d.iqdb.org' if self._cf_proxy else 'https://3d.iqdb.org'
                iqdb = Iqdb(base_url = base_url, base_url_3d = base_url_3d, client = client)
                resp = await iqdb.search(file = self._media)
                if not resp.raw:
                    raise ValueError(f"No Iqdb search result for '{args[0]}'")

                return await self._format(resp)
            elif args[1] == "google":
                google = Google(client = client)
                resp = await google.search(file = self._media)
                if not resp.raw:
                    raise ValueError(f"No Google search result for '{args[0]}'")

                return await self._format(resp)
            else:
                raise ValueError(f"Unrecognized argument: '{args[1]}'")

    async def iqdb_search(self, url: str) -> Dict:
        """
        通过 Iqdb 搜索

        Args:
            url: 图像链接

        Returns:
            Iqdb 搜索结果

        Raises:
            HTTPStatusError: 获取图像失败
            RuntimeError: 和服务器通信失败
            ValueError: 返回了空的搜索结果
        """
        return await self._search(url, 'iqdb')

    async def ascii2d_search(self, url: str) -> Dict:
        """
        通过 Ascii2D 搜索

        Args:
            url: 图像链接

        Returns:
            Ascii2D 搜索结果

        Raises:
            HTTPStatusError: 获取图像失败
            RuntimeError: 和服务器通信失败
            ValueError: 返回了空的搜索结果
        """
        r, b = await self._search(url, 'ascii2d')

        for i in range(min(len(r), len(b))):
            if r[i]["url"] == b[i]["url"]:
                return r[i]

        raise ValueError(f"No Ascii2D search result for '{url}'")

    async def google_search(self, url: str) -> Dict:
        """
        通过 Google 搜索，使用时确保网络通畅，CloudFlare Worker 不支持反代此 API

        Args:
            url: 图像链接

        Returns:
            谷歌眼镜搜索结果

        Raises:
            HTTPStatusError: 获取图像失败
            RuntimeError: 和服务器通信失败
            ValueError: 返回了空的搜索结果
        """
        return await self._search(url, 'google')

    async def aggregation_search(self, url: str) -> List[Dict]:
        """
        聚合搜索

        Args:
            url: 图像链接

        Returns:
            列表形式的搜索结果，注意可能为空
        """
        return [r for r in await asyncio.gather(
            self.ascii2d_search(url),
            self.iqdb_search(url),
            self.google_search(url),
            return_exceptions = True
        ) if r is not None and not isinstance(r, Exception)]
