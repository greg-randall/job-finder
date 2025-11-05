# Job Scraper and Matcher

This project is a sophisticated, configuration-driven framework for scraping job postings from various websites, processing them, and rating them against a candidate's resume using the OpenAI API.

## Key Features

- **Centralized Configuration**: All settings are managed in `config.yaml`, allowing for easy updates without code changes.
- **Unified Scraper Architecture**: A flexible architecture supports different types of job boards through a factory pattern.
- **Single Entry Point**: `run_scrapers.py` script to run all or specific scrapers.
- **AI-Powered Job Matching**: `process_jobs.py` uses an AI model to rate and rank jobs based on your resume.
- **Extensible**: Easily add new job boards by updating the `config.yaml` file.

## Project Structure

The project is organized into several key components:

- **`config.yaml`**: The central configuration file for all settings, including job boards, API keys, and processing parameters.
- **`config_loader.py`**: A module for loading and accessing settings from `config.yaml`.
- **`run_scrapers.py`**: The main entry point for executing the job scrapers.
- **`process_jobs.py`**: The script for processing cached job postings and rating them with an AI model.
- **`scrapers/`**: This directory contains the modern, class-based scraper architecture.
    - **`base_scraper.py`**: The abstract base class that provides common functionality for all scrapers.
    - **`scraper_factory.py`**: A factory for creating scraper instances based on the configuration.
    - **`standard_scraper.py`, `iframe_scraper.py`, etc.**: Concrete scraper implementations for different types of job boards.
- **`legacy_scrapers/`**: Contains the original scraper scripts, which are still functional but deprecated.
- **`functions.py`**: A utility module with common functions for web scraping and API interaction.
- **`logging_config.py`**: Configures structured logging for the application.
- **`cache/`**: A directory where the raw HTML content of scraped job postings is stored.
- **`processed_jobs.csv`**: The output CSV file containing the processed and rated job postings.

## How it Works

1.  **Configuration**: Define the job boards you want to scrape and other settings in the `config.yaml` file. You can enable or disable scrapers, set API keys, and adjust job rating criteria.
2.  **Scraping**: Run the `run_scrapers.py` script to collect job postings. The script uses the configuration in `config.yaml` to determine which sites to scrape.
    ```bash
    # Run all enabled scrapers
    python run_scrapers.py

    # Run a specific group of scrapers
    python run_scrapers.py --group workday
    ```
3.  **Processing**: After scraping, run the `process_jobs.py` script to analyze the collected jobs. This script reads the cached job postings, extracts the relevant text, and sends it to the OpenAI API along with your resume.
    ```bash
    # Process all cached jobs
    python process_jobs.py
    ```
4.  **Rating**: The AI model evaluates each job description against your resume and returns a structured set of ratings for experience, education, skills, and interest.
5.  **Output**: The processed data, including the ratings, is saved to `processed_jobs.csv`. The script also generates ranked lists of jobs to help you identify the most promising opportunities.

## Dependencies

This project relies on several Python libraries. You can install them using pip:

```bash
pip install openai playwright selenium beautifulsoup4 trafilatura pandas geopy tqdm pyyaml undetected-chromedriver aiofiles python-dotenv pyppeteer pyppeteer-stealth termcolor
```

You also need to install the Playwright browser dependencies:

```bash
playwright install
```

## Usage

1.  **Installation**: Install the required Python libraries as described above.
2.  **Configuration**:
    -   Create a `.env` file in the root directory and add your OpenAI API key:
        ```
        OPENAI_API_KEY="your_openai_api_key"
        ```
    -   Update `config.yaml` to specify the job boards you want to scrape. You can enable/disable sites and groups by setting the `enabled` flag to `true` or `false`.
    -   Place your resume file (e.g., `resume.md`) in the root directory and ensure the path is correctly set in `config.yaml`.
3.  **Scraping**: Run the `run_scrapers.py` script to start collecting job postings.
    ```bash
    # Run all enabled scrapers
    python run_scrapers.py

    # To see a list of all available scrapers
    python run_scrapers.py --list
    ```
4.  **Processing**: After scraping is complete, run the `process_jobs.py` script to rate the collected jobs.
    ```bash
    python process_jobs.py
    ```
    You can customize the processing with various command-line arguments. For example, to force reprocessing of all jobs:
    ```bash
    python process_jobs.py --force
    ```
5.  **Review Results**: Open `processed_jobs.csv` to see the rated job postings. You can also check the `ranked_jobs.csv` and `high_quality_matches_*.csv` files for filtered and ranked lists of jobs.