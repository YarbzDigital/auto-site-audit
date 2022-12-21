import os
import urllib.parse
import requests
import threading
from bs4 import BeautifulSoup
from TinyMongoClient import TinyMongoClient
from UniqueQueue import UniqueQueue
from flask import Flask, Response, request
from tinymongo import tinymongo as tm
import json

cache_scraped_urls = {}

q_urls = UniqueQueue()
q_audit = UniqueQueue()

app = Flask(__name__)

tmclient = TinyMongoClient('./lsr_db')
tmconn = tmclient.default
tmcol_audits = tmconn.audits

@app.route('/api/scrape', methods=[ 'POST' ])
def add_scrape_url():
    if 'url' not in request.json:
        return Response("Missing 'url' param", status=401)
    
    url = request.json['url']
    q_urls.put(url)
    print(f'/api/scrape queued URL {url}')

    return Response("", status=200)

def main():
    print('Starting...')

    threading.Thread(target=worker_scrape_urls, daemon=False).start()
    threading.Thread(target=worker_audit, daemon=False).start()

    return

def strip_to_hostname(url):
    return urllib.parse.urlparse(url).netloc

def worker_audit():
    while True:
        audit_url = q_audit.get()

        print(f'Auditing {audit_url} ({q_audit.unfinished_tasks} left in audit queue)')

        # Run lighthouse node command (must be installed globally on OS)
        outpath = f"./audit/{urllib.parse.quote_plus(audit_url)}.json"
        os.system(f'lighthouse {audit_url} --output=json --output-path="{outpath}" --chrome-flags="--headless" --only-categories=performance --max-wait-for-load=20000')

        # Add to DB
        outfile = open(outpath)
        json_content = json.load(outfile)
        tmcol_audits.insert_one(json_content)

        print(f'Finished auditing {audit_url}')

        q_audit.task_done()
    
def worker_scrape_urls():
    while True:
        url = q_urls.get()

        print(f'Scraping ${url}... ({q_urls.unfinished_tasks} left in scrape queue)')

        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0'
        })

        if (resp.ok):

            host = strip_to_hostname(resp.url)
            print(f'Identified host for {url} as {host}')

            # Add homepage URL to audit queue
            q_audit.put(resp.url)

            found_urls = 0
            soup = BeautifulSoup(resp.text, 'html.parser')

            for link in soup.find_all('a'):
                href = link.get('href')

                # Check the link is relative to this site
                if href is not None and len(href) > 1 and href.startswith('/#') == False and (href.startswith('/') or strip_to_hostname(href) == host):

                    full_url = urllib.parse.urljoin(resp.url, href)

                    if (not q_audit.exists(full_url)):
                        print(
                            f'Found {full_url} under {resp.url}; adding to audit queue')

                        q_audit.put(full_url)

                        found_urls = found_urls + 1
            
            print(f'Finished scraping ${url}: {found_urls} added to audit queue')

        else:

            print(f'Abandoned scrape for {url}: GET request failed with status code {resp.status_code}')

        q_urls.task_done()


main()
