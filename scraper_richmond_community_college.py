"""This module scrapes job postings from the Richmond Community College job board."""

import asyncio
import xml.etree.ElementTree as ET

import aiohttp

from functions import init_browser, download_all_links


NAME = "richmond-community-college"
URL = ("https://jobs.vccs.edu/postings/search.atom?"
       "utf8=%E2%9C%93&query=&query_v0_posted_at_date=&435=&query_organizational_tier_1_id%5B%5D=7885&commit=Search")


async def main():
    """Scrapes the Richmond Community College job board."""
    page = await init_browser(headless=True)

    async with aiohttp.ClientSession() as session:
        async with session.get(URL) as response:
            xml_content = await response.text()

    root = ET.fromstring(xml_content)

    job_links = []
    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        link = entry.find('{http://www.w3.org/2005/Atom}link')
        if link is not None and 'href' in link.attrib:
            job_links.append(link.attrib['href'])

    print(f"Found {len(job_links)} job links in the XML feed")

    print("\nStarting download of job postings...")
    await download_all_links(job_links, page, NAME)

    await page.context.close()


if __name__ == "__main__":
    asyncio.run(main())
