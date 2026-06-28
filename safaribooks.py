#!/usr/bin/env python3
# coding: utf-8
import re
import os
import sys
import json
import shutil
import pathlib
import logging
import requests
import traceback
from html import escape
from random import random
from lxml import html, etree
from multiprocessing import Process, Queue, Value
from urllib.parse import urljoin, urlparse

import click


PATH = os.path.dirname(os.path.realpath(__file__))
COOKIES_FILE = os.path.join(PATH, "cookies.json")

ORLY_BASE_HOST = "oreilly.com"  # PLEASE INSERT URL HERE

SAFARI_BASE_HOST = "learning." + ORLY_BASE_HOST
API_ORIGIN_HOST = "api." + ORLY_BASE_HOST

ORLY_BASE_URL = "https://www." + ORLY_BASE_HOST
SAFARI_BASE_URL = "https://" + SAFARI_BASE_HOST
API_ORIGIN_URL = "https://" + API_ORIGIN_HOST
PROFILE_URL = SAFARI_BASE_URL + "/profile/"

SIGN_IN_URL = ORLY_BASE_URL + "/member/sign-in.html"

# DEBUG
USE_PROXY = False
PROXIES = {"https": "https://127.0.0.1:8080"}


class Display:
    BASE_FORMAT = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%d/%b/%Y %H:%M:%S"
    )

    SH_DEFAULT = "\033[0m" if "win" not in sys.platform else ""  # TODO: colors for Windows
    SH_YELLOW = "\033[33m" if "win" not in sys.platform else ""
    SH_BG_RED = "\033[41m" if "win" not in sys.platform else ""
    SH_BG_YELLOW = "\033[43m" if "win" not in sys.platform else ""

    def __init__(self, log_file):
        self.output_dir = ""
        self.output_dir_set = False
        self.log_file = os.path.join(PATH, log_file)

        self.logger = logging.getLogger("SafariBooks")
        self.logger.setLevel(logging.INFO)
        logs_handler = logging.FileHandler(filename=self.log_file)
        logs_handler.setFormatter(self.BASE_FORMAT)
        logs_handler.setLevel(logging.INFO)
        self.logger.addHandler(logs_handler)

        self.columns, _ = shutil.get_terminal_size()

        self.logger.info("** Welcome to SafariBooks! **")

        self.book_ad_info = False
        self.css_ad_info = Value("i", 0)
        self.images_ad_info = Value("i", 0)
        self.last_request = (None,)
        self.in_error = False

        self.state_status = Value("i", 0)
        sys.excepthook = self.unhandled_exception

    def set_output_dir(self, output_dir):
        self.info("Output directory:\n    %s" % output_dir)
        self.output_dir = output_dir
        self.output_dir_set = True

    def unregister(self):
        self.logger.handlers[0].close()
        sys.excepthook = sys.__excepthook__

    def log(self, message):
        try:
            self.logger.info(str(message, "utf-8", "replace"))

        except (UnicodeDecodeError, Exception):
            self.logger.info(message)

    def out(self, put):
        pattern = "\r{!s}\r{!s}\n"
        try:
            s = pattern.format(" " * self.columns, str(put, "utf-8", "replace"))

        except TypeError:
            s = pattern.format(" " * self.columns, put)

        sys.stdout.write(s)

    def info(self, message, state=False):
        self.log(message)
        output = (self.SH_YELLOW + "[*]" + self.SH_DEFAULT if not state else
                  self.SH_BG_YELLOW + "[-]" + self.SH_DEFAULT) + " %s" % message
        self.out(output)

    def error(self, error):
        if not self.in_error:
            self.in_error = True

        self.log(error)
        output = self.SH_BG_RED + "[#]" + self.SH_DEFAULT + " %s" % error
        self.out(output)

    def warning(self, message):
        self.log(message)
        output = self.SH_YELLOW + "[!]" + self.SH_DEFAULT + " %s" % message
        self.out(output)

    def exit(self, error):
        self.error(str(error))

        if self.output_dir_set:
            output = (self.SH_YELLOW + "[+]" + self.SH_DEFAULT +
                      " Please delete the output directory '" + self.output_dir + "'"
                      " and restart the program.")
            self.out(output)

        output = self.SH_BG_RED + "[!]" + self.SH_DEFAULT + " Aborting..."
        self.out(output)

        self.save_last_request()
        sys.exit(1)

    def unhandled_exception(self, _, o, tb):
        self.log("".join(traceback.format_tb(tb)))
        self.exit("Unhandled Exception: %s (type: %s)" % (o, o.__class__.__name__))

    def save_last_request(self):
        if any(self.last_request):
            self.log("Last request done:\n\tURL: {0}\n\tDATA: {1}\n\tOTHERS: {2}\n\n\t{3}\n{4}\n\n{5}\n"
                     .format(*self.last_request))

    def intro(self):
        output = self.SH_YELLOW + (r"""
       ____     ___         _
      / __/__ _/ _/__ _____(_)
     _\ \/ _ `/ _/ _ `/ __/ /
    /___/\_,_/_/ \_,_/_/ /_/
      / _ )___  ___  / /__ ___
     / _  / _ \/ _ \/  '_/(_-<
    /____/\___/\___/_/\_\/___/
""" if random() > 0.5 else r"""
 ██████╗     ██████╗ ██╗  ██╗   ██╗██████╗
██╔═══██╗    ██╔══██╗██║  ╚██╗ ██╔╝╚════██╗
██║   ██║    ██████╔╝██║   ╚████╔╝   ▄███╔╝
██║   ██║    ██╔══██╗██║    ╚██╔╝    ▀▀══╝
╚██████╔╝    ██║  ██║███████╗██║     ██╗
 ╚═════╝     ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝
""") + self.SH_DEFAULT
        output += "\n" + "~" * (self.columns // 2)

        self.out(output)

    def parse_description(self, desc):
        if not desc:
            return "n/d"

        try:
            return html.fromstring(desc).text_content()

        except (html.etree.ParseError, html.etree.ParserError) as e:
            self.log("Error parsing the description: %s" % e)
            return "n/d"

    def book_info(self, info):
        description = self.parse_description(info.get("description", None)).replace("\n", " ")
        for t in [
            ("Title", info.get("title", "")), ("Authors", ", ".join(aut.get("name", "") for aut in info.get("authors", []))),
            ("Identifier", info.get("identifier", "")), ("ISBN", info.get("isbn", "")),
            ("Publishers", ", ".join(pub.get("name", "") for pub in info.get("publishers", []))),
            ("Rights", info.get("rights", "")),
            ("Description", description[:500] + "..." if len(description) >= 500 else description),
            ("Release Date", info.get("issued", "")),
            ("URL", info.get("web_url", ""))
        ]:
            self.info("{0}{1}{2}: {3}".format(self.SH_YELLOW, t[0], self.SH_DEFAULT, t[1]), True)

    def state(self, origin, done):
        progress = int(done * 100 / origin)
        bar = int(progress * (self.columns - 11) / 100)
        if self.state_status.value < progress:
            self.state_status.value = progress
            sys.stdout.write(
                "\r    " + self.SH_BG_YELLOW + "[" + ("#" * bar).ljust(self.columns - 11, "-") + "]" +
                self.SH_DEFAULT + ("%4s" % progress) + "%" + ("\n" if progress == 100 else "")
            )

    def done(self, epub_file):
        self.info("Done: %s\n\n" % epub_file +
                  "    If you like it, please * this project on GitHub to make it known:\n"
                  "        https://github.com/lorenzodifuccia/safaribooks\n"
                  "    e don't forget to renew your Safari Books Online subscription:\n"
                  "        " + SAFARI_BASE_URL + "\n\n" +
                  self.SH_BG_RED + "[!]" + self.SH_DEFAULT + " Bye!!")

    @staticmethod
    def api_error(response):
        message = "API: "
        if "detail" in response and "Not found" in response["detail"]:
            message += "book's not present in Safari Books Online.\n" \
                       "    The book identifier is the digits that you can find in the URL:\n" \
                       "    `" + SAFARI_BASE_URL + "/library/view/book-name/XXXXXXXXXXXXX/`"

        else:
            os.remove(COOKIES_FILE)
            message += "Out-of-Session%s.\n" % (" (%s)" % response["detail"]) if "detail" in response else "" + \
                       Display.SH_YELLOW + "[+]" + Display.SH_DEFAULT + \
                       " Use the `--cred` or `--login` options in order to perform the auth login to Safari."

        return message


class WinQueue(list):  # TODO: error while use `process` in Windows: can't pickle _thread.RLock objects
    def put(self, el):
        self.append(el)

    def qsize(self):
        return self.__len__()


class SafariBooks:
    API_V1_TEMPLATE = SAFARI_BASE_URL + "/api/v1/book/{0}/"
    API_V2_CHAPTERS = SAFARI_BASE_URL + "/api/v2/epub-chapters/"
    API_V2_EPUBS = SAFARI_BASE_URL + "/api/v2/epubs/"

    BASE_01_HTML = "<!DOCTYPE html>\n" \
                   "<html lang=\"en\" xml:lang=\"en\" xmlns=\"http://www.w3.org/1999/xhtml\"" \
                   " xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"" \
                   " xsi:schemaLocation=\"http://www.w3.org/2002/06/xhtml2/" \
                   " http://www.w3.org/MarkUp/SCHEMA/xhtml2.xsd\"" \
                   " xmlns:epub=\"http://www.idpf.org/2007/ops\">\n" \
                   "<head>\n" \
                   "{0}\n" \
                   "<style type=\"text/css\">" \
                   "body{{margin:1em;background-color:transparent!important;}}" \
                   "#sbo-rt-content *{{text-indent:0pt!important;}}#sbo-rt-content .bq{{margin-right:1em!important;}}"

    KINDLE_HTML = "#sbo-rt-content *{{word-wrap:break-word!important;" \
                  "word-break:break-word!important;}}#sbo-rt-content table,#sbo-rt-content pre" \
                  "{{overflow-x:unset!important;overflow:unset!important;" \
                  "overflow-y:unset!important;white-space:pre-wrap!important;}}"

    BASE_02_HTML = "</style>" \
                   "</head>\n" \
                   "<body>{1}</body>\n</html>"

    CONTAINER_XML = "<?xml version=\"1.0\"?>" \
                    "<container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">" \
                    "<rootfiles>" \
                    "<rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\" />" \
                    "</rootfiles>" \
                    "</container>"

    # Format: ID, Title, Authors, Description, Subjects, Publisher, Rights, Date, CoverId, MANIFEST, SPINE, CoverUrl
    CONTENT_OPF = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" \
                  "<package xmlns=\"http://www.idpf.org/2007/opf\" unique-identifier=\"bookid\" version=\"2.0\" >\n" \
                  "<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\" " \
                  " xmlns:opf=\"http://www.idpf.org/2007/opf\">\n" \
                  "<dc:title>{1}</dc:title>\n" \
                  "{2}\n" \
                  "<dc:description>{3}</dc:description>\n" \
                  "{4}" \
                  "<dc:publisher>{5}</dc:publisher>\n" \
                  "<dc:rights>{6}</dc:rights>\n" \
                  "<dc:language>en-US</dc:language>\n" \
                  "<dc:date>{7}</dc:date>\n" \
                  "<dc:identifier id=\"bookid\">{0}</dc:identifier>\n" \
                  "<meta name=\"cover\" content=\"{8}\"/>\n" \
                  "</metadata>\n" \
                  "<manifest>\n" \
                  "<item id=\"ncx\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\" />\n" \
                  "{9}\n" \
                  "</manifest>\n" \
                  "<spine toc=\"ncx\">\n{10}</spine>\n" \
                  "<guide><reference href=\"{11}\" title=\"Cover\" type=\"cover\" /></guide>\n" \
                  "</package>"

    # Format: ID, Depth, Title, Author, NAVMAP
    TOC_NCX = "<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"no\" ?>\n" \
              "<!DOCTYPE ncx PUBLIC \"-//NISO//DTD ncx 2005-1//EN\"" \
              " \"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd\">\n" \
              "<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\">\n" \
              "<head>\n" \
              "<meta content=\"ID:ISBN:{0}\" name=\"dtb:uid\"/>\n" \
              "<meta content=\"{1}\" name=\"dtb:depth\"/>\n" \
              "<meta content=\"0\" name=\"dtb:totalPageCount\"/>\n" \
              "<meta content=\"0\" name=\"dtb:maxPageNumber\"/>\n" \
              "</head>\n" \
              "<docTitle><text>{2}</text></docTitle>\n" \
              "<docAuthor><text>{3}</text></docAuthor>\n" \
              "<navMap>{4}</navMap>\n" \
              "</ncx>"

    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://learning.oreilly.com/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/125.0.0.0 Safari/537.36"
    }

    COOKIE_FLOAT_MAX_AGE_PATTERN = re.compile(r'(max-age=\d*\.\d*)', re.IGNORECASE)

    @staticmethod
    def _apply_stealth(page):
        """Apply stealth patches to a Playwright page to avoid bot detection."""
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete window.__playwright;
            delete window.__pw_manual;
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        """)

    def _set_session_cookies(self, cookies):
        """Set session cookies with proper domain scoping.
        
        When cookies are saved to/loaded from cookies.json as a simple
        name→value dict, they lose their domain attribute. Without domain
        info, requests.Session won't send them to the right servers.
        This method ensures all cookies are scoped to .oreilly.com."""
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain='.oreilly.com')
        # Also set auth-related cookies for subdomains they come from
        AUTH_COOKIES_SUBDOMAINS = {
            'auth0': 'sso.oreilly.com',
            'auth0_compat': 'sso.oreilly.com',
            'did': 'sso.oreilly.com',
            'did_compat': 'sso.oreilly.com',
        }
        for name, domain in AUTH_COOKIES_SUBDOMAINS.items():
            if name in cookies:
                self.session.cookies.set(name, cookies[name], domain=domain)

    @staticmethod
    def _try_cookie_extraction():
        """Try to extract O'Reilly cookies directly from the user's browser
        using browser_cookie3. This bypasses Akamai entirely since we read
        cookies from the actual browser profile (no HTTP request made).

        We collect cookies from all browsers but prioritize ones that have
        auth tokens (orm-jwt, auth0, csrftoken) since without these the
        API returns only preview snippets instead of full chapter content."""
        try:
            import browser_cookie3
        except ImportError:
            return None

        AUTH_COOKIES = {'orm-jwt', 'auth0', 'auth0_compat', 'csrftoken',
                         'groot_sessionid', 'orm-rt'}

        # Collect cookies per browser, track which ones have auth tokens
        browser_cookies = []  # list of (has_auth, cookies_dict)
        for browser_fn in [browser_cookie3.brave, browser_cookie3.chrome,
                           browser_cookie3.chromium, browser_cookie3.firefox]:
            try:
                cj = browser_fn(domain_name='.oreilly.com')
                browser_dict = {}
                for c in cj:
                    if 'oreilly' in getattr(c, 'domain', ''):
                        browser_dict[c.name] = c.value
                has_auth = bool(AUTH_COOKIES & set(browser_dict.keys()))
                if browser_dict:
                    browser_cookies.append((has_auth, browser_dict))
            except Exception:
                continue

        if not browser_cookies:
            return None

        # Merge cookies, preferring browsers with auth tokens
        # If any browser has auth cookies, use those cookies as base
        browser_cookies.sort(key=lambda x: x[0], reverse=True)
        merged = {}
        for has_auth, cookies_dict in browser_cookies:
            for name, value in cookies_dict.items():
                if name not in merged or (has_auth and not browser_cookies[0][0] and name in AUTH_COOKIES):
                    merged[name] = value

        return merged if merged else None

    @staticmethod
    def browser_login(email=None, password=None):
        """Authenticate with O'Reilly and return session cookies.

        Strategies (in order):
        1. Extract cookies from the user's browser via browser_cookie3
           (no browser window needed, bypasses Akamai entirely)
        2. Connect to user's running Chrome via CDP and navigate to login
           (uses the user's real browser that Akamai trusts)
        3. Launch Playwright browser with stealth patches
           (may be blocked by Akamai but worth trying)
        """
        # Strategy 1: Extract cookies directly from browser (best method)
        cookies = SafariBooks._try_cookie_extraction()
        if cookies:
            session_cookies = any(
                k for k in cookies
                if k in ("session", "_js_session_id", "lrj3", "OReilly-Session-Id")
            )
            if session_cookies or len(cookies) >= 3:
                print("Found O'Reilly cookies in your browser. Using them directly.")
                return cookies
            else:
                print("Found some O'Reilly cookies, but session may be expired.")
                print("Opening browser for re-authentication...\n")

        # Strategy 2 & 3: Browser-based login via Playwright
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is required for browser-based login. "
                "Install with: uv sync --extra login && uv run playwright install chromium\n"
                "Alternatively, log into https://learning.oreilly.com in your browser,\n"
                "then run: python retrieve_cookies.py"
            )

        with sync_playwright() as p:
            browser = None
            cdp_connection = False

            # Strategy 2: Connect to user's running Chrome via CDP
            try:
                browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                cdp_connection = True
                print("Connected to your existing Chrome browser.")
            except Exception:
                pass

            # Strategy 3: Launch Playwright with stealth patches
            if browser is None:
                # Try system Chrome first (more trusted by Akamai)
                try:
                    browser = p.chromium.launch(
                        headless=False,
                        channel="chromium",
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-first-run",
                            "--no-default-browser-check",
                        ],
                    )
                except Exception:
                    try:
                        browser = p.chromium.launch(
                            headless=False,
                            args=[
                                "--disable-blink-features=AutomationControlled",
                            ],
                        )
                    except Exception as launch_err:
                        raise RuntimeError(
                            "Could not launch browser. Try one of these:\n"
                            "  1. Log into https://learning.oreilly.com in your browser,\n"
                            "     then run: python retrieve_cookies.py\n"
                            "  2. Run Chrome with remote debugging:\n"
                            "     google-chrome-stable --remote-debugging-port=9222\n"
                            "     Then rerun this script.\n"
                            "  Error: " + str(launch_err)
                        )

            if cdp_connection:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
            else:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()
                SafariBooks._apply_stealth(page)

            # Navigate to sign-in page
            page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=30000)

            # Check if we got blocked by Akamai
            page_title = page.title()
            if "Access Denied" in page_title or "Access Denied" in page.content()[:2000]:
                if not cdp_connection:
                    browser.close()
                raise RuntimeError(
                    "O'Reilly blocked the automated browser (Akamai bot protection).\n"
                    "Please try one of these alternatives:\n"
                    "  1. Log into https://learning.oreilly.com in your real browser,\n"
                    "     then run: python retrieve_cookies.py\n"
                    "  2. Run Chrome with: google-chrome-stable --remote-debugging-port=9222\n"
                    "     Then rerun this script."
                )

            auto_filled = False
            if email and password:
                try:
                    email_input = page.locator('input[name="email"], input[type="email"]').first
                    email_input.wait_for(state="visible", timeout=10000)
                    email_input.fill(email)

                    password_input = page.locator('input[type="password"]').first
                    password_input.wait_for(state="visible", timeout=10000)
                    password_input.fill(password)

                    sign_in_btn = page.locator('button[type="submit"], input[type="submit"]').first
                    sign_in_btn.click()
                    auto_filled = True
                except Exception:
                    print("\n" + "=" * 60)
                    print("Could not auto-fill login form.")
                    print("Please complete the login manually in the browser.")
                    print("=" * 60 + "\n")

            if auto_filled:
                print("\n" + "=" * 60)
                print("Credentials submitted. If 2FA/CAPTCHA is required,")
                print("please complete it in the browser window.")
                print("=" * 60 + "\n")
            else:
                print("\n" + "=" * 60)
                print("Please log in to O'Reilly in the browser window.")
                print("Once logged in and on the dashboard, the script")
                print("will continue automatically.")
                print("=" * 60 + "\n")

            # Wait until the user lands on learning.oreilly.com
            try:
                page.wait_for_url(re.compile(r'https://learning\.oreilly\.com/.*'), timeout=120000)
            except Exception:
                if "learning.oreilly.com" not in page.url:
                    if not cdp_connection:
                        browser.close()
                    raise RuntimeError(
                        "Login timed out. Please try again and make sure to "
                        "complete the login in the browser window."
                    )

            # Extract cookies from the browser context
            raw_cookies = context.cookies()
            cookies = {c["name"]: c["value"] for c in raw_cookies
                       if "oreilly" in c.get("domain", "")}

            if not cdp_connection:
                browser.close()

        return cookies
    def __init__(self, display=None):
        """Initialize with a session and optional display. Does NOT perform auth."""
        self.session = requests.Session()
        if USE_PROXY:  # DEBUG
            self.session.proxies = PROXIES
            self.session.verify = False

        self.session.headers.update(self.HEADERS)
        self.jwt = {}
        self.display = display

    def authenticate(self, cred=None, no_cookies=False):
        """Perform authentication using cookies, browser cookies, --cred, or --login.
        
        Args:
            cred: None (use cookies/browser), [email, password] (--cred), or [None, None] (--login)
            no_cookies: If True, don't save cookies to file
        """
        if not cred:
            # Try browser cookie extraction first (no login needed)
            if not os.path.isfile(COOKIES_FILE):
                self.display.info("Trying to extract cookies from your browser...")
                cookies = self._try_cookie_extraction()
                if cookies and len(cookies) >= 3:
                    self.display.info("Found O'Reilly cookies in browser. Using them.", state=True)
                    self._set_session_cookies(cookies)
                    if not no_cookies:
                        json.dump(cookies, open(COOKIES_FILE, 'w'))
                    self.display.info("Cookies loaded", state=True)
                else:
                    self.display.exit(
                        "Login: unable to find `cookies.json` file and no browser cookies found.\n"
                        "    Options:\n"
                        "    1. Log into https://learning.oreilly.com in your browser, then rerun this script\n"
                        "    2. Use `--cred` or `--login` for browser-based authentication\n"
                        "    3. Run `python retrieve_cookies.py` to extract cookies from your browser"
                    )
            else:
                saved_cookies = json.load(open(COOKIES_FILE))
                self._set_session_cookies(saved_cookies)

        else:
            # cred is either [email, password] from --cred or [None, None] from --login
            email, password = cred
            self.display.info("Logging into Safari Books Online...", state=True)
            self.do_login(email, password, no_cookies=no_cookies)
            # Cookies are saved inside do_login

        self.check_login()

    def download(self, book_id, kindle=False, preserve_log=False):
        """Download a book by ID and create an EPUB."""
        self.book_id = book_id
        self.display = Display("info_%s.log" % escape(book_id))
        self.display.intro()

        self.api_url = self.API_V1_TEMPLATE.format(self.book_id)
        self.urn = "urn:orm:book:{}".format(self.book_id)
        self.book_slug = None  # will be set by get_book_info

        self.display.info("Retrieving book info...")
        self.book_info = self.get_book_info()
        self.display.book_info(self.book_info)

        self.display.info("Retrieving book chapters...")
        self.book_chapters = self.get_book_chapters()

        self.chapters_queue = self.book_chapters[:]

        if len(self.book_chapters) > sys.getrecursionlimit():
            sys.setrecursionlimit(len(self.book_chapters))

        self.book_title = self.book_info["title"]
        self.base_url = self.book_info["web_url"]

        self.clean_book_title = "".join(self.escape_dirname(self.book_title).split(",")[:2]) \
                                + " ({0})".format(self.book_id)

        books_dir = os.path.join(PATH, "Books")
        if not os.path.isdir(books_dir):
            os.mkdir(books_dir)

        self.BOOK_PATH = os.path.join(books_dir, self.clean_book_title)
        self.display.set_output_dir(self.BOOK_PATH)
        self.css_path = ""
        self.images_path = ""
        self.create_dirs()

        self.chapter_title = ""
        self.filename = ""
        self.chapter_stylesheets = []
        self.css = []
        self.images = []

        self.display.info("Downloading book contents... (%s chapters)" % len(self.book_chapters), state=True)
        self.BASE_HTML = self.BASE_01_HTML + (self.KINDLE_HTML if not kindle else "") + self.BASE_02_HTML

        self.cover = False
        self.get()
        if not self.cover:
            self.cover = self.get_default_cover() if "cover" in self.book_info else False
            cover_html = self.parse_html(
                html.fromstring("<div id=\"sbo-rt-content\"><img src=\"Images/{0}\"></div>".format(self.cover)), True
            )

            self.book_chapters = [{
                "filename": "default_cover.xhtml",
                "title": "Cover"
            }] + self.book_chapters

            self.filename = self.book_chapters[0]["filename"]
            self.save_page_html(cover_html)

        self.css_done_queue = Queue(0) if "win" not in sys.platform else WinQueue()
        self.display.info("Downloading book CSSs... (%s files)" % len(self.css), state=True)
        self.collect_css()
        self.images_done_queue = Queue(0) if "win" not in sys.platform else WinQueue()
        self.display.info("Downloading book images... (%s files)" % len(self.images), state=True)
        self.collect_images()

        self.display.info("Creating EPUB file...", state=True)
        self.create_epub()

        if not self.display.in_error and not preserve_log:
            os.remove(self.display.log_file)

        self.display.done(os.path.join(self.BOOK_PATH, self.book_id + ".epub"))
        self.display.unregister()

    def search(self, query, page=1, limit=10):
        """Search for books on O'Reilly. Returns (results_list, total_count, has_next_page).

        The `page` argument is 1-indexed from the caller's perspective (the
        first page is page 1). The O'Reilly /api/v2/search/ endpoint is
        0-indexed (the first page is page 0), so we translate here.
        """
        api_page = max(0, page - 1)
        response = self.requests_provider(
            SAFARI_BASE_URL + "/api/v2/search/",
            params={"query": query, "page": api_page, "limit": limit, "formats": "book"}
        )
        if response == 0:
            self.display.exit("Search: unable to reach the search API.")
            return [], 0, False

        if response.status_code != 200:
            self.display.exit("Search: API returned status %d: %s" % (response.status_code, response.text[:200]))
            return [], 0, False

        data = response.json()
        results = data.get("results", [])
        total = data.get("total", 0)
        next_page = data.get("next") is not None

        return results, total, next_page

    @staticmethod
    def format_search_result(idx, result):
        """Format a single search result for display."""
        title = result.get("title", "Unknown")
        authors = ", ".join(result.get("authors", [])) or "Unknown"
        book_id = result.get("archive_id", "?")
        year = result.get("issued", "")[:4] if result.get("issued") else "n/a"
        pages = result.get("virtual_pages", "?")
        publisher = ", ".join(result.get("publishers", [])) or "Unknown"

        line1 = "[%d] %s" % (idx, title)
        line2 = "    by %s | ISBN: %s | %s | %s pages" % (authors, book_id, year, pages)

        return line1, line2

    def handle_cookie_update(self, set_cookie_headers):
        for morsel in set_cookie_headers:
            # Handle Float 'max-age' Cookie
            if self.COOKIE_FLOAT_MAX_AGE_PATTERN.search(morsel):
                cookie_key, cookie_value = morsel.split(";")[0].split("=")
                self.session.cookies.set(cookie_key, cookie_value)

    def requests_provider(self, url, is_post=False, data=None, perform_redirect=True, params=None, **kwargs):
        try:
            response = getattr(self.session, "post" if is_post else "get")(
                url,
                data=data,
                allow_redirects=False,
                params=params,
                **kwargs
            )

            self.handle_cookie_update(response.raw.headers.getlist("Set-Cookie"))

            self.display.last_request = (
                url, data, kwargs, response.status_code, "\n".join(
                    ["\t{}: {}".format(*h) for h in response.headers.items()]
                ), response.text
            )

        except (requests.ConnectionError, requests.ConnectTimeout, requests.RequestException) as request_exception:
            self.display.error(str(request_exception))
            return 0

        if response.is_redirect and perform_redirect:
            return self.requests_provider(response.next.url, is_post, None, perform_redirect)
            # TODO How about **kwargs?

        return response

    @staticmethod
    def parse_cred(cred):
        if ":" not in cred:
            return False

        sep = cred.index(":")
        new_cred = ["", ""]
        new_cred[0] = cred[:sep].strip("'").strip('"')
        if "@" not in new_cred[0]:
            return False

        new_cred[1] = cred[sep + 1:]
        return new_cred

    def do_login(self, email=None, password=None, no_cookies=False):
        """Log into O'Reilly using browser automation (Playwright).
        Akamai bot protection blocks direct HTTP login, so we use
        a real browser to authenticate and capture session cookies."""
        self.display.info("Opening browser for O'Reilly login...")

        try:
            cookies = self.browser_login(email, password)
        except ImportError:
            self.display.exit(
                "Login: Playwright is required for browser-based login.\n"
                "    Install it with: uv sync --extra login && uv run playwright install chromium"
            )
        except Exception as e:
            self.display.exit(
                "Login: browser login failed.\n"
                "    " + str(e)
            )
            return  # unreachable, but satisfies linters

        if not cookies:
            self.display.exit(
                "Login: no cookies received from browser login.\n"
                "    Make sure you are logged in and try again."
            )

        # Apply cookies to the requests session
        self.session.cookies.update(cookies)

        if not no_cookies:
            json.dump(self.session.cookies.get_dict(), open(COOKIES_FILE, 'w'))

        self.display.info("Browser login complete, cookies captured.", state=True)

    def check_login(self):
        response = self.requests_provider(PROFILE_URL, perform_redirect=False)

        if response == 0:
            self.display.exit("Login: unable to reach Safari Books Online. Try again...")

        elif response.status_code == 302:
            # 302 redirect from profile means cookies may be expired;
            # try to proceed anyway since the book API might still work
            self.display.info("Session may be expired, trying anyway...")

        elif response.status_code != 200:
            self.display.exit("Authentication issue: unable to access profile page.")

        elif "user_type\":\"Expired\"" in response.text:
            self.display.exit("Authentication issue: account subscription expired.")

        else:
            self.display.info("Successfully authenticated.", state=True)

    def get_book_info(self):
        # Try v1 API first (may still work for some books)
        response = self.requests_provider(self.api_url)
        if response != 0 and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and len(data.keys()) > 1:
                    if "last_chapter_read" in data:
                        del data["last_chapter_read"]
                    for key, value in data.items():
                        if value is None:
                            data[key] = 'n/a'
                    self.book_slug = data.get("web_url", "").split("/library/view/")[-1].split("/")[0] if "/library/view/" in data.get("web_url", "") else None
                    return data
            except (ValueError, KeyError):
                pass

        # Fallback: scrape book info from the library HTML page + v2 API
        self.display.info("Using v2 API for book info...")

        # Try v2 epub API first (more reliable than HTML scraping)
        v2_epub_info = {}
        try:
            v2_resp = self.requests_provider(
                self.API_V2_EPUBS + self.urn + "/",
            )
            if v2_resp != 0 and v2_resp.status_code == 200:
                v2_data = v2_resp.json()
                if isinstance(v2_data, dict) and v2_data.get('title'):
                    v2_epub_info = {
                        "title": v2_data.get("title", "Unknown"),
                        "identifier": self.book_id,
                        "isbn": v2_data.get("isbn", self.book_id),
                        "issued": v2_data.get("publication_date", ""),
                        "cover": "",
                        "description": "",
                    }
                    # Extract text description
                    descs = v2_data.get("descriptions", {})
                    desc = descs.get("text/plain", descs.get("text/html", ""))
                    if desc:
                        # Strip HTML from description
                        desc_text = re.sub(r'<[^>]+>', '', desc).strip()
                        v2_epub_info["description"] = desc_text
                    self.book_slug = None
                    # Try to extract slug from v2 data URLs
                    v2_url = v2_data.get("url", "")
                    if "/library/view/" in v2_url:
                        self.book_slug = v2_url.split("/library/view/")[-1].split("/")[0]
        except Exception:
            pass

        # Fetch the book page for additional metadata
        book_page_url = ORLY_BASE_URL + "/library/view/-/" + self.book_id + "/"
        try:
            # Use specific headers for the book page (override session headers)
            book_page_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": SAFARI_BASE_URL + "/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            }
            resp = self.session.get(book_page_url, allow_redirects=True, timeout=30,
                                    headers=book_page_headers)
            self.handle_cookie_update(resp.raw.headers.getlist("Set-Cookie"))
        except requests.RequestException as e:
            self.display.exit("API: unable to retrieve book info - network error: %s" % str(e))

        if resp.status_code != 200:
            self.display.exit("API: unable to retrieve book info (v1 and v2 both failed).")

        # Extract slug from the final URL
        slug_match = re.search(r'/library/view/([^/]+)/' + self.book_id, resp.url)
        if slug_match:
            self.book_slug = slug_match.group(1)

        # Parse JSON-LD metadata from the HTML page
        json_ld_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            resp.text, re.DOTALL
        )
        book_meta = {}
        if json_ld_match:
            try:
                ld = json.loads(json_ld_match.group(1))
                book_meta["title"] = ld.get("name", "Unknown")
                book_meta["description"] = ld.get("description", "")
                book_meta["isbn"] = self.book_id
                book_meta["identifier"] = self.book_id
                image = ld.get("image", {})
                if isinstance(image, dict):
                    book_meta["cover"] = image.get("url", "")
                elif isinstance(image, str):
                    book_meta["cover"] = image
                book_meta["issued"] = ld.get("datePublished", "")
            except (json.JSONDecodeError, KeyError):
                pass

        if not book_meta.get("title"):
            # Use v2 API data if available (more reliable than HTML scraping)
            if v2_epub_info:
                book_meta.update(v2_epub_info)
            else:
                # Fallback: extract title from HTML title tag
                title_match = re.search(r'<title>([^<]+)</title>', resp.text)
                if title_match:
                    book_meta["title"] = title_match.group(1).split(" [")[0].strip()
                else:
                    book_meta["title"] = "Unknown"

        # Fill in fields from v2 API if HTML scraping didn't find them
        if v2_epub_info:
            for key in ["description", "isbn", "identifier", "issued"]:
                if not book_meta.get(key) and v2_epub_info.get(key):
                    book_meta[key] = v2_epub_info[key]

        # Extract publisher from HTML
        pub_match = re.search(r'"publisher":\s*\{[^}]*"name":\s*"([^"]+)"', resp.text)
        if pub_match:
            book_meta["publishers"] = [{"name": pub_match.group(1)}]
        else:
            book_meta["publishers"] = [{"name": "Unknown"}]

        # Extract rights/copyright
        rights_match = re.search(r'©\s*\d{4}[^<]*', resp.text)
        if rights_match:
            book_meta["rights"] = rights_match.group(0).strip()
        else:
            book_meta["rights"] = ""

        # Get authors from v1 talent API
        authors = []
        try:
            talent_resp = self.requests_provider(
                SAFARI_BASE_URL + "/api/v1/talent/work/" + self.urn
            )
            if talent_resp != 0 and talent_resp.status_code == 200:
                talent_data = talent_resp.json()
                for a in talent_data:
                    name = " ".join(filter(None, [
                        a.get("firstname", ""),
                        a.get("middlename", ""),
                        a.get("surname", "")
                    ]))
                    if a.get("contribution_type") == "AU" or not a.get("contribution_type"):
                        authors.append({"name": name})
        except Exception:
            pass
        book_meta["authors"] = authors if authors else [{"name": "Unknown"}]

        # Extract subjects/tags from HTML
        subjects = []
        subject_matches = re.findall(r'"keywords":\s*"([^"]+)"', resp.text)
        if not subject_matches:
            subject_matches = re.findall(r'<meta name="keywords" content="([^"]+)"', resp.text)
        if subject_matches:
            for kw in subject_matches[0].split(","):
                kw = kw.strip()
                if kw:
                    subjects.append({"name": kw})
        book_meta["subjects"] = subjects

        # Set web_url and cover
        book_meta["web_url"] = resp.url
        if "cover" not in book_meta or not book_meta["cover"]:
            book_meta["cover"] = SAFARI_BASE_URL + "/library/cover/" + self.book_id + "/250w/"

        # Set missing fields
        book_meta.setdefault("isbn", self.book_id)
        book_meta.setdefault("identifier", self.book_id)

        return book_meta

    def get_book_chapters(self, page=1):
        # Try v1 API first
        response = self.requests_provider(urljoin(self.api_url, "chapter/?page=%s" % page))
        if response != 0 and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and "results" in data and len(data["results"]) > 0:
                    # v1 API works - use existing logic
                    if data["count"] > sys.getrecursionlimit():
                        sys.setrecursionlimit(data["count"])
                    result = []
                    result.extend([c for c in data["results"] if "cover" in c["filename"] or "cover" in c["title"]])
                    for c in result:
                        del data["results"][data["results"].index(c)]
                    result += data["results"]
                    return result + (self.get_book_chapters(page + 1) if data.get("next") else [])
            except (ValueError, KeyError):
                pass

        # Fallback: use v2 API
        self.display.info("Using v2 API for book chapters...")
        chapters = []
        offset = 0
        limit = 100
        while True:
            url = "{}?epub_identifier={}&limit={}&offset={}".format(
                self.API_V2_CHAPTERS, self.urn, limit, offset
            )
            resp = self.requests_provider(url)
            if resp == 0:
                self.display.exit("API v2: unable to retrieve book chapters.")

            try:
                data = resp.json()
            except ValueError:
                self.display.exit("API v2: unable to parse book chapters response.")

            if not isinstance(data, dict) or "results" not in data:
                self.display.exit(self.display.api_error(data))

            results = data.get("results", [])
            if not results:
                break

            for ch in results:
                # Convert v2 format to v1-compatible format
                filename = ch["reference_id"].split("-", 1)[1].lstrip("/") if "-" in ch["reference_id"] else ch["reference_id"]
                ourn = ch["ourn"]
                
                chapter_data = {
                    "filename": filename,
                    "title": ch["title"],
                    "content": ch["content_url"],  # v2: full URL to content
                    "asset_base_url": self.API_V2_EPUBS + self.urn + "/files",
                    "images": [],  # will be populated per-chapter in get()
                    "stylesheets": [],  # will be populated per-chapter
                    # v2 extras
                    "ourn": ourn,
                    "is_v2": True,
                    "related_assets": ch.get("related_assets", {}),
                }
                chapters.append(chapter_data)

            total = data.get("count", len(chapters))
            # Check if there are more pages
            if len(chapters) >= total:
                break
            offset += limit

            if offset > total + limit:
                # Safety break to avoid infinite loops
                break

        # Move cover chapters to the front
        cover_chapters = [c for c in chapters if "cover" in c["filename"].lower() or "cover" in c["title"].lower()]
        non_cover = [c for c in chapters if c not in cover_chapters]
        return cover_chapters + non_cover

    def get_default_cover(self):
        cover_url = self.book_info.get("cover", "")
        if not cover_url:
            self.display.error("No cover URL found in book info.")
            return False

        # v2 cover URLs are full paths like /library/cover/{id}/250w/
        if not cover_url.startswith("http"):
            cover_url = SAFARI_BASE_URL + cover_url if cover_url.startswith("/") else SAFARI_BASE_URL + "/" + cover_url

        response = self.requests_provider(cover_url, stream=True)
        if response == 0 or response.status_code != 200:
            self.display.error("Error trying to retrieve the cover: %s" % cover_url)
            return False

        file_ext = response.headers.get("Content-Type", "image/jpeg").split("/")[-1]
        # Handle odd content types like "image/jpeg" -> "jpg"
        if file_ext == "jpeg":
            file_ext = "jpg"
        with open(os.path.join(self.images_path, "default_cover." + file_ext), 'wb') as i:
            for chunk in response.iter_content(1024):
                i.write(chunk)

        return "default_cover." + file_ext

    def get_html(self, url):
        response = self.requests_provider(url)
        if response == 0 or response.status_code != 200:
            self.display.exit(
                "Crawler: error trying to retrieve this page: %s (%s)\n    From: %s" %
                (self.filename, self.chapter_title, url)
            )

        root = None
        try:
            root = html.fromstring(response.text, base_url=SAFARI_BASE_URL)

        except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
            self.display.error(parsing_error)
            self.display.exit(
                "Crawler: error trying to parse this page: %s (%s)\n    From: %s" %
                (self.filename, self.chapter_title, url)
            )

        # Check if the content appears truncated. With proper auth cookies
        # (orm-jwt), the API returns full chapter content. Without auth,
        # only a 3-paragraph preview is served.
        book_content = root.xpath("//div[@id='sbo-rt-content']")
        if len(book_content) == 1:
            content_text = book_content[0].text_content().strip()
            if len(content_text) < 500:
                self.display.warning(
                    "Chapter content appears truncated (only %d chars). "
                    "This usually means your O'Reilly session cookies are missing or expired. "
                    "Try logging into O'Reilly in your browser and run again."
                    % len(content_text)
                )

        return root

    @staticmethod
    def url_is_absolute(url):
        return bool(urlparse(url).netloc)

    @staticmethod
    def is_image_link(url: str):
        return pathlib.Path(url).suffix[1:].lower() in ["jpg", "jpeg", "png", "gif"]

    def link_replace(self, link):
        if link and not link.startswith("mailto"):
            if not self.url_is_absolute(link):
                if any(x in link for x in ["cover", "images", "graphics"]) or \
                        self.is_image_link(link):
                    image = link.split("/")[-1]
                    return "Images/" + image

                return link.replace(".html", ".xhtml")

            else:
                if self.book_id in link:
                    return self.link_replace(link.split(self.book_id)[-1])

        return link

    @staticmethod
    def get_cover(html_root):
        lowercase_ns = etree.FunctionNamespace(None)
        lowercase_ns["lower-case"] = lambda _, n: n[0].lower() if n and len(n) else ""

        images = html_root.xpath("//img[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover') or"
                                 "contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover') or"
                                 "contains(lower-case(@alt), 'cover')]")
        if len(images):
            return images[0]

        divs = html_root.xpath("//div[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover') or"
                               "contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover')]//img")
        if len(divs):
            return divs[0]

        a = html_root.xpath("//a[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover') or"
                            "contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover')]//img")
        if len(a):
            return a[0]

        return None

    def parse_html(self, root, first_page=False):
        if random() > 0.8:
            if len(root.xpath("//div[@class='controls']/a/text()")):
                self.display.exit(self.display.api_error(" "))

        book_content = root.xpath("//div[@id='sbo-rt-content']")
        if not len(book_content):
            self.display.exit(
                "Parser: book content's corrupted or not present: %s (%s)" %
                (self.filename, self.chapter_title)
            )

        page_css = ""
        if len(self.chapter_stylesheets):
            for chapter_css_url in self.chapter_stylesheets:
                if chapter_css_url not in self.css:
                    self.css.append(chapter_css_url)
                    self.display.log("Crawler: found a new CSS at %s" % chapter_css_url)

                page_css += "<link href=\"Styles/Style{0:0>2}.css\" " \
                            "rel=\"stylesheet\" type=\"text/css\" />\n".format(self.css.index(chapter_css_url))

        stylesheet_links = root.xpath("//link[@rel='stylesheet']")
        if len(stylesheet_links):
            for s in stylesheet_links:
                css_url = urljoin("https:", s.attrib["href"]) if s.attrib["href"][:2] == "//" \
                    else urljoin(self.base_url, s.attrib["href"])

                if css_url not in self.css:
                    self.css.append(css_url)
                    self.display.log("Crawler: found a new CSS at %s" % css_url)

                page_css += "<link href=\"Styles/Style{0:0>2}.css\" " \
                            "rel=\"stylesheet\" type=\"text/css\" />\n".format(self.css.index(css_url))

        stylesheets = root.xpath("//style")
        if len(stylesheets):
            for css in stylesheets:
                if "data-template" in css.attrib and len(css.attrib["data-template"]):
                    css.text = css.attrib["data-template"]
                    del css.attrib["data-template"]

                try:
                    page_css += html.tostring(css, method="xml", encoding='unicode') + "\n"

                except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
                    self.display.error(parsing_error)
                    self.display.exit(
                        "Parser: error trying to parse one CSS found in this page: %s (%s)" %
                        (self.filename, self.chapter_title)
                    )

        # TODO: add all not covered tag for `link_replace` function
        svg_image_tags = root.xpath("//image")
        if len(svg_image_tags):
            for img in svg_image_tags:
                image_attr_href = [x for x in img.attrib.keys() if "href" in x]
                if len(image_attr_href):
                    svg_url = img.attrib.get(image_attr_href[0])
                    svg_root = img.getparent().getparent()
                    new_img = svg_root.makeelement("img")
                    new_img.attrib.update({"src": svg_url})
                    svg_root.remove(img.getparent())
                    svg_root.append(new_img)

        book_content = book_content[0]
        book_content.rewrite_links(self.link_replace)

        xhtml = None
        try:
            if first_page:
                is_cover = self.get_cover(book_content)
                if is_cover is not None:
                    page_css = "<style>" \
                               "body{display:table;position:absolute;margin:0!important;height:100%;width:100%;}" \
                               "#Cover{display:table-cell;vertical-align:middle;text-align:center;}" \
                               "img{height:90vh;margin-left:auto;margin-right:auto;}" \
                               "</style>"
                    cover_html = html.fromstring("<div id=\"Cover\"></div>")
                    cover_div = cover_html.xpath("//div")[0]
                    cover_img = cover_div.makeelement("img")
                    cover_img.attrib.update({"src": is_cover.attrib["src"]})
                    cover_div.append(cover_img)
                    book_content = cover_html

                    self.cover = is_cover.attrib["src"]

            xhtml = html.tostring(book_content, method="xml", encoding='unicode')

        except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
            self.display.error(parsing_error)
            self.display.exit(
                "Parser: error trying to parse HTML of this page: %s (%s)" %
                (self.filename, self.chapter_title)
            )

        return page_css, xhtml

    @staticmethod
    def escape_dirname(dirname, clean_space=False):
        if ":" in dirname:
            if dirname.index(":") > 15:
                dirname = dirname.split(":")[0]

            elif "win" in sys.platform:
                dirname = dirname.replace(":", ",")

        for ch in ['~', '#', '%', '&', '*', '{', '}', '\\', '<', '>', '?', '/', '`', '\'', '"', '|', '+', ':']:
            if ch in dirname:
                dirname = dirname.replace(ch, "_")

        return dirname if not clean_space else dirname.replace(" ", "")

    def create_dirs(self):
        if os.path.isdir(self.BOOK_PATH):
            self.display.log("Book directory already exists: %s" % self.BOOK_PATH)

        else:
            os.makedirs(self.BOOK_PATH)

        oebps = os.path.join(self.BOOK_PATH, "OEBPS")
        if not os.path.isdir(oebps):
            self.display.book_ad_info = True
            os.makedirs(oebps)

        self.css_path = os.path.join(oebps, "Styles")
        if os.path.isdir(self.css_path):
            self.display.log("CSSs directory already exists: %s" % self.css_path)

        else:
            os.makedirs(self.css_path)
            self.display.css_ad_info.value = 1

        self.images_path = os.path.join(oebps, "Images")
        if os.path.isdir(self.images_path):
            self.display.log("Images directory already exists: %s" % self.images_path)

        else:
            os.makedirs(self.images_path)
            self.display.images_ad_info.value = 1

    def save_page_html(self, contents):
        self.filename = self.filename.replace(".html", ".xhtml")
        open(os.path.join(self.BOOK_PATH, "OEBPS", self.filename), "wb") \
            .write(self.BASE_HTML.format(contents[0], contents[1]).encode("utf-8", 'xmlcharrefreplace'))
        self.display.log("Created: %s" % self.filename)

    def get(self):
        len_books = len(self.book_chapters)

        for _ in range(len_books):
            if not len(self.chapters_queue):
                return

            first_page = len_books == len(self.chapters_queue)

            next_chapter = self.chapters_queue.pop(0)
            self.chapter_title = next_chapter["title"]
            self.filename = next_chapter["filename"]

            is_v2 = next_chapter.get("is_v2", False)

            if is_v2:
                # v2 API: content_url is a full URL, asset_base_url is the epub files prefix
                asset_base_url = self.API_V2_EPUBS + self.urn + "/files"
            else:
                asset_base_url = next_chapter['asset_base_url']
                # Old v1 detection for hybrid chapters
                if 'v2' in next_chapter['content']:
                    asset_base_url = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{}/files".format(self.book_id)
                    is_v2 = True

            # Images from v2 related_assets or v1 images field
            if is_v2 and "related_assets" in next_chapter:
                for img_url in next_chapter["related_assets"].get("images", []):
                    self.images.append(img_url)
            elif "images" in next_chapter and len(next_chapter["images"]):
                for img_url in next_chapter['images']:
                    if is_v2:
                        self.images.append(asset_base_url + '/' + img_url)
                    else:
                        self.images.append(urljoin(next_chapter['asset_base_url'], img_url))

            # Stylesheets from v2 related_assets or v1 stylesheets field
            self.chapter_stylesheets = []
            if is_v2 and "related_assets" in next_chapter:
                for ss_url in next_chapter["related_assets"].get("stylesheets", []):
                    self.chapter_stylesheets.append(ss_url)
            else:
                if "stylesheets" in next_chapter and len(next_chapter["stylesheets"]):
                    self.chapter_stylesheets.extend(x["url"] for x in next_chapter["stylesheets"])

            if "site_styles" in next_chapter and len(next_chapter["site_styles"]):
                self.chapter_stylesheets.extend(next_chapter["site_styles"])

            if os.path.isfile(os.path.join(self.BOOK_PATH, "OEBPS", self.filename.replace(".html", ".xhtml"))):
                if not self.display.book_ad_info and \
                        next_chapter not in self.book_chapters[:self.book_chapters.index(next_chapter)]:
                    self.display.info(
                        ("File `%s` already exists.\n"
                         "    If you want to download again all the book,\n"
                         "    please delete the output directory '" + self.BOOK_PATH + "' and restart the program.")
                         % self.filename.replace(".html", ".xhtml")
                    )
                    self.display.book_ad_info = 2

            else:
                self.save_page_html(self.parse_html(self.get_html(next_chapter["content"]), first_page))

            self.display.state(len_books, len_books - len(self.chapters_queue))

    def _thread_download_css(self, url):
        css_file = os.path.join(self.css_path, "Style{0:0>2}.css".format(self.css.index(url)))
        if os.path.isfile(css_file):
            if not self.display.css_ad_info.value and url not in self.css[:self.css.index(url)]:
                self.display.info(("File `%s` already exists.\n"
                                   "    If you want to download again all the CSSs,\n"
                                   "    please delete the output directory '" + self.BOOK_PATH + "'"
                                   " and restart the program.") %
                                  css_file)
                self.display.css_ad_info.value = 1

        else:
            response = self.requests_provider(url)
            if response == 0:
                self.display.error("Error trying to retrieve this CSS: %s\n    From: %s" % (css_file, url))

            with open(css_file, 'wb') as s:
                s.write(response.content)

        self.css_done_queue.put(1)
        self.display.state(len(self.css), self.css_done_queue.qsize())


    def _thread_download_images(self, url):
        image_name = url.split("/")[-1]
        image_path = os.path.join(self.images_path, image_name)
        if os.path.isfile(image_path):
            if not self.display.images_ad_info.value and url not in self.images[:self.images.index(url)]:
                self.display.info(("File `%s` already exists.\n"
                                   "    If you want to download again all the images,\n"
                                   "    please delete the output directory '" + self.BOOK_PATH + "'"
                                   " and restart the program.") %
                                  image_name)
                self.display.images_ad_info.value = 1

        else:
            response = self.requests_provider(urljoin(SAFARI_BASE_URL, url), stream=True)
            if response == 0:
                self.display.error("Error trying to retrieve this image: %s\n    From: %s" % (image_name, url))
                return

            with open(image_path, 'wb') as img:
                for chunk in response.iter_content(1024):
                    img.write(chunk)

        self.images_done_queue.put(1)
        self.display.state(len(self.images), self.images_done_queue.qsize())

    def _start_multiprocessing(self, operation, full_queue):
        if len(full_queue) > 5:
            for i in range(0, len(full_queue), 5):
                self._start_multiprocessing(operation, full_queue[i:i + 5])

        else:
            process_queue = [Process(target=operation, args=(arg,)) for arg in full_queue]
            for proc in process_queue:
                proc.start()

            for proc in process_queue:
                proc.join()

    def collect_css(self):
        self.display.state_status.value = -1

        # "self._start_multiprocessing" seems to cause problem. Switching to mono-thread download.
        for css_url in self.css:
            self._thread_download_css(css_url)

    def collect_images(self):
        if self.display.book_ad_info == 2:
            self.display.info("Some of the book contents were already downloaded.\n"
                              "    If you want to be sure that all the images will be downloaded,\n"
                              "    please delete the output directory '" + self.BOOK_PATH +
                              "' and restart the program.")

        self.display.state_status.value = -1

        # "self._start_multiprocessing" seems to cause problem. Switching to mono-thread download.
        for image_url in self.images:
            self._thread_download_images(image_url)

    def create_content_opf(self):
        self.css = next(os.walk(self.css_path))[2]
        self.images = next(os.walk(self.images_path))[2]

        manifest = []
        spine = []
        for c in self.book_chapters:
            c["filename"] = c["filename"].replace(".html", ".xhtml")
            item_id = escape("".join(c["filename"].split(".")[:-1]))
            manifest.append("<item id=\"{0}\" href=\"{1}\" media-type=\"application/xhtml+xml\" />".format(
                item_id, c["filename"]
            ))
            spine.append("<itemref idref=\"{0}\"/>".format(item_id))

        for i in set(self.images):
            dot_split = i.split(".")
            head = "img_" + escape("".join(dot_split[:-1]))
            extension = dot_split[-1]
            manifest.append("<item id=\"{0}\" href=\"Images/{1}\" media-type=\"image/{2}\" />".format(
                head, i, "jpeg" if "jp" in extension else extension
            ))

        for i in range(len(self.css)):
            manifest.append("<item id=\"style_{0:0>2}\" href=\"Styles/Style{0:0>2}.css\" "
                            "media-type=\"text/css\" />".format(i))

        authors = "\n".join("<dc:creator opf:file-as=\"{0}\" opf:role=\"aut\">{0}</dc:creator>".format(
            escape(aut.get("name", "n/d"))
        ) for aut in self.book_info.get("authors", []))

        subjects = "\n".join("<dc:subject>{0}</dc:subject>".format(escape(sub.get("name", "n/d")))
                             for sub in self.book_info.get("subjects", []))

        return self.CONTENT_OPF.format(
            (self.book_info.get("isbn",  self.book_id)),
            escape(self.book_title),
            authors,
            escape(self.book_info.get("description", "")),
            subjects,
            ", ".join(escape(pub.get("name", "")) for pub in self.book_info.get("publishers", [])),
            escape(self.book_info.get("rights", "")),
            self.book_info.get("issued", ""),
            self.cover,
            "\n".join(manifest),
            "\n".join(spine),
            self.book_chapters[0]["filename"].replace(".html", ".xhtml")
        )

    @staticmethod
    def parse_toc(l, c=0, mx=0):
        r = ""
        for cc in l:
            c += 1
            if int(cc["depth"]) > mx:
                mx = int(cc["depth"])

            r += "<navPoint id=\"{0}\" playOrder=\"{1}\">" \
                 "<navLabel><text>{2}</text></navLabel>" \
                 "<content src=\"{3}\"/>".format(
                    cc["fragment"] if len(cc["fragment"]) else cc["id"], c,
                    escape(cc["label"]), cc["href"].replace(".html", ".xhtml").split("/")[-1]
                 )

            if cc["children"]:
                sr, c, mx = SafariBooks.parse_toc(cc["children"], c, mx)
                r += sr

            r += "</navPoint>\n"

        return r, c, mx

    def create_toc(self):
        # Try v1 API first
        response = self.requests_provider(urljoin(self.api_url, "toc/"))
        if response != 0 and response.status_code == 200:
            try:
                toc_data = response.json()
                if isinstance(toc_data, list):
                    navmap, _, max_depth = self.parse_toc(toc_data)
                    return self.TOC_NCX.format(
                        (self.book_info["isbn"] if self.book_info["isbn"] else self.book_id),
                        max_depth,
                        self.book_title,
                        ", ".join(aut.get("name", "") for aut in self.book_info.get("authors", [])),
                        navmap
                    )
            except (ValueError, KeyError):
                pass

        # Fallback: build TOC from chapter list
        self.display.info("Building TOC from chapter list...")
        r = ""
        c = 0
        for ch in self.book_chapters:
            c += 1
            ch_filename = ch["filename"].replace(".html", ".xhtml")
            r += '<navPoint id="navpoint-{0}" playOrder="{0}">' \
                 '<navLabel><text>{1}</text></navLabel>' \
                 '<content src="{2}"/>'.format(
                    c, escape(ch["title"]), ch_filename
                 )
            r += "</navPoint>\n"

        return self.TOC_NCX.format(
            (self.book_info["isbn"] if self.book_info["isbn"] else self.book_id),
            1,
            self.book_title,
            ", ".join(aut.get("name", "") for aut in self.book_info.get("authors", [])),
            r
        )

    def create_epub(self):
        open(os.path.join(self.BOOK_PATH, "mimetype"), "w").write("application/epub+zip")
        meta_info = os.path.join(self.BOOK_PATH, "META-INF")
        if os.path.isdir(meta_info):
            self.display.log("META-INF directory already exists: %s" % meta_info)

        else:
            os.makedirs(meta_info)

        open(os.path.join(meta_info, "container.xml"), "wb").write(
            self.CONTAINER_XML.encode("utf-8", "xmlcharrefreplace")
        )
        open(os.path.join(self.BOOK_PATH, "OEBPS", "content.opf"), "wb").write(
            self.create_content_opf().encode("utf-8", "xmlcharrefreplace")
        )
        open(os.path.join(self.BOOK_PATH, "OEBPS", "toc.ncx"), "wb").write(
            self.create_toc().encode("utf-8", "xmlcharrefreplace")
        )

        zip_file = os.path.join(PATH, "Books", self.book_id)
        if os.path.isfile(zip_file + ".zip"):
            os.remove(zip_file + ".zip")

        shutil.make_archive(zip_file, 'zip', self.BOOK_PATH)
        os.rename(zip_file + ".zip", os.path.join(self.BOOK_PATH, self.book_id) + ".epub")


# CLI with Click
@click.group()
@click.option('--cred', metavar='<EMAIL:PASS>', default=None, help='Credentials for auth login (e.g. "user@mail.com:password01").')
@click.option('--login', is_flag=True, default=False, help='Open a browser for interactive login.')
@click.option('--no-cookies', is_flag=True, default=False, help='Prevent saving session data to cookies.json.')
@click.pass_context
def cli(ctx, cred, login, no_cookies):
    """Download and generate EPUB books from Safari Books Online."""
    ctx.ensure_object(dict)
    ctx.obj['no_cookies'] = no_cookies
    
    if cred and login:
        click.echo("Error: --cred and --login are mutually exclusive.")
        sys.exit(1)
    
    if cred:
        parsed = SafariBooks.parse_cred(cred)
        if not parsed:
            click.echo("Error: invalid credential format. Expected 'email:password'.")
            sys.exit(1)
        ctx.obj['cred'] = parsed
    elif login:
        ctx.obj['cred'] = [None, None]
    else:
        ctx.obj['cred'] = None


@cli.command()
@click.argument('book_id')
@click.option('--kindle', is_flag=True, default=False, help='Add CSS rules for Kindle compatibility.')
@click.option('--preserve-log', is_flag=True, default=False, help='Keep the log file even without errors.')
@click.pass_context
def download(ctx, book_id, kindle, preserve_log):
    """Download a book by its ID and generate an EPUB."""
    sb = SafariBooks(display=Display("info_%s.log" % escape(book_id)))
    sb.display.intro()
    sb.authenticate(cred=ctx.obj['cred'], no_cookies=ctx.obj['no_cookies'])
    
    # Save cookies after successful auth
    if not ctx.obj['no_cookies']:
        json.dump(sb.session.cookies.get_dict(), open(COOKIES_FILE, "w"))
    
    sb.download(book_id, kindle=kindle, preserve_log=preserve_log)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--page', default=1, help='Page number for search results.')
@click.option('--limit', default=10, help='Number of results per page.')
@click.pass_context
def search(ctx, query, page, limit):
    """Search for books on Safari Books Online and download by selection."""
    query_str = ' '.join(query)
    
    sb = SafariBooks(display=Display("info_search.log"))
    sb.display.intro()
    sb.authenticate(cred=ctx.obj['cred'], no_cookies=ctx.obj['no_cookies'])
    
    # Save cookies after successful auth
    if not ctx.obj['no_cookies']:
        json.dump(sb.session.cookies.get_dict(), open(COOKIES_FILE, "w"))
    
    # Interactive search loop
    current_page = page
    while True:
        click.echo(click.style("\nSearching for: '%s' (page %d)" % (query_str, current_page), fg='yellow'))
        results, total, has_next = sb.search(query_str, page=current_page, limit=limit)
        
        if not results:
            click.echo("No results found.")
            return
        
        click.echo(click.style("Found %d results. Showing page %d:" % (total, current_page), fg='green'))
        click.echo("-" * 60)
        
        offset = (current_page - 1) * limit
        for i, r in enumerate(results):
            idx = offset + i + 1
            line1, line2 = SafariBooks.format_search_result(idx, r)
            click.echo(click.style(line1, fg='cyan'))
            click.echo(line2)
            click.echo()
        
        click.echo("-" * 60)
        prompt = "Enter number to download"
        if has_next:
            prompt += ", 'n' for next page"
        prompt += ", 'q' to quit"
        
        choice = click.prompt(prompt, default='').strip()
        
        if choice.lower() == 'q':
            click.echo("Bye!")
            return
        
        if choice.lower() == 'n' and has_next:
            current_page += 1
            continue
        
        # Try to parse as a number
        try:
            num = int(choice)
            if num < 1 or num > offset + len(results):
                if num > offset + len(results):
                    click.echo("Number out of range.")
                elif num < 1:
                    click.echo("Please enter a positive number.")
                continue
        except (ValueError, TypeError):
            click.echo("Invalid input.")
            continue
        
        # Find the selected book
        selected_idx = num - 1
        selected_offset = (current_page - 1) * limit
        result_idx = selected_idx - selected_offset
        
        if result_idx < 0 or result_idx >= len(results):
            # The selected number might be from a previous page we don't have
            # Re-fetch that page
            result_page = (selected_idx // limit) + 1
            result_page_offset = (result_page - 1) * limit
            new_results, _, _ = sb.search(query_str, page=result_page, limit=limit)
            result_idx = selected_idx - result_page_offset
            if result_idx < 0 or result_idx >= len(new_results):
                click.echo("Number out of range.")
                continue
            selected = new_results[result_idx]
        else:
            selected = results[result_idx]
        
        # Show full details and confirm
        book_id = selected.get('archive_id', selected.get('isbn', ''))
        title = selected.get('title', 'Unknown')
        authors = ', '.join(selected.get('authors', [])) or 'Unknown'
        publisher = ', '.join(selected.get('publishers', [])) or 'Unknown'
        year = selected.get('issued', '')[:4] if selected.get('issued') else 'n/a'
        pages = selected.get('virtual_pages', '?')
        description = re.sub(r'<[^>]+>', '', selected.get('description', '')).strip()
        if len(description) > 500:
            description = description[:500] + '...'
        
        click.echo(click.style("\n" + "=" * 60, fg='yellow'))
        click.echo(click.style("Title: ", fg='yellow') + title)
        click.echo(click.style("Authors: ", fg='yellow') + authors)
        click.echo(click.style("Publisher: ", fg='yellow') + publisher)
        click.echo(click.style("Year: ", fg='yellow') + year)
        click.echo(click.style("Pages: ", fg='yellow') + str(pages))
        click.echo(click.style("ID: ", fg='yellow') + book_id)
        click.echo(click.style("Description: ", fg='yellow'))
        click.echo(description)
        click.echo(click.style("=" * 60, fg='yellow'))
        
        if click.confirm('Download this book?'):
            sb.download(book_id)
            return
        else:
            click.echo("Cancelled. Returning to search results...\n")


if __name__ == "__main__":
    cli()
