import abc
import time
import urllib.request
import urllib.error
import ssl

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7',
}

class ScraperFetchError(Exception):
    """Raised when a URL fetch fails after exhausting all retries."""
    def __init__(self, url, status_code=None, message=""):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Fetch failed for {url} [status: {status_code}]: {message}")

class BaseScraper(abc.ABC):
    def __init__(self, headers=None, rate_limit_delay=0.15):
        self.headers = headers or DEFAULT_HEADERS
        self.rate_limit_delay = rate_limit_delay

    def fetch_url(self, url, timeout=15, max_retries=4):
        """Fetch URL with exponential retry on 429/timeouts and user-agent spoofing."""
        last_error = None
        last_status = None

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
                    return resp.read().decode('utf-8', errors='replace')
            except urllib.error.HTTPError as e:
                last_error = e
                last_status = e.code
                if e.code == 429:
                    wait_time = 2.0 * (2 ** attempt)
                    time.sleep(wait_time)
                elif attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    raise ScraperFetchError(url, status_code=last_status, message=str(e)) from e
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    raise ScraperFetchError(url, status_code=last_status, message=str(e)) from e

        raise ScraperFetchError(url, status_code=last_status, message=f"Exhausted {max_retries} retries: {last_error}")

    @abc.abstractmethod
    def scrape_wet(self):
        """Scrape wet cat food catalog and PDP details. Returns list of raw product dicts."""
        pass

    @abc.abstractmethod
    def scrape_dry(self):
        """Scrape dry cat food catalog and PDP details. Returns list of raw product dicts."""
        pass
