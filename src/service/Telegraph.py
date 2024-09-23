import asyncio
import os
import re
import shutil
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin
from zipfile import ZipFile, ZIP_DEFLATED

import aiofiles
import httpx
from bs4 import BeautifulSoup
from ebooklib import epub
from fake_useragent import UserAgent
from httpx import URL, AsyncClient, Proxy, Response

from src.Environment import EnvironmentReader
from src.utils.Logger import logger


class Telegraph:
    def __init__(
            self,
            telegraph_url: str,
            proxy: Optional[Proxy] = None,
            cloudflare_worker_proxy: Optional[str] = None
    ):
        self._url = f'{cloudflare_worker_proxy}/{telegraph_url}' if cloudflare_worker_proxy else telegraph_url
        self._proxy = proxy
        self._cf_proxy = cloudflare_worker_proxy
        self._headers = {'User-Agent': UserAgent().random}
        self._image_url_list = []
        self._raw_title: Optional[str] = None

        self.title: Optional[str] = None
        self.artist: Optional[str] = None
        self.thumbnail: Optional[str | URL] = None

        env = EnvironmentReader()
        self._thread = env.get_variable("TELEGRAPH_THREADS")

        # declared in bot/Main.py
        self.komga_dir = '/neko/komga'
        self.epub_dir = '/neko/epub'
        self._tmp_dir = '/neko/.temp'

        # generated path
        self.manga_path = self._tmp_dir
        self._epub_file_path = self._tmp_dir
        self._zip_file_path = self._tmp_dir
        self._download_path = self._tmp_dir

        # remove cache folders last longer than 1 day
        for root, dirs, _ in os.walk(self._tmp_dir):
            for temp_dir in dirs:
                path = os.path.join(root, temp_dir)
                modified_time = datetime.fromtimestamp(os.path.getmtime(path))
                shutil.rmtree(path) if datetime.now() - modified_time > timedelta(days = 1) else None

    async def _task_handler(self) -> int:
        async def download_handler():
            async def worker(q: asyncio.Queue, client: AsyncClient):
                while True:
                    i, u = await q.get()
                    if u is None:
                        q.task_done()
                        break

                    path = os.path.join(self._download_path, f"{i}.jpg")
                    if os.path.exists(path) and os.path.getsize(path) != 0:
                        return

                    async with aiofiles.open(path, 'wb') as f:
                        await f.write(await (await client.get(u, headers = self._headers)).raise_for_status().aread())

                    q.task_done()

            # async parallel download
            download_queue = asyncio.Queue()
            [download_queue.put_nowait((i, u)) for i, u in enumerate(self._image_url_list)]

            async with httpx.AsyncClient(timeout = 10, proxy = self._proxy) as c:
                tasks = []
                [tasks.append(asyncio.create_task(worker(download_queue, c))) for _ in range(self._thread)]
                await download_queue.join()

                [download_queue.put_nowait((None, None)) for _ in range(self._thread)]
                await asyncio.gather(*tasks)

        self._zip_file_path = os.path.join(self.manga_path, self.title + '.zip')
        self._epub_file_path = os.path.join(self.manga_path, self.title + '.epub')

        if os.path.exists(self._zip_file_path):
            logger.info(f"[Telegraph]: Existed ZIP at \"{self._zip_file_path}\"")
            return 1
        elif os.path.exists(self._epub_file_path):
            logger.info(f"[Telegraph]: Existed EPUB at \"{self._epub_file_path}\"")
            return 1

        os.makedirs(self._download_path, exist_ok = True)
        await download_handler()

    async def _get_info_handler(self, is_zip = False, is_epub = False) -> None:
        async def regex(r: Response):
            self._image_url_list = [
                (self._cf_proxy + full_url) if self._cf_proxy else full_url
                for i in re.findall(r'img src="(.*?)"', r.text)
                for full_url in [urljoin(str(r.url), i)]
            ]

            self._raw_title = re.sub(
                r'\*|\||\?|– Telegraph| |/|:',
                lambda x: {'*': '٭', '|': '丨', '?': '？', '– Telegraph': '', ' ': '', '/': 'ǀ', ':': '∶'}[x.group()],
                BeautifulSoup(r.text, 'html.parser').find("title").text
            )

            if len(self._image_url_list) == 0:
                raise Exception(f"[Telegraph]: Empty URL list, Source: \"{self._url}\"")

            self.thumbnail = self._image_url_list[0]

            title_match = next(
                (re.search(pattern, self._raw_title)
                 for pattern in [r'](.*?\(.*?\))', r'](.*?)[(\[]', r"](.*)"]
                 if re.search(pattern, self._raw_title)), None
            )
            self.title = title_match.group(1) if title_match else self._raw_title

            artist_match = re.search(r'\[(.*?)(?:\((.*?)\))?]', self._raw_title)
            self.artist = artist_match.group(2) or artist_match.group(1) if artist_match else 'その他'

            if is_epub:
                self.manga_path = os.path.join(self.epub_dir, self.artist)
            elif is_zip or re.search(r'Fanbox|FANBOX|FanBox|Pixiv|PIXIV', self.artist):
                self.manga_path = os.path.join(self.komga_dir, self.artist)
            else:
                self.manga_path = os.path.join(self.komga_dir, self.title)

            self._download_path = os.path.join(self._tmp_dir, self.title)
            logger.info(f"[Telegraph]: Started job for '{self._raw_title}'")

        async with AsyncClient(timeout = 10, proxy = self._proxy) as client:
            await regex((await client.get(url = self._url, headers = self._headers)).raise_for_status())

    async def _process_handler(self, is_zip = False, is_epub = False) -> None:
        async def create_zip():
            os.mkdir(self.manga_path) if not os.path.exists(self.manga_path) else None

            with ZipFile(os.path.join(self.manga_path, self.title) + '.zip', 'w', ZIP_DEFLATED) as f:
                for root, _, files in os.walk(self._download_path):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        f.write(file_path, os.path.relpath(file_path, self._download_path))

            logger.info(f"[Telegraph]: Create ZIP at '{self._zip_file_path}'")

        async def create_epub():
            sorted_images = sorted(
                [f for f in os.listdir(self._download_path) if
                 os.path.isfile(os.path.join(self._download_path, f)) and str(f).endswith('.jpg')],
                key = lambda x: int(re.search(r'\d+', x).group())
            )
            async with aiofiles.open(os.path.join(self._download_path, sorted_images[0]), "rb") as f:
                manga_cover = await f.read()

            manga = epub.EpubBook()
            manga.set_title(self.title)
            manga.add_author(self.artist)
            manga.set_cover("cover.jpg", manga_cover)
            manga.set_language('zh') if re.search(r'翻訳|汉化|中國|翻译|中文|中国', self._raw_title) else None

            for i, img_path in enumerate(sorted_images):
                html = epub.EpubHtml(
                    title = f"Page {i + 1}", file_name = f"image_{i + 1}.xhtml",
                    content = f"<html><body><img src='{img_path}'></body></html>".encode('utf8')
                )
                async with aiofiles.open(os.path.join(self._download_path, img_path), "rb") as f:
                    img_byte = await f.read()

                manga.add_item(
                    epub.EpubImage(
                        uid = img_path, file_name = img_path,
                        media_type = "image/jpeg", content = img_byte
                    )
                )
                manga.add_item(html)
                manga.spine.append(html)
                manga.toc.append(epub.Link(html.file_name, html.title, ''))

            manga.add_item(epub.EpubNav())
            manga.add_item(epub.EpubNcx())

            os.mkdir(self.manga_path) if not os.path.exists(self.manga_path) else None
            os.chdir(self.manga_path)
            epub.write_epub(self.title + '.epub', manga, {})
            os.chdir(os.getcwd())
            logger.info(f"[Telegraph]: Create EPUB at '{self._epub_file_path}'")

        async def check_integrity(first_time = True) -> None:
            empty = [file for file in [file for file in os.listdir(self._download_path)]
                     if os.path.getsize(os.path.join(self._download_path, file)) == 0]

            if len(empty) != 0 and first_time:
                await self._task_handler()
                await check_integrity(first_time = False)
            elif len(empty) != 0 and not first_time:
                raise Exception(f"[Telegraph]: Images are broken! Source: \"{self._raw_title}\"")

        await self._get_info_handler(is_zip = is_zip, is_epub = is_epub)

        if await self._task_handler() == 1:
            return

        await check_integrity()
        await create_zip() if is_zip else await create_epub()

    async def get_epub(self) -> str:
        """Successfully get epub, return file path, else raise exception"""
        try:
            await self._process_handler(is_epub = True)
            return self._epub_file_path
        except Exception as exc:
            raise exc

    async def get_zip(self):
        try:
            return await self._process_handler(is_zip = True)
        except Exception as exc:
            raise exc

    async def get_info(self):
        return await self._get_info_handler()
