import asyncio
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import randint
from sqlite3 import connect, Cursor
from typing import Optional, List, Dict, Union, Match
from urllib.parse import urljoin
from zipfile import ZipFile, ZIP_DEFLATED

import aiofiles
import httpx
from bs4 import BeautifulSoup
from ebooklib import epub
from fake_useragent import UserAgent
from httpx import URL, AsyncClient, Proxy, Response

from src.utils import EnvironmentReader, logger


class Telegraph:
    def __init__(
            self,
            telegraph_url: str,
            proxy: Optional[Proxy] = None,
            cloudflare_workers_proxy: Optional[str] = None
    ):
        self._urls: List[str] = [
            f'{cloudflare_workers_proxy}/{telegraph_url}' if cloudflare_workers_proxy else telegraph_url
        ]

        self._proxy: Optional[Proxy] = proxy
        self._cf_proxy: Optional[str] = cloudflare_workers_proxy

        self._headers: Dict[str, str] = {'User-Agent': UserAgent().random}
        self._images: List[Optional[str]] = []  # image urls get from article
        self._host: Optional[str] = None  # show in debug message

        self._raw_title: Optional[str] = None
        self.title: Optional[str] = None
        self.artist: Optional[str] = None
        self.thumbnail: Optional[str | URL] = None  # equals to self._images[0]

        env = EnvironmentReader()
        self._thread = env.get_variable("TELEGRAPH_THREADS")

        # declared in bot/main.py
        self._komga_dir = '/neko/komga'
        self._epub_dir = '/neko/epub'
        self._tmp_dir = '/neko/.temp'

        # generated path
        self._file_dir = self._file_path = self._download_dir = self._tmp_dir

        # remove cache folders last longer than 1 day
        for root, dirs, _ in os.walk(self._tmp_dir):
            for temp_dir in dirs:
                path = os.path.join(root, temp_dir)
                modified_time = datetime.fromtimestamp(os.path.getmtime(path))
                shutil.rmtree(path) if datetime.now() - modified_time > timedelta(days = 1) else None

    async def _task_handler(self, timeout: int) -> int:
        async def download_handler():
            async def worker(q: asyncio.Queue, client: AsyncClient):
                while True:
                    i, u, r = await q.get()
                    if not u:
                        q.task_done()
                        break

                    p = os.path.join(self._download_dir, f"{i}.jpg")
                    if os.path.exists(p):
                        logger.debug(f"[Telegraph]: Skip existed '{p}'")
                        q.task_done()
                        continue

                    try:
                        resp = (await client.get(u, headers = self._headers, timeout = timeout)).raise_for_status()
                        if not resp.content:
                            raise OSError(f"'{self._host}' respond no content for '{p}'")
                    except (httpx.HTTPError, OSError) as _e1:
                        if r != 3:
                            logger.warning(f"[Telegraph]: Failed to download '{p}', retry time {r + 1}")
                            q.task_done()
                            q.put_nowait((i, u, r + 1))
                        else:
                            logger.error(f"[Telegraph]: Failed to download '{p}' because '{str(_e1)}'")
                            q.task_done()

                        continue

                    try:
                        async with aiofiles.open(p, 'wb') as f:
                            await f.write(await resp.aread())

                        logger.debug(f"[Telegraph]: Image download complete for '{p}'")
                    except Exception as _e2:
                        logger.error(f"[Telegraph]: Failed to write image '{p}': {str(_e2)}")

                    q.task_done()

            dq = asyncio.Queue()
            for num, url in enumerate(self._images):
                dq.put_nowait((num, url, 0))

            logger.debug(f"[Telegraph]: Queue Length: {len(self._images)}, Service host: {self._host}")

            async with httpx.AsyncClient(proxy = self._proxy) as c:
                tasks = []
                for _ in range(self._thread):
                    tasks.append(asyncio.create_task(worker(dq, c)))

                await dq.join()

            for _ in range(self._thread):
                dq.put_nowait((None, None, None))

            await asyncio.gather(*tasks)

        async def check():
            for root, _, files in os.walk(self._download_dir):
                if len(files) != len(self._images):
                    raise ValueError(f"Missing {len(self._images) - len(files)} files in '{self._download_dir}'")
                for f in files:
                    if os.path.getsize(os.path.join(root, f)) == 0:
                        raise ValueError(f"'{os.path.join(root, f)}' is empty")

        # execute script
        if os.path.exists(self._file_path):
            logger.debug(f"[Telegraph]: Skip existed file at '{self._file_path}'")
            return 1

        os.makedirs(self._download_dir, exist_ok = True)
        await download_handler()
        await check()

        return 0

    async def _get_info_handler(self, is_zip = False, is_epub = False):
        def get_title(raw: str) -> Match[str] | None:
            return next(
                (re.search(pattern, raw) for pattern in [r'](.*?\(.*?\))', r'](.*?)[(\[]', r"](.*)"]
                 if re.search(pattern, raw)), None)

        def clean_symbols(raw: str, replace: bool = True) -> str:
            pr = {
                '*': '٭',
                '|': '丨',
                '?': '？',
                '– Telegraph': '',
                ' ': '',
                '/': 'ǀ',
                ':': '∶',
                '【': '[',
                '】': ']'
            }
            pc = {
                '[': '',
                ']': '',
                '(': '',
                ')': '',
                ' ': ''
            }
            escaped_p = {re.escape(key): value for key, value in (pr if replace else pc).items()}
            return re.sub('|'.join(escaped_p.keys()), lambda x: escaped_p[re.escape(x.group())], raw)

        async def regex(r: Response):
            self._urls += [
                f"{self._cf_proxy}/{full_url}" if self._cf_proxy else full_url
                for i in re.findall(r'a href="(.*?)"', r.text)
                for full_url in [urljoin(str(r.url), i)]
                if full_url.startswith("https://telegra.ph")
            ]
            self._images = [
                f"{self._cf_proxy}/{full_url}" if self._cf_proxy else full_url
                for r_ex in (
                    [r] if len(self._urls) == 1 else
                    [await client.get(url) for url in self._urls[1:]]
                )
                for i in re.findall(r'img src="(.*?)"', r_ex.text)
                for full_url in [urljoin(str(r_ex.url), i)]
            ]
            self._host = URL(self._images[0]).host
            self._raw_title = clean_symbols(BeautifulSoup(r.text, 'html.parser').find("title").text).strip()

            if len(self._images) == 0:
                raise ValueError(f"No images from '{self._urls}'")

            self.thumbnail = self._images[0]

            matched_title = get_title(self._raw_title)
            if matched_title.group(1).startswith('(') and matched_title.group(1).endswith(')'):
                matched_title = get_title(self._raw_title.replace(matched_title.group(1), ''))

            if not matched_title or matched_title.group(1) == '':
                self.title = self._raw_title
                self.artist = "その他"
            else:
                self.title = clean_symbols(matched_title.group(1), False).strip()
                matched_artist = re.search(r'\[(.*?)(?:\((.*?)\))?]', self._raw_title)
                self.artist = matched_artist.group(2) or matched_artist.group(1) if matched_artist else "その他"
                self.artist = clean_symbols(self.artist, False).strip()

            if is_epub:
                self._file_dir = os.path.join(self._epub_dir, self.artist)
            elif is_zip or re.search(r"Fanbox|FANBOX|FanBox|Pixiv|PIXIV", self.artist):
                self._file_dir = os.path.join(self._komga_dir, self.artist)
            else:
                self._file_dir = os.path.join(self._komga_dir, self.title)

            self._download_dir = os.path.join(self._tmp_dir, self.title)
            self._file_path = os.path.join(self._file_dir, f"{self.title}.{'zip' if is_zip else 'epub'}")

        # execute script
        async with AsyncClient(timeout = 10, proxy = self._proxy) as client:
            await regex((await client.get(url = self._urls[0], headers = self._headers)).raise_for_status())

    async def _process_handler(self, is_zip = False, is_epub = False) -> Optional[int]:
        async def create_zip():
            os.mkdir(self._file_dir) if not os.path.exists(self._file_dir) else None

            with ZipFile(os.path.join(self._file_dir, self.title) + '.zip', 'w', ZIP_DEFLATED) as f:
                for root, _, files in os.walk(self._download_dir):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        f.write(file_path, os.path.relpath(file_path, self._download_dir))

            logger.debug(f"[Telegraph]: Create ZIP file at '{self._file_path}'")

        async def create_epub():
            manga = epub.EpubBook()
            manga.set_title(self.title)
            manga.add_author(self.artist)
            manga.set_language('zh') if re.search(r'翻訳|汉化|中國|翻译|中文|中国', self._raw_title) else None

            sorted_images = sorted(
                [f for f in os.listdir(self._download_dir) if
                 os.path.isfile(os.path.join(self._download_dir, f)) and str(f).endswith('.jpg')],
                key = lambda x: int(re.search(r'\d+', x).group())
            )

            async with aiofiles.open(os.path.join(self._download_dir, sorted_images[0]), "rb") as f:
                manga.set_cover("cover.jpg", await f.read())

            for i, path in enumerate(sorted_images):
                html = epub.EpubHtml(title = f"Page {i + 1}", file_name = f"image_{i + 1}.xhtml",
                                     content = f"<html><body><img src='{path}'></body></html>".encode('utf8'))

                async with aiofiles.open(os.path.join(self._download_dir, path), "rb") as f:
                    manga.add_item(epub.EpubImage(
                        uid = path, file_name = path, media_type = "image/jpeg", content = await f.read()))

                manga.add_item(html)
                manga.spine.append(html)
                manga.toc.append(epub.Link(html.file_name, html.title, ''))

            manga.add_item(epub.EpubNav())
            manga.add_item(epub.EpubNcx())

            os.mkdir(self._file_dir) if not os.path.exists(self._file_dir) else None
            os.chdir(self._file_dir)
            epub.write_epub(f"{self.title}.epub", manga, {})
            os.chdir(os.getcwd())
            logger.debug(f"[Telegraph]: Create EPUB file at '{self._file_path}'")

        async def fun_handler(func, *args):
            for attempt in range(1, 4):
                try:
                    return await func(*args)
                except (httpx.HTTPError, ValueError) as hve:
                    if attempt == 3:
                        raise Exception(f"{func.__name__} failed with {hve}")

                    logger.warning(f"[Telegraph]: {func.__name__} failed: {hve}, retry time {attempt}")

        # execute script
        if not self._raw_title:
            await fun_handler(self._get_info_handler, is_zip, is_epub)

        logger.info(f"[Telegraph]: Get task '{self._raw_title}'")

        return_value = await self._task_handler(timeout = 3)
        if return_value == 1:
            return
        elif return_value == 2:
            try:
                await fun_handler(self._process_handler, is_zip, is_epub)
            except Exception as _e:
                logger.error(f"[Telegraph]: {_e}")
                return 1
        else:
            await create_zip() if is_zip else await create_epub()

    async def get_epub(self) -> Optional[str]:
        """Pack manga to epub format and return file path"""
        start = time.time()
        if await self._process_handler(is_epub = True) == 1:
            return None

        logger.info(f"[Telegraph]: Task '{self._raw_title}' finished in {round(time.time() - start, 2)} seconds")
        return self._file_path

    async def get_zip(self) -> Optional[str]:
        """Pack manga to zip format"""
        start = time.time()
        if not await self._process_handler(is_zip = True):
            return None

        logger.info(f"[Telegraph]: Task '{self._raw_title}' finished in {round(time.time() - start, 2)} seconds")
        return self._file_path

    async def get_info(self):
        """Gey basic info from Telegraph link"""
        return await self._get_info_handler()


class TelegraphDatabase:
    @dataclass
    class TelegraphData:
        """
        title: The title of the Telegraph Manga.
        file_location: Download Location, get from Telegraph().
        original_url: (Optional) The original URL of the content, which can be either an EX, NH, or EH URL.
        preview_url: (Optional) Telegraph Link: "https://telegra.ph/{title}".
        language: (Optional) A list of language tags.
        artist: (Optional) A list of artist tags.
        team: (Optional) A list of team tags.
        original: (Optional) A list of original works or sources related to the content.
        characters: (Optional) A list of characters tags.
        male: (Optional) A list of male tags.
        female: (Optional) A list of female tags.
        others.: (Optional) A list of any other relevant tags.
        """
        title: str = ''
        file_location: str = ''
        tag_id: Optional[int] = None
        telegraph_id: Optional[int] = None
        time_added: Optional[str] = None
        original_url: Optional[str] = None
        preview_url: Optional[str] = None
        language: Optional[List[str]] = None
        artist: Optional[List[str]] = None
        team: Optional[List[str]] = None
        original: Optional[List[str]] = None
        characters: Optional[List[str]] = None
        male: Optional[List[str]] = None
        female: Optional[List[str]] = None
        others: Optional[List[str]] = None

        def __post_init__(self, *args, **kwargs):
            attributes = [
                'title', 'file_location', 'tag_id', 'telegraph_id',
                'time_added', 'original_url', 'preview_url',
                'language', 'artist', 'team', 'original',
                'characters', 'male', 'female', 'others'
            ]

            for i, attr in enumerate(attributes):
                if i < len(args):
                    setattr(self, attr, args[i])

            for key, value in kwargs.items():
                if key in attributes:
                    setattr(self, key, value)

    def __init__(self):
        self._attrs = ['tag_id', 'time_added', 'title', 'original_url', 'preview_url',
                       'file_location', 'telegraph_id', 'lang', 'artist', 'team',
                       'original', 'characters', 'male', 'female', 'others']

        if not os.path.exists("../telegraph.db"):
            logger.info("[TelegraphDatabase]: Initializing new database...")
            self._database = connect("../telegraph.db")

            cursor = self._database.cursor()
            _script = [
                """
                CREATE TABLE telegraph (
                    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time_added DATE,
                    title VARCHAR(100) NOT NULL,
                    original_url VARCHAR(200),
                    preview_url VARCHAR(200),
                    file_location VARCHAR(200),
                    FOREIGN KEY (tag_id) REFERENCES tag(telegraph_id)
                );
                """,
                """
                CREATE TABLE tag (
                    telegraph_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lang JSON,
                    artist JSON,
                    team JSON,
                    original JSON,
                    characters JSON,
                    male JSON,
                    female JSON,
                    others JSON,
                    FOREIGN KEY (telegraph_id) REFERENCES telegraph(tag_id)
                );
                """,
                """
                CREATE INDEX idx_telegraph_tag_id ON telegraph (tag_id);
                """,
                """
                CREATE INDEX idx_telegraph_name ON telegraph (title);
                """,
                """
                CREATE INDEX idx_tag_telegraph_id ON tag (telegraph_id);
                """,
                """
                CREATE INDEX idx_tag_language ON tag (lang);
                """,
                """
                CREATE INDEX idx_tag_artist ON tag (artist);
                """,
                """
                CREATE INDEX idx_tag_team ON tag (team);
                """,
                """
                CREATE INDEX idx_tag_original ON tag (original);
                """,
                """
                CREATE INDEX idx_tag_character ON tag (characters);
                """,
                """
                CREATE INDEX idx_tag_male ON tag (male);
                """,
                """
                CREATE INDEX idx_tag_female ON tag (female);
                """,
                """
                CREATE INDEX idx_tag_others ON tag (others);
                """,
            ]
            [cursor.execute(script) for script in _script]
            self._database.commit()
            cursor.close()
        else:
            self._database = connect("../telegraph.db")

    def new(self, data: Union[Dict, List]) -> TelegraphData:
        """
        Get an empty TelegraphData instance, or deliver a List or a Dict to fill some params.

        Example:
            new({
                'Manga Title',  # 位置参数: title
                'file/location',  # 位置参数: file_location
                tag_id=1,  # 关键字参数: tag_id
                original_url='https://example.com',  # 关键字参数: original_url
                language=['English', 'Japanese'],  # 关键字参数: language
                artist=['Artist Name'],  # 关键字参数: artist
                team=['Team Name'],  # 关键字参数: team
                others=['Some other tags']  # 关键字参数: others
            })
        """

        if isinstance(data, Dict):
            return self.TelegraphData(**{k: v for k, v in data.items() if k in self.TelegraphData.__annotations__})
        if isinstance(data, List):
            return self.TelegraphData(*data)

    async def insert(
            self,
            data: TelegraphData,
            telegraph_task: Optional[Telegraph] = None
    ):
        """
        Insert filled data into the Telegraph database.
        Please ensure data's integrity.
        """
        if telegraph_task:
            data.file_location = await telegraph_task.get_zip()
            if not data.file_location:
                return

            data.title = telegraph_task.title

        cursor = self._database.cursor()
        telegraph_script = \
            """
            INSERT INTO telegraph (time_added, title, original_url, preview_url, file_location)
            VALUES (?, ?, ?, ?, ?)
            """
        tag_script = \
            """
            INSERT INTO tag (lang, artist, team, original, characters, male, female, others)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
        cursor.execute(telegraph_script, (
            datetime.today(), data.title,
            data.original_url, data.preview_url, data.file_location))
        cursor.execute(tag_script, (
            f'{data.language}', f'{data.artist}', f'{data.team}', f'{data.original}',
            f'{data.characters}', f'{data.male}', f'{data.female}', f'{data.others}'
        ))
        self._database.commit()
        logger.info(f"[Telegraph]: Add {data.title} to telegraph database")
        cursor.close()

    async def remove(self, idx: int):
        """Delete a Telegraph entry."""
        cursor = self._database.cursor()
        script = ["DELETE FROM telegraph WHERE tag_id = ?", "DELETE FROM tag WHERE telegraph_id = ?"]
        [cursor.execute(script, (idx,)) for script in script]

        self._database.commit()
        cursor.close()

    async def modify(self, table: int, attr: int, idx: int, elem: str | List[str]):
        """
        Modify a Telegraph entry.

        :param table telegraph = 0, tag = 1
        :param attr tag_id = 0, time_added = 1, title = 2, original_url = 3, preview_url = 4,
                    file_location = 5, telegraph_id = 6, lang = 7, artist = 8, team = 9,
                    original = 10, characters = 11, male = 12, female = 13, others = 14
        :param idx primary key index number
        :param elem see members in TelegraphData()
        """
        if (table == 0 and attr > 5) or (table == 1 and attr < 6):
            raise Exception(f"No attribute {attr} in {table}.")

        cursor = self._database.cursor()
        script = \
            f"""
            UPDATE {'telegraph' if table == 0 else 'tag'} SET {self._attrs[attr]} = ?
            WHERE {'tag_id' if table == 0 else 'telegraph_id'} = ?
            """

        cursor.execute(script, (idx, elem))
        self._database.commit()
        cursor.close()

    async def check_health(self):
        cursor = self._database.cursor()

        if not (cursor.execute("PRAGMA integrity_check").fetchall())[0][0] == 'ok':
            cursor.close()
            raise Exception("Database health check failed.")

        cursor.close()

    async def disconnect(self):
        self._database.close()

    def _return_search_result(self, cursor: Cursor) -> List[Optional[TelegraphData]]:
        result = cursor.fetchall()
        self._database.commit()
        cursor.close()
        return [self.TelegraphData(**{k: r[i] for i, k in enumerate(self._attrs) if k in self._attrs}) for r in result]

    async def search_by_title(self, key: str) -> List[Optional[TelegraphData]]:
        cursor = self._database.cursor()
        script = \
            """
            SELECT * FROM telegraph
            JOIN tag ON telegraph.tag_id = tag.telegraph_id
            WHERE title LIKE ?;
            """
        cursor.execute(script, (f"%{key}%",))
        return self._return_search_result(cursor)

    async def search_by_tag(self, key: str) -> List[Optional[TelegraphData]]:
        cursor = self._database.cursor()
        script = \
            """
            SELECT * FROM telegraph
            WHERE tag_id = (
                SELECT telegraph_id FROM tag
                WHERE EXISTS (
                    SELECT 1
                    FROM (
                        SELECT * FROM json_each(lang) UNION ALL
                        SELECT * FROM json_each(artist) UNION ALL
                        SELECT * FROM json_each(team) UNION ALL
                        SELECT * FROM json_each(original) UNION ALL
                        SELECT * FROM json_each(characters) UNION ALL
                        SELECT * FROM json_each(male) UNION ALL
                        SELECT * FROM json_each(female) UNION ALL
                        SELECT * FROM json_each(others)
                    ) AS keywords
                    WHERE keywords.value = ?
                )
            );
            """
        cursor.execute(script, (key,))
        return self._return_search_result(cursor)

    async def random(self):
        cursor = self._database.cursor()
        script = \
            """
            SELECT * FROM telegraph
            JOIN tag ON telegraph.tag_id = tag.telegraph_id
            WHERE tag_id = ?
            ORDER BY random()
            LIMIT 1
            """
        cursor.execute(script, (randint(0, 100),))
        return self._return_search_result(cursor)
