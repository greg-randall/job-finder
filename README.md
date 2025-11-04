# Job Scraper and Matcher

This project is a collection of Python scripts designed to scrape job postings from various websites, process them, and rate them against a candidate's resume and cover letter using the OpenAI API.

## Project Structure

The project is organized into several key files:

- **`functions.py`**: A utility module containing common functions used across the different scrapers. This includes functions for:
    - Initializing a web browser (Playwright and Selenium) with anti-detection measures.
    - Navigating to web pages with retry logic.
    - Handling cookie consent modals.
    - Downloading and caching web page content.
    - Interacting with the OpenAI API to process text.

- **`process_jobs.py`**: The core script for processing and rating job postings. It performs the following steps:
    1. Reads cached job postings from the `cache/` directory.
    2. For each job, it calls the OpenAI API to evaluate how well the job description matches the candidate's resume and cover letter.
    3. The evaluation includes an overall rating and individual scores for experience, education, skills, and interest.
    4. The results are saved to a `processed_jobs.csv` file.
    5. It can also generate ranked lists of jobs based on the evaluation scores.

- **`scraper_*.py`**: Each of these files is a dedicated scraper for a specific job board or platform (e.g., `scraper_workday.py`, `scraper_linkedin.py`). These scripts use the functions from `functions.py` to:
    - Navigate to the target job board.
    - Find and extract links to individual job postings.
    - Download the content of each job posting and save it to the `cache/` directory for later processing.

- **`cache/`**: A directory where the raw HTML content of scraped job postings is stored. This prevents the need to re-download the same job posting multiple times.

- **`processed_jobs.csv`**: The output CSV file containing the processed and rated job postings.

## How it Works

1. **Scraping**: The `scraper_*.py` scripts are run to gather job postings from various websites. They navigate through job listings, collect links to individual jobs, and save the HTML content of each job page into the `cache/` directory.

2. **Processing**: The `process_jobs.py` script is then run to analyze the scraped jobs. It reads the cached HTML files, extracts the relevant text from each job description, and sends it to the OpenAI API along with the candidate's resume and cover letter.

3. **Rating**: The OpenAI API, using a powerful language model like GPT-4, evaluates the job description against the candidate's documents and returns a structured JSON object with ratings for different categories (experience, education, skills, interest) and other relevant information like job title, company, location, and salary.

4. **Output**: The processed data, including the ratings, is saved in the `processed_jobs.csv` file. This file can then be used to identify the most promising job opportunities.

## Dependencies

This project relies on several Python libraries for web scraping, data processing, and interacting with the OpenAI API. The main dependencies include:

- `openai`: For interacting with the OpenAI API.
- `playwright` and `selenium`: For web browser automation and scraping.
- `beautifulsoup4` and `trafilatura`: For parsing HTML and extracting content.
- `pandas`: For data manipulation and creating CSV files.
- `geopy`: For geocoding and location-based filtering.
- `tqdm`: For displaying progress bars.

## Usage

1. **Installation**: Install the required Python libraries using pip:
   ```bash
   pip install openai playwright selenium beautifulsoup4 trafilatura pandas geopy tqdm undetected-chromedriver aiofiles python-dotenv pyppeteer pyppeteer-stealth termcolor
   ```

2. **Configuration**:
   - Create a `.env` file in the root directory and add your OpenAI API key:
     ```
     OPENAI_API_KEY="your_openai_api_key"
     ```
   - Place your resume and cover letter files (e.g., `resume.md`, `cover_letter.md`) in the root directory.

3. **Scraping**: Run the desired scraper scripts to collect job postings:
   ```bash
   python scraper_linkedin.py
   python scraper_workday.py
   # ... and so on for other scrapers
   ```

4. **Processing**: After scraping, run the `process_jobs.py` script to rate the collected jobs:
   ```bash
   python process_jobs.py --resume resume.md --cover-letter cover_letter.md
   ```
   You can use various command-line arguments to customize the processing, such as `--max-jobs` to limit the number of jobs processed or `--force` to re-process already rated jobs.

5. **Review Results**: Open the `processed_jobs.csv` file to see the rated job postings. You can also check the `ranked_jobs.csv` and `high_quality_matches_*.csv` files for filtered and ranked lists of jobs.
