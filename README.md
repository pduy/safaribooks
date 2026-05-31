# SafariBooks
Download and generate *EPUB* of your favorite books from [*Safari Books Online*](https://www.safaribooksonline.com) library.  
I'm not responsible for the use of this program, this is only for *personal* and *educational* purpose.  
Before any usage please read the *O'Reilly*'s [Terms of Service](https://learning.oreilly.com/terms/).  

<a href='https://ko-fi.com/Y8Y0MPEGU' target='_blank'><img height='80' style='border:0px;height:60px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com'/></a>

## ✨✨ *Attention needed* ✨✨
- This project is no longer actively maintained.
- ~~*Login through `safaribooks` no longer works due to changes in ORLY APIs.*~~ **Fixed!** Direct login now works via browser automation (Playwright).
- *The program needs a major refactor to include new features and integrate new APIs.*
- **It works for downloading books.** Login via `--cred`, `--login`, or `cookies.json`. Love ❤️

---

## Overview:
  * [Requirements & Setup](#requirements--setup)
  * [Usage](#usage)
  * [Single Sign-On (SSO), Company, University Login](https://github.com/lorenzodifuccia/safaribooks/issues/150#issuecomment-555423085)
  * [Calibre EPUB conversion](https://github.com/lorenzodifuccia/safaribooks#calibre-epub-conversion)
  * [Example: Download *Test-Driven Development with Python, 2nd Edition*](#download-test-driven-development-with-python-2nd-edition)
  * [Example: Use or not the `--kindle` option](#use-or-not-the---kindle-option)

## Requirements & Setup:
First of all, it requires `python3` (>=3.9) and `pip3` or `uv` to be installed.  
```shell
$ git clone https://github.com/lorenzodifuccia/safaribooks.git
Cloning into 'safaribooks'...

$ cd safaribooks/
$ pip3 install -r requirements.txt

OR (recommended, with uv):

$ uv sync
```

The program depends of only three **Python _3_** modules:
```python3
lxml>=4.1.1
requests>=2.20.0
click>=8.1.0
```

For login via `--cred` or `--login`, you also need **Playwright**:
```shell
$ uv sync --extra login && uv run playwright install chromium
```

This enables browser-based login that bypasses O'Reilly's Akamai bot protection.
  
## Usage:

There are **two commands**: `download` and `search`.

### Download a book by ID

```shell
# Using cookies from a previous session:
$ uv run python safaribooks.py download XXXXXXXXXXXXX

# Using credentials:
$ uv run --extra login python safaribooks.py --cred "account_mail@mail.com:password01" download XXXXXXXXXXXXX

# Interactive browser login:
$ uv run --extra login python safaribooks.py --login download XXXXXXXXXXXXX
```

### Search for books

```shell
# Search and interactively pick a book to download:
$ uv run python safaribooks.py search "machine learning python"

# Search with credentials:
$ uv run --extra login python safaribooks.py --cred "account_mail@mail.com:password01" search "machine learning python"

# Specify page and results per page:
$ uv run python safaribooks.py search --page 2 --limit 20 "rust programming"
```

The search shows results with title, authors, book ID, and year. You can:
- Enter a **number** to see full details and confirm download
- Type **`n`** for the next page of results
- Type **`q`** to quit

### Authentication options

Auth options (`--cred`, `--login`, `--no-cookies`) are specified on the main command, before the subcommand:

```shell
$ uv run python safaribooks.py --cred "email:pass" download 9781491958698
$ uv run python safaribooks.py --login search "python"
$ uv run python safaribooks.py --no-cookies download 9781491958698
```

### Program options:
```shell
$ python3 safaribooks.py --help
Usage: safaribooks.py [OPTIONS] COMMAND [ARGS]...

  Download and generate EPUB books from Safari Books Online.

Options:
  --cred <EMAIL:PASS>  Credentials for auth login (e.g. "user@mail.com:password01").
  --login              Open a browser for interactive login.
  --no-cookies         Prevent saving session data to cookies.json.
  --help               Show this help message and exit.

Commands:
  download  Download a book by its ID and generate an EPUB.
  search    Search for books on Safari Books Online and download by selection.

$ python3 safaribooks.py download --help
Usage: safaribooks.py download [OPTIONS] BOOK_ID

  Download a book by its ID and generate an EPUB.

Options:
  --kindle        Add CSS rules for Kindle compatibility.
  --preserve-log  Keep the log file even without errors.
  --help           Show this help message and exit.

$ python3 safaribooks.py search --help
Usage: safaribooks.py search [OPTIONS] QUERY...

  Search for books on Safari Books Online and download by selection.

Options:
  --page INTEGER   Page number for search results.
  --limit INTEGER  Number of results per page.
  --help           Show this help message and exit.
```
  
When using `--cred`, the program opens a browser window, auto-fills your credentials, and waits for you to complete any 2FA/CAPTCHA.  
When using `--login`, the program opens a browser window for interactive login (supports SSO/2FA).  
In both cases, session cookies are saved to `cookies.json` for future use — so next time you can run without `--cred` or `--login` until the session expires.

For **SSO/Company/University login**, use `--login` and complete the login flow in the browser.

For the manual **cookies.json** approach, use `retrieve_cookies.py` (see below).  
  
Pay attention if you use a shared PC, because everyone that has access to your files can steal your session. 
If you don't want to cache the cookies, just use the `--no-cookies` option and provide all time your credential through the `--cred` option or the more safe `--login` one: this will prompt you for credential during the script execution.

You can configure proxies by setting on your system the environment variable `HTTPS_PROXY` or using the `USE_PROXY` directive into the script.

#### Calibre EPUB conversion
**Important**: since the script only download HTML pages and create a raw EPUB, many of the CSS and XML/HTML directives are wrong for an E-Reader. To ensure best quality of the output, I suggest you to always convert the `EPUB` obtained by the script to standard-`EPUB` with [Calibre](https://calibre-ebook.com/).
You can also use the command-line version of Calibre with `ebook-convert`, e.g.:
```bash
$ ebook-convert "XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)/9781491958698.epub" "XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)/9781491958698_CLEAR.epub"
```
After the execution, you can read the `9781491958698_CLEAR.epub` in every E-Reader and delete all other files.

The program offers also an option to ensure best compatibilities for who wants to export the `EPUB` to E-Readers like Amazon Kindle: `--kindle`, it blocks overflow on `table` and `pre` elements (see [example](#use-or-not-the---kindle-option)).  
In this case, I suggest you to convert the `EPUB` to `AZW3` with Calibre or to `MOBI`, remember in this case to select `Ignore margins` in the conversion options:  
  
![Calibre IgnoreMargins](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_calibre_IgnoreMargins.png "Select Ignore margins")  
  
## Examples:
  * ## Download [Test-Driven Development with Python, 2nd Edition](https://www.safaribooksonline.com/library/view/test-driven-development-with/9781491958698/):  
    ```shell
    $ python3 safaribooks.py --cred "my_email@gmail.com:MyPassword1!" 9781491958698

           ____     ___         _ 
          / __/__ _/ _/__ _____(_)
         _\ \/ _ `/ _/ _ `/ __/ / 
        /___/\_,_/_/ \_,_/_/ /_/  
          / _ )___  ___  / /__ ___
         / _  / _ \/ _ \/  '_/(_-<
        /____/\___/\___/_/\_\/___/

    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    [-] Logging into Safari Books Online...
    [*] Retrieving book info... 
    [-] Title: Test-Driven Development with Python, 2nd Edition                     
    [-] Authors: Harry J.W. Percival                                                
    [-] Identifier: 9781491958698                                                   
    [-] ISBN: 9781491958704                                                         
    [-] Publishers: O'Reilly Media, Inc.                                            
    [-] Rights: Copyright © O'Reilly Media, Inc.                                    
    [-] Description: By taking you through the development of a real web application 
    from beginning to end, the second edition of this hands-on guide demonstrates the 
    practical advantages of test-driven development (TDD) with Python. You’ll learn 
    how to write and run tests before building each part of your app, and then develop
    the minimum amount of code required to pass those tests. The result? Clean code
    that works.In the process, you’ll learn the basics of Django, Selenium, Git, 
    jQuery, and Mock, along with curre...
    [-] Release Date: 2017-08-18
    [-] URL: https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/
    [*] Retrieving book chapters...                                                 
    [*] Output directory:                                                           
        /XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)
    [-] Downloading book contents... (53 chapters)                                  
        [#####################################################################] 100%
    [-] Downloading book CSSs... (2 files)                                          
        [#####################################################################] 100%
    [-] Downloading book images... (142 files)                                      
        [#####################################################################] 100%
    [-] Creating EPUB file...                                                       
    [*] Done: /XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition 
    (9781491958698)/9781491958698.epub
    
        If you like it, please * this project on GitHub to make it known:
            https://github.com/lorenzodifuccia/safaribooks
        e don't forget to renew your Safari Books Online subscription:
            https://learning.oreilly.com
    
    [!] Bye!!
    ```  
     The result will be (opening the `EPUB` file with Calibre):  

    ![Book Appearance](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_example01_TDD.png "Book opened with Calibre")  
 
  * ## Use or not the `--kindle` option:
    ```bash
    $ python3 safaribooks.py --kindle 9781491958698
    ```  
    On the right, the book created with `--kindle` option, on the left without (default):  
    
    ![NoKindle Option](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_example02_NoKindle.png "Version compare")  
    
---  
  
## Thanks!!
For any kind of problem, please don't hesitate to open an issue here on *GitHub*.  
  
*Lorenzo Di Fuccia*
