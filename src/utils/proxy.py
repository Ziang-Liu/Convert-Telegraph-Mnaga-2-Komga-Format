from httpx import URL, Proxy, Client
from httpx_socks import SyncProxyTransport

from .logger import logger


def proxy_init(proxy: URL | str | None) -> Proxy | None:
    if not proxy:
        return None

    if isinstance(proxy, str):
        proxy = URL(proxy)

    if proxy.scheme not in ("http", "https", "socks5"):
        logger.error(f"[Proxy]: Unknown scheme for proxy URL {proxy!r}")
        exit(1)

    if proxy.port is None:
        logger.error("[Proxy]: No port specified.")
        exit(1)

    _test(str(proxy))

    if proxy.username or proxy.password == '':
        notice = f"{proxy.scheme}://username:password@{proxy.host}:{proxy.port}"
        logger.info(f"[Proxy]: If you have authorization secret, use {notice} like this.")

        return Proxy(url = proxy)

    return Proxy(url = proxy, auth = (proxy.username, proxy.password))


def _test(proxy: str):
    transport = SyncProxyTransport.from_url(proxy)
    client = Client(transport = transport)

    try:
        client.get("https://api.telegram.org", follow_redirects = True).raise_for_status()
    except Exception as exc:
        logger.error(f"[Proxy]: Error occurred when initializing proxy: {exc}")
        exit(1)
    finally:
        client.close()
