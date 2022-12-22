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
import time
from config import Config
from db import DbClient
from helpers import strip_to_hostname
import uuid
from multiprocessing import Pool, Process


config = Config()

q_urls = UniqueQueue()
q_audit = UniqueQueue()

app = Flask(__name__)
db_client = DbClient().connect()


@app.route('/api/scrape', methods=['POST'])
def add_scrape_url():
    if 'urls' not in request.json:
        return Response("Missing 'urls' array param", status=401)

    urls = request.json['urls']

    for url in urls:
        add_to_scrape_queue(url)

    return Response("", status=200)


def main():

    threading.Thread(target=worker_scrape_urls, daemon=True).start()

    for i in range(3):
        worker_id = i + 1
        print(f'Starting worker_audit thread #{worker_id}')
        threading.Thread(target=worker_audit, daemon=True,
                         args=(worker_id,)).start()

    app.run(debug=True, host='0.0.0.0', port=1338)

    return


def add_to_audit_queue(url):
    if q_audit.exists(url) or db_client.url_has_entry(url):
        print(
            f'Skipping adding {url} to AUDIT queue: already exists in queue or DB')

        return False

    q_audit.put(url)

    return True


def add_to_scrape_queue(url):
    if q_urls.exists(url):
        print(
            f'Skipping adding {url} to SCRAPE queue: already exists in queue')

        return False

    q_urls.put(url)

    return True


def worker_audit(worker_id):

    worker_sig = f'[Worker #{worker_id}]'

    while True:
        tic = time.perf_counter()

        audit_url = q_audit.get()

        if db_client.url_has_entry(audit_url):
            print(
                f'{worker_sig} Skipping audit for {audit_url}: audit already exists in DB')
            continue

        print(
            f'{worker_sig} Auditing {audit_url}...')

        # Run lighthouse node command (must be installed globally on OS)
        outpath = f"./audit/{urllib.parse.quote_plus(audit_url)}.json"
        os.system(
            f'lighthouse {audit_url} --output=json --output-path="{outpath}" --chrome-flags="--headless" --only-categories=performance --max-wait-for-load=20000 --quiet')

        toc = time.perf_counter()
        elapsed_timespan = toc - tic

        outfile = open(outpath)
        outfile_json = json.load(outfile)
        # Remove unnecessary bits
        del outfile_json['audits']['screenshot-thumbnails']
        del outfile_json['audits']['full-page-screenshot']
        del outfile_json['i18n']

        record = {
            'url': audit_url,
            'host': strip_to_hostname(audit_url),
            'elapsedTimeSeconds': round(elapsed_timespan, 2),
            'lighthouse': outfile_json
        }

        db_client.insert_audit_record(record)

        q_audit.task_done()

        print(
            f'{worker_sig} Finished auditing {audit_url} in {elapsed_timespan:0.2f}s; {q_audit.unfinished_tasks} left in AUDIT queue')


def worker_scrape_urls():
    while True:
        url = q_urls.get()

        print(
            f'Scraping {url}... ({q_urls.unfinished_tasks} left in scrape queue)')

        # If no protocol given, assume http (server will likely upgrade us to https automatically)
        # but maybe not
        if not url.startswith('http'):
            url = f'http://{url}'

        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0'
        })

        if (resp.ok):

            host = strip_to_hostname(resp.url)
            print(f'Identified host for {url} as {host}')

            added_to_queue = 0
            # Add homepage URL to audit queue
            if add_to_audit_queue(resp.url):
                added_to_queue = added_to_queue + 1

            soup = BeautifulSoup(resp.text, 'html.parser')

            for link in soup.find_all('a'):
                href = link.get('href')

                # Check the link is relative to this site
                if href is not None and len(href) > 1 and href.startswith('/#') == False and (href.startswith('/') or strip_to_hostname(href) == host):

                    full_url = urllib.parse.urljoin(resp.url, href)

                    if (not q_audit.exists(full_url)):
                        print(
                            f'Found {full_url} under {resp.url}; adding to AUDIT queue')

                        if add_to_audit_queue(full_url):
                            added_to_queue = added_to_queue + 1

            print(
                f'Finished scraping {url}: {added_to_queue} added to audit queue')

        else:

            print(
                f'Abandoned scrape for {url}: GET request failed with status code {resp.status_code}')

        q_urls.task_done()


# main()

if __name__ == '__main__':
    print('Starting app...')
    main()
