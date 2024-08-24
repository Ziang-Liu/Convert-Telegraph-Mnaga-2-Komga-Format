import asyncio
from typing import Dict, Optional, List

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

        self._ascii2d: List = []
        self._ascii2d_bovw: List = []

        self.exception = []
        self.media = b''
        self.ascii2d_result: Dict = {}
        self.iqdb_result: Dict = {}
        self.google_result: Dict = {}

    async def get_media(self, url: str, cookies: Optional[str] = None):
        _url: URL = URL(url)
        _referer: str = f"{_url.scheme}://{_url.host}/"
        _default_headers: Dict = {"User-Agent": UserAgent().random}
        headers: Dict = {"Referer": _referer, **_default_headers}

        async with AsyncClient(
                headers = headers, cookies = parse_cookies(cookies),
                proxies = self._proxy, follow_redirects = True
        ) as client:
            resp = await client.get(_url)
            self.media = resp.raise_for_status().content

    async def _search_with_type(self, url: str, type: str):
        async with Network(proxies = self._proxy) as client:
            await self.get_media(url)

            if type == "ascii2d":
                base_url = f'{self._cf_proxy}/https://ascii2d.net' if self._cf_proxy else 'https://ascii2d.net'
                ascii2d = Ascii2D(base_url = base_url, client = client)
                ascii2d_bovw = Ascii2D(base_url = base_url, client = client, bovw = True)

                resp, bovw_resp = await asyncio.gather(ascii2d.search(file = self.media),
                                                       ascii2d_bovw.search(file = self.media))
                if not resp.raw and not bovw_resp.raw:
                    raise Exception(f"No ascii2d search results, search url: {resp.url}")

                await asyncio.gather(self._format_ascii2d_result(bovw_resp, bovw = True),
                                     self._format_ascii2d_result(resp))

            if type == "iqdb":
                base_url = f'{self._cf_proxy}/https://iqdb.org' if self._cf_proxy else 'https://iqdb.org'
                base_url_3d = f'{self._cf_proxy}/https://3d.iqdb.org' if self._cf_proxy else 'https://3d.iqdb.org'
                iqdb = Iqdb(base_url = base_url, base_url_3d = base_url_3d, client = client)

                resp = await iqdb.search(file = self.media)
                if not resp.raw:
                    raise Exception(f"No iqdb search results, search url: {resp.url}")

                await self._format_iqdb_result(resp)

            if type == "google":
                base_url = f'{self._cf_proxy}/https://www.google.com' if self._cf_proxy else 'https://www.google.com'
                google = Google(base_url = base_url, client = client)

                resp = await google.search(file = self.media)
                if not resp.raw:
                    raise Exception(f"No google search results, search url: {resp.url}")

                await self._format_google_result(resp)

    async def _format_google_result(self, resp: GoogleResponse):
        if len(resp.raw) >= 3:
            self.google_result = {
                "class": "google",
                "thumbnail": resp.raw[2].thumbnail,
                "title": resp.raw[2].title,
                "url": resp.raw[2].url
            }

    async def _format_iqdb_result(self, resp: IqdbResponse):
        selected_res = resp.raw[0]
        danbooru_res = [i for i in resp.raw if i.source == "Danbooru"]
        yandere_res = [i for i in resp.raw if i.source == "yande.re"]

        selected_res = danbooru_res[0] if danbooru_res else yandere_res[0] if yandere_res else selected_res

        if selected_res.similarity >= 85.0:
            self.iqdb_result = {
                "class": "iqdb",
                "url": selected_res.url,
                "similarity": selected_res.similarity,
                "thumbnail": selected_res.thumbnail,
                "content": selected_res.content,
                "source": selected_res.source
            }

    async def _format_ascii2d_result(self, resp: Ascii2DResponse, bovw: bool = False):
        target = self._ascii2d_bovw if bovw else self._ascii2d

        for i, r in enumerate(resp.raw):
            if not r.url_list or i == 0 or not r.url:
                continue

            r.author = r.author or "None"
            target.append({
                "class": "ascii2d",
                "url": r.url,
                "author": r.author,
                "author_url": r.author_url,
                "thumbnail": r.thumbnail
            })

            if i == 3:
                break

    async def iqdb_search(self, url: str):
        try:
            await self._search_with_type(url, 'iqdb')
        except Exception as e:
            self.exception.append(e)

    async def ascii2d_search(self, url):
        try:
            await self._search_with_type(url, 'ascii2d')

            for i in range(min(len(self._ascii2d_bovw), len(self._ascii2d))):
                if self._ascii2d[i]["url"] == self._ascii2d_bovw[i]["url"]:
                    self.ascii2d_result = self._ascii2d[i]
        except Exception as e:
            self.exception.append(e)

    async def google_search(self, url):
        try:
            await self._search_with_type(url, 'google') if self._proxy else None
        except Exception as e:
            self.exception.append(e)

    async def aggregation_search(self, url: str) -> Optional[List[Dict]]:
        await asyncio.gather(self.iqdb_search(url), self.ascii2d_search(url), self.google_search(url))
        result = []
        result.append(self.iqdb_result) if self.iqdb_result else None
        result.append(self.ascii2d_result) if self.ascii2d_result else None
        result.append(self.google_result) if self.google_result else None

        return result
