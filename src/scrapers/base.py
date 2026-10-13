import abc
import urllib.request
import time

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7',
}

class BaseScraper(abc.ABC):
    def __init__(self, headers=None, rate_limit_delay=0.15):
        self.headers = headers or DEFAULT_HEADERS
        self.rate_limit_delay = rate_limit_delay

    def fetch_url(self, url, timeout=15, max_retries=4):
        """Fetch URL with exponential retry on 429/timeouts and user-agent spoofing."""
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode('utf-8', errors='replace')
            except Exception as e:
                # On rate limit (429), back off longer
                err_str = str(e)
                if '429' in err_str:
                    wait_time = 2.0 * (2 ** attempt)
                    time.sleep(wait_time)
                elif attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    print(f"[Scraper] Failed fetching {url}: {e}")
                    raise
        return None

    @abc.abstractmethod
    def scrape_wet(self):
        """Scrape wet cat food catalog and PDP details. Returns list of raw product dicts."""
        pass

    @abc.abstractmethod
    def scrape_dry(self):
        """Scrape dry cat food catalog and PDP details. Returns list of raw product dicts."""
        pass
