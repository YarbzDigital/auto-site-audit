from logging import warn
import os
import urllib.parse
import requests
import threading
from bs4 import BeautifulSoup
from TinyMongoClient import TinyMongoClient
from UniqueQueue import UniqueQueue
from flask import Flask, Response, request, json, make_response, jsonify
from tinymongo import tinymongo as tm
import json
import time
from config import Config
from db import DbClient
from helpers import strip_to_hostname
import uuid
from multiprocessing import Pool, Process
from colorama import init, Fore, Back, Style
import gzip
import subprocess
import logging

config = Config()

q_crawl = UniqueQueue()
q_audit = UniqueQueue()

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

db_client = DbClient().connect()

PRINT_SCRAPE = Style.NORMAL + Fore.LIGHTBLUE_EX
PRINT_QUEUE = Style.NORMAL + Fore.MAGENTA
PRINT_SKIP = Style.NORMAL + Fore.LIGHTBLACK_EX
PRINT_AUDIT = Style.NORMAL + Fore.BLUE
PRINT_AUDIT_SUCCESS = Style.NORMAL + Fore.GREEN
PRINT_ERROR = Style.NORMAL = Fore.RED

init(autoreset=True)

@app.route('/api/scrape', methods=['POST'])
def api_post_scrape_url():
    if 'urls' not in request.json:
        return Response("Missing 'urls' array param", status=401)

    urls = request.json['urls']

    for url in urls:
        if not add_to_scrape_queue(url):
            print(f'Skipping posted url {url}: already in queue')

    return Response("", status=200)


@app.route('/api/status', methods=['GET'])
def api_get_status():
    return Response(json.dumps({
        'queue_audit_item_count': q_audit.unfinished_tasks,
        'queue_crawl_item_count': q_crawl.unfinished_tasks
    }), status=200, mimetype='application/json')

@app.route('/api/hosts', methods=['GET'])
def api_get_hosts():
    
    hosts = []

    res = db_client.get_urls_by_host()
    for host in res:
        hosts.append(host)

    return jsonify(hosts)
    # content = gzip.compress(json_d.encode('utf8'), 9)
    # response = make_response(content)
    # response.headers['Content-Length'] = len(content)
    # response.headers['Content-Encoding'] = 'gzip'
    # response.headers['Content-Type'] = 'application/json; charset=utf-8'

    # return response


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
            f'{PRINT_SKIP}Skipping adding {url} to AUDIT queue: already exists in queue or DB')

        return False

    q_audit.put(url)
    print(f'{PRINT_QUEUE}Added {url} to AUDIT queue')

    return True


def add_to_scrape_queue(url):
    if q_crawl.exists(url):
        print(
            f'{PRINT_SKIP}Skipping adding {url} to SCRAPE queue: already exists in queue')

        return False

    q_crawl.put(url)
    print(f'{PRINT_QUEUE}Added {url} to SCRAPE queue')

    return True


def worker_audit(worker_id):

    worker_sig = f'[Worker #{worker_id}]'

    while True:
        tic = time.perf_counter()

        audit_url = q_audit.get()

        if db_client.url_has_entry(audit_url):
            print(
                f'{PRINT_SKIP}{worker_sig} Skipping audit for {audit_url}: audit already exists in DB')
            continue

        print(
            f'{PRINT_AUDIT}{worker_sig} Auditing {audit_url}...')

        try:

            # Run lighthouse node command (must be installed globally on OS)
            proc = subprocess.run(
                f'lighthouse {audit_url} --output=json --output-path="stdout" --chrome-flags="--headless --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run" --only-categories=performance,seo --max-wait-for-load=60000 --quiet',
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Handle process errors
            if proc.returncode != 0:
                raise Exception(f'Lighthouse subprocess exited with error code {proc.returncode}: {proc.stderr}')

            toc = time.perf_counter()
            elapsed_timespan = toc - tic

            outfile_json = json.loads(proc.stdout)

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
                f'{PRINT_AUDIT_SUCCESS}{worker_sig} Finished auditing {audit_url} in {elapsed_timespan:0.2f}s; {q_audit.unfinished_tasks} left in AUDIT queue')
        except Exception as e:
            msg = getattr(e, 'message', str(e))
            logging.error(PRINT_ERROR + f'An error occured while auditing {audit_url}: {msg}')

            


def worker_scrape_urls():
    while True:
        url = q_crawl.get()

        print(
            f'{PRINT_SCRAPE}Scraping {url}... ({q_crawl.unfinished_tasks} left in scrape queue)')

        # If no protocol given, assume http (server will likely upgrade us to https automatically)
        # but maybe not
        if not url.startswith('http'):
            url = f'http://{url}'

        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0'
        })

        if (resp.ok):

            host = strip_to_hostname(resp.url)

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

                    if add_to_audit_queue(full_url):
                        added_to_queue = added_to_queue + 1

        else:

            print(
                f'{PRINT_SKIP}Abandoned scrape for {url}: GET request failed with status code {resp.status_code}')

        q_crawl.task_done()


# main()

if __name__ == '__main__':
    print('Starting app...')
    main()
