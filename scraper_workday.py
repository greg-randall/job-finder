"""This module scrapes job postings from Workday job boards."""

import asyncio

from functions import scrape_site


JOBS = ["https://bbinsurance.wd1.myworkdayjobs.com/en-US/Careers",
        "https://graybar.wd1.myworkdayjobs.com/Careers",
        "https://gsknch.wd3.myworkdayjobs.com/GSKCareers",
        "https://hksinc.wd5.myworkdayjobs.com/HKSCareers",
        "https://indivior.wd3.myworkdayjobs.com/Indivior",
        ("https://jdrf.wd1.myworkdayjobs.com/JDRF?"
         "_ga=2.68390741.594165681.1704744294-2139354499.1696866599&"
         "_gac=1.47826835.1703000449.EAIaIQobChMI_ufrg-ubgwMV-0tHAR39qwUqEAAYASAAEgJlRfD_BwE"),
        "https://markelcorp.wd5.myworkdayjobs.com/GlobalCareers",
        "https://nascar.wd1.myworkdayjobs.com/NASCAR",
        "https://patientfirst.wd5.myworkdayjobs.com/PatientFirst",
        "https://pgatoursuperstore.wd12.myworkdayjobs.com/PGAT_SS",
        "https://qtsdatacenters.wd5.myworkdayjobs.com/en-US/qts",
        "https://richmond.wd5.myworkdayjobs.com/staff_faculty",
        "https://sci.wd5.myworkdayjobs.com/SCI",
        "https://scripps.wd5.myworkdayjobs.com/Scripps_Careers",
        "https://sonoco.wd1.myworkdayjobs.com/en-US/CorporateCareers",
        "https://vacu.wd1.myworkdayjobs.com/VACU_Careers?jobFamilyGroup=7701a7cf554a0101b6e137cc26780000",
        "https://xylem.wd5.myworkdayjobs.com/xylem-careers"]


async def main():
    """Scrapes all Workday job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} Workday job boards")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        print(f"\n🔄 Processing site {index}/{total_sites}: {name}")
        await scrape_site(
            url, name, '[data-automation-id="jobTitle"]',
            '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
            '[data-uxi-widget-type="stepToNextButton"][disabled]'
        )

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
