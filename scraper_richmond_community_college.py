"""This module scrapes job postings from the Richmond Community College job board."""

import asyncio
import xml.etree.ElementTree as ET

import aiohttp

from functions import init_browser, download_all_links
from logging_config import get_logger


NAME = "richmond-community-college"
URL = ("https://jobs.vccs.edu/postings/search.atom?"
       "utf8=%E2%9C%93&query=&query_v0_posted_at_date=&435=&query_organizational_tier_1_id%5B%5D=7885&commit=Search")


async def main():
    """Scrapes the Richmond Community College job board."""
    # Initialize logger
    logger = get_logger("richmond_community_college")

    logger.info("Starting Richmond Community College Scraper")
    logger.add_breadcrumb("Initializing browser")

    page = await init_browser(headless=True)

    logger.add_breadcrumb("Fetching XML feed")
    async with aiohttp.ClientSession() as session:
        async with session.get(URL) as response:
            xml_content = await response.text()

    logger.add_breadcrumb("Parsing XML")
    root = ET.fromstring(xml_content)

    job_links = []
    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        link = entry.find('{http://www.w3.org/2005/Atom}link')
        if link is not None and 'href' in link.attrib:
            job_links.append(link.attrib['href'])

    logger.info(f"Found {len(job_links)} job links in the XML feed")
    logger.increment_stat("total_jobs_found", len(job_links))

    logger.add_breadcrumb("Starting job download")
    logger.info("Starting download of job postings...")
    await download_all_links(job_links, page, NAME)

    await page.context.close()

    # Write summary
    duration = logger.write_summary()
    logger.info("Completed Richmond Community College job board scraping")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
