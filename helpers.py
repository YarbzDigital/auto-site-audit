import urllib.parse

def average(list):
    return sum(list) / len(list)

def strip_to_hostname(url):
    return urllib.parse.urlparse(url).netloc