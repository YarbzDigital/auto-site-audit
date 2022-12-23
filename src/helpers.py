from urllib.parse import urlparse
import pathlib

def average(list):
    return sum(list) / len(list)

def strip_to_hostname(url):
    return urlparse(url).netloc

def normalize_url(url):
    parsed = urlparse(url)
    
    # If no scheme given, default toh http (will be auto-upgraded)
    # by host if necessary
    scheme = parsed.scheme if parsed.scheme != '' else 'http'

    return f'{scheme}://{parsed.netloc}{parsed.path}'

def is_url_file(url):
    parsed = urlparse(url)
    path = pathlib.Path(parsed.path)
    return path.suffix != ''