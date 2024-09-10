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
    def __init__(self, url: str, proxy: Optional[Proxy] = None, cf_proxy: Optional[str] = None) -> None:
        self.url = f'{cf_proxy}/{url}' if cf_proxy else url
        self._proxy = proxy
        self._cf_proxy = cf_proxy
        self._headers = {'User-Agent': UserAgent().random}

        self.title_raw: Optional[str] = None
        self.title: Optional[str] = None
        self.artist: Optional[str] = None
        self.thumbnail: Optional[str | URL] = None
        self._image_url_list = []

        env = EnvironmentReader()
        self._thread = env.get_variable("TELEGRAPH_THREADS")

        # declared in bot/Main.py
        self.komga_folder = '/neko/komga'
        self.epub_folder = '/neko/epub'
        self._temp_folder = '/neko/.temp'

        # remove cache folders last longer than 1 day
        for root, dirs, _ in os.walk(self._temp_folder):
            for temp_dir in dirs:
                path = os.path.join(root, temp_dir)
                modified_time = datetime.fromtimestamp(os.path.getmtime(path))
                shutil.rmtree(path) if datetime.now() - modified_time > timedelta(days = 1) else None

        # generated path
        self.manga_path = self._temp_folder
        self._epub_file_path = self._temp_folder
        self._zip_file_path = self._temp_folder
        self._download_path = self._temp_folder

    async def _task_handler(self) -> str:
        async def image_handler(client: AsyncClient, url, image_path):
            async def write_image(response: Response, target_path) -> None:
                if os.path.exists(target_path) and os.path.getsize(target_path) != 0:
                    return

                async with aiofiles.open(target_path, 'wb') as f:
                    await f.write(await response.aread())

            resp = await client.get(url, headers = self._headers)
            await write_image(resp.raise_for_status(), image_path)

        async def create_queue():
            async def worker(queue: asyncio.Queue, client: AsyncClient):
                while True:
                    _num, _url = await queue.get()
                    if _url is None:
                        queue.task_done()
                        break

                    await image_handler(client, _url, os.path.join(self._download_path, f'{_num}.jpg'))
                    queue.task_done()

            fixed_length_rank = asyncio.Queue()
            [fixed_length_rank.put_nowait((i, img_url)) for i, img_url in enumerate(self._image_url_list)]

            async with httpx.AsyncClient(timeout = 10, proxy = self._proxy) as _client:
                tasks = []
                [tasks.append(asyncio.create_task(worker(fixed_length_rank, _client))) for _ in range(self._thread)]
                await fixed_length_rank.join()
                [fixed_length_rank.put_nowait((None, None)) for _ in range(self._thread)]
                await asyncio.gather(*tasks)

        self._zip_file_path = os.path.join(self.manga_path, self.title + '.zip')
        self._epub_file_path = os.path.join(self.manga_path, self.title + '.epub')

        if os.path.exists(self._zip_file_path) or os.path.exists(self._epub_file_path):
            logger.info(f"[Telegraph]: Skip existed file '{self.title}'")
            return "EXIST"

        os.makedirs(self._download_path, exist_ok = True)
        await create_queue()

    async def _get_info_handler(self, is_zip = False, is_epub = False) -> None:
        async def regex(r: Response) -> None:
            self._image_url_list = [
                (self._cf_proxy + full_url) if self._cf_proxy else full_url
                for i in re.findall(r'img src="(.*?)"', r.text)
                for full_url in [urljoin(str(r.url), i)]
            ]

            self.title_raw = re.sub(
                r'\*|\||\?|– Telegraph| |/|:',
                lambda x: {'*': '٭', '|': '丨', '?': '？', '– Telegraph': '', ' ': '', '/': 'ǀ', ':': '∶'}[x.group()],
                BeautifulSoup(r.text, 'html.parser').find("title").text
            )

            if len(self._image_url_list) == 0:
                raise Exception(f'Image url list is empty for {self.url}')

            self.thumbnail = self._image_url_list[0]

            title_match = next(
                (re.search(pattern, self.title_raw)
                 for pattern in [r'](.*?\(.*?\))', r'](.*?)[(\[]', r"](.*)"]
                 if re.search(pattern, self.title_raw)), None
            )
            self.title = title_match.group(1) if title_match else self.title_raw

            artist_match = re.search(r'\[(.*?)(?:\((.*?)\))?]', self.title_raw)
            self.artist = artist_match.group(2) or artist_match.group(1) if artist_match else 'その他'

            if is_epub:
                self.manga_path = os.path.join(self.epub_folder, self.artist)
            elif is_zip or re.search(r'Fanbox|FANBOX|FanBox|Pixiv|PIXIV', self.artist):
                self.manga_path = os.path.join(self.komga_folder, self.artist)
            else:
                self.manga_path = os.path.join(self.komga_folder, self.title)

            self._download_path = os.path.join(self._temp_folder, self.title)
            logger.info(f"[Telegraph]: Start job for '{self.title_raw}'")

        async with AsyncClient(timeout = 10, proxy = self._proxy) as client:
            resp = await client.get(url = self.url, headers = self._headers)
            await regex(resp.raise_for_status())

    async def _process_handler(self, is_zip = False, is_epub = False) -> None:
        async def create_zip() -> None:
            os.mkdir(self.manga_path) if not os.path.exists(self.manga_path) else None

            output = os.path.join(self.manga_path, self.title) + '.zip'
            with ZipFile(output, 'w', ZIP_DEFLATED) as output_zip:
                for root, _, files in os.walk(self._download_path):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        rel = os.path.relpath(file_path, self._download_path)
                        output_zip.write(file_path, rel)

            logger.info(f"[Telegraph]: Create zip '{output}'")

        async def create_epub() -> None:
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
            manga.set_language('zh') if re.search(r'翻訳|汉化|中國|翻译|中文|中国', self.title_raw) else None

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
            logger.info(f"[Telegraph]: Create epub '{self.title + '.epub'}'")

        async def check_integrity(first_time = True) -> None:
            empty = [file for file in [file for file in os.listdir(self._download_path)]
                     if os.path.getsize(os.path.join(self._download_path, file)) == 0]

            if len(empty) != 0 and first_time:
                await self._task_handler()
                await check_integrity(first_time = False)
            elif len(empty) != 0 and not first_time:
                raise Exception(f"Download Images are broken for {self.title}")

        await self._get_info_handler(is_zip = is_zip, is_epub = is_epub)

        if await self._task_handler() == "EXIST":
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
