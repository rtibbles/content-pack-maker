import os
import requests


def download_and_cache_file(url, cachedir=None, ignorecache=False) -> str:
    """
    Download the given url if it's not saved in cachedir. Returns the
    path to the file. Always download the file if ignorecache is True.
    """

    if not cachedir:
        cachedir = os.path.join(os.getcwd(), "build")

    os.makedirs(cachedir, exist_ok=True)

    path = os.path.join(cachedir, os.path.basename(url))

    if ignorecache or not os.path.exists(path):
        r = requests.get(url, stream=True)
        r.raise_for_status()

        with open(path, "w") as f:
            for chunk in r.iter_content(1024, decode_unicode=True):
                f.write(chunk)

    return path
