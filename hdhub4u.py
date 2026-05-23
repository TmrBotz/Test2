import os
import re
from datetime import datetime

from .base import BaseScraper


QUALITY_PATTERNS = re.compile(
    r"(4k|2160p|1080p|720p|480p|360p|HEVC|x264|x265|WEB-DL|HDRip|BluRay|MULTI)",
    re.IGNORECASE,
)

DOWNLOAD_SECTION_PATTERN = re.compile(
    r"(download|dl|link)", re.IGNORECASE
)


class HDHub4UScraper(BaseScraper):

    @property
    def name(self) -> str:
        return "hdhub4u"

    @property
    def rss_url(self) -> str:
        return os.environ.get(
            "HDHUB4U_RSS",
            "https://new1.hdhub4u.limo/feed/"
        )

    @property
    def channel_id(self) -> str:
        return os.environ["-1002233093561"]

    # =========================================================
    # MAIN SCRAPER
    # =========================================================

    def scrape_links(self, movie_url: str) -> list:

        self.log.info(f"Scraping: {movie_url}")

        soup = self.get_soup(movie_url)

        if not soup:
            return []

        results = []
        seen = set()

        # -----------------------------------------------------
        # Strategy 1
        # -----------------------------------------------------

        for tag in soup.find_all(["h2", "h3", "h4", "p", "div"]):

            text = tag.get_text(" ", strip=True)

            if any(x in text.upper() for x in [
                "WATCH",
                "PLAYER",
                "SCREENSHOT",
                "STORYLINE",
                "REVIEW"
            ]):
                continue

            quality = self._extract_quality_label(text)

            for a in tag.find_all("a", href=True):

                href = a["href"].strip()

                if not href.startswith("http"):
                    continue

                # skip useless
                if any(skip in href for skip in [
                    "youtube.com",
                    "youtu.be",
                    "catimages.org",
                    "facebook.com",
                    "twitter.com",
                    "instagram.com"
                ]):
                    continue

                # skip watch/player
                anchor_text = a.get_text(" ", strip=True).upper()

                if any(x in anchor_text for x in [
                    "WATCH",
                    "PLAYER",
                    "SCREENSHOT",
                    "TRAILER"
                ]):
                    continue

                key = f"{quality}-{href}"

                if key in seen:
                    continue

                seen.add(key)

                # recursive resolve
                final_links = self.resolve_recursive(href)

                if not final_links:
                    final_links = [href]

                results.append({
                    "quality": quality or "Download Link",
                    "final_links": list(dict.fromkeys(final_links))
                })

                self.log.info(
                    f"✓ {quality} -> {len(final_links)} links"
                )

        # -----------------------------------------------------
        # fallback
        # -----------------------------------------------------

        if not results:

            self.log.warning("Fallback extraction")

            links = self.extract_hosting_links(soup)

            if links:
                results.append({
                    "quality": "Download Links",
                    "final_links": links
                })

        self.log.info(f"Total qualities: {len(results)}")

        return results

    # =========================================================
    # QUALITY
    # =========================================================

    def _extract_quality_label(self, text: str) -> str:

        if not text:
            return ""

        text = re.sub(r"[⚡🔥💥]", "", text)
        text = re.sub(r"\s+", " ", text).strip()

        return text[:80]

    # =========================================================
    # RECURSIVE RESOLVER
    # =========================================================

    def resolve_recursive(self, url: str, visited=None) -> list:

        if visited is None:
            visited = set()

        if url in visited:
            return []

        visited.add(url)

        final_links = []

        try:

            # -------------------------------------------------
            # gadgetsweb
            # -------------------------------------------------

            if "gadgetsweb.xyz" in url:

                resolved = self.resolve_gadgetsweb(url)

                if resolved and resolved != url:

                    return self.resolve_recursive(
                        resolved,
                        visited
                    )

            # -------------------------------------------------
            # hubdrive
            # -------------------------------------------------

            elif "hubdrive.space/file/" in url:

                links = self.scrape_hubdrive_page(url)

                for link in links:

                    final_links.extend(
                        self.resolve_recursive(
                            link,
                            visited
                        )
                    )

                final_links.append(url)

            # -------------------------------------------------
            # hubcloud
            # -------------------------------------------------

            elif "hubcloud.foo/drive/" in url:

                resolved = self.resolve_hubcloud(url)

                if resolved:

                    final_links.extend(
                        self.resolve_recursive(
                            resolved,
                            visited
                        )
                    )

                final_links.append(url)

            # -------------------------------------------------
            # gamerxyt
            # -------------------------------------------------

            elif "gamerxyt.com/hubcloud.php" in url:

                mirrors = self.resolve_gamerxyt(url)

                for mirror in mirrors:

                    if any(x in mirror for x in [
                        "hubdrive.space/file/",
                        "hubcloud.foo/drive/",
                        "gadgetsweb.xyz",
                        "gamerxyt.com/hubcloud.php"
                    ]):

                        final_links.extend(
                            self.resolve_recursive(
                                mirror,
                                visited
                            )
                        )

                    else:
                        final_links.append(mirror)

                final_links.append(url)

            # -------------------------------------------------
            # direct/final
            # -------------------------------------------------

            else:
                final_links.append(url)

        except Exception as e:

            self.log.error(
                f"Recursive resolve failed: {e}"
            )

        return list(dict.fromkeys(final_links))

    # =========================================================
    # GADGETSWEB
    # =========================================================

    def resolve_gadgetsweb(self, url: str) -> str:

        try:

            resp = self.session.get(
                url,
                timeout=15,
                allow_redirects=True
            )

            if resp.url and resp.url != url:
                return resp.url

            html = resp.text

            match = re.search(
                r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]",
                html,
                re.IGNORECASE
            )

            if match:
                return match.group(1).strip()

        except Exception as e:

            self.log.error(
                f"gadgetsweb resolve failed: {e}"
            )

        return url

    # =========================================================
    # HUBDRIVE
    # =========================================================

    def scrape_hubdrive_page(self, url: str) -> list:

        links = []

        try:

            soup = self.get_soup(url)

            if not soup:
                return links

            # normal links
            for a in soup.find_all("a", href=True):

                href = a["href"].strip()

                if not href.startswith("http"):
                    continue

                if any(skip in href for skip in [
                    "facebook.com",
                    "twitter.com",
                    "snvhost.com"
                ]):
                    continue

                links.append(href)

            # hidden form links
            for form in soup.find_all("form"):

                inp = form.find(
                    "input",
                    {"name": "r"}
                )

                if inp and inp.get("value"):

                    val = inp["value"].strip()

                    if val.startswith("http"):
                        links.append(val)

        except Exception as e:

            self.log.error(
                f"hubdrive scrape failed: {e}"
            )

        return list(dict.fromkeys(links))

    # =========================================================
    # HUBCLOUD
    # =========================================================

    def resolve_hubcloud(self, url: str) -> str:

        try:

            soup = self.get_soup(url)

            if not soup:
                return url

            a = soup.find(
                "a",
                id="download",
                href=True
            )

            if a:

                href = a["href"].strip()

                if href.startswith("http"):
                    return href

            for a in soup.find_all("a", href=True):

                href = a["href"].strip()

                if "hubcloud.php" in href:
                    return href

        except Exception as e:

            self.log.error(
                f"hubcloud resolve failed: {e}"
            )

        return url

    # =========================================================
    # GAMERXYT
    # =========================================================

    def resolve_gamerxyt(self, url: str) -> list:

        results = []

        try:

            resp = self.session.get(
                url,
                timeout=20
            )

            html = resp.text

            soup = self.make_soup(html)

            # ---------------------------------------------
            # normal href
            # ---------------------------------------------

            for a in soup.find_all("a", href=True):

                href = a["href"].strip()

                if not href.startswith("http"):
                    continue

                if any(x in href for x in [
                    "facebook.com",
                    "twitter.com",
                    "snvhost.com"
                ]):
                    continue

                results.append(href)

            # ---------------------------------------------
            # JS links
            # ---------------------------------------------

            js_links = re.findall(
                r'var\s+\w+\s*=\s*["\'](https?://[^"\']+)["\']',
                html,
                re.IGNORECASE
            )

            for link in js_links:
                results.append(link)

            # ---------------------------------------------
            # homelander token append
            # ---------------------------------------------

            for i, link in enumerate(results):

                if (
                    "hub.homelander.buzz" in link
                    and "token=" in link
                ):

                    minute = datetime.now().minute

                    results[i] = f"{link}1{minute}"

        except Exception as e:

            self.log.error(
                f"gamerxyt resolve failed: {e}"
            )

        return list(dict.fromkeys(results))
