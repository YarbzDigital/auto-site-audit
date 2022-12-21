# auto-site-audit

 A service w/ API to scrape and locally audit page performance and SEO using Google's lighthouse.

## Requirements

- npm
- `lighthouse` npm package (`npm install -g lighthouse`)
- python3

## Running

1.  Run `python report.py`
2. Post HTTP request to `http://127.0.0.1:5000/api/scrape` with body:

```
{
	"url": "URL_TO_SCRAPE_AND_AUDIT"
}
```