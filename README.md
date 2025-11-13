# Job Scraper and Matcher

This project is a sophisticated, configuration-driven framework for scraping job postings from various websites, discovering new job boards, processing the findings, and rating them against a candidate's resume using the OpenAI API.

## Key Features

- **Centralized Configuration**: All settings are managed in `config.yaml`, allowing for easy updates without code changes.
- **Unified Scraper Architecture**: A flexible architecture supports different types of job boards through a factory pattern.
- **Job Board Discovery**: Automatically find new job boards using search engines, powered by `nodriver`.
- **Single Entry Point**: `run_scrapers.py` script to run all or specific scrapers.
- **AI-Powered Job Matching**: `process_jobs.py` uses an AI model to rate and rank jobs based on your resume.
- **Extensible**: Easily add new job boards by updating the `config.yaml` file.

## Architecture Overview

This project uses a modular and configuration-driven architecture. For a detailed explanation of the system design, scraper types, and how to extend the system, please see the full **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Project Structure

- **`config.yaml`**: Central configuration for scrapers, API keys, and job rating.
- **`job_board_discovery_config.yaml`**: Configuration for the job board discovery feature.
- **`config_loader.py`**: Loads and provides access to settings from YAML files.
- **`run_scrapers.py`**: The main entry point for executing the job scrapers.
- **`run_job_board_finder.py`**: The entry point for discovering new job boards.
- **`job_board_finder.py`**: Core logic for the discovery feature.
- **`process_jobs.py`**: Script for processing cached job postings and rating them with an AI model.
- **`scrapers/`**: Modern, class-based scraper architecture.
  - **`base_scraper.py`**: Abstract base class for all scrapers.
  - **`scraper_factory.py`**: Factory for creating scraper instances.
  - **`standard_scraper.py`, `iframe_scraper.py`, etc.**: Concrete scraper implementations.
- **`legacy_scrapers/`**: Deprecated scraper scripts. See `legacy_scrapers/README.md` for details.
- **`functions.py`**: Utility module for web scraping and API interaction.
- **`logging_config.py`**: Configures structured logging.
- **`github_issue_handler.py`**: Manages automatic GitHub issue creation for errors.
- **`cache/`**: Stores raw HTML content of scraped job postings.
- **`discovered_job_boards.json`**: Output file for the job board discovery tool.
- **`processed_jobs.csv`**: Output CSV file with processed and rated job postings.

## How it Works

1.  **Discovery (Optional)**: Run the `run_job_board_finder.py` script to discover new job boards. This will generate `discovered_job_boards.json`.
    ```bash
    # Discover new job boards (runs 5 queries by default)
    python run_job_board_finder.py
    ```
2.  **Configuration**: Add newly discovered or known job boards to `config.yaml`. Enable/disable scrapers, set API keys, and adjust job rating criteria.
3.  **Scraping**: Run `run_scrapers.py` to collect job postings from the sites defined in `config.yaml`.
    ```bash
    # Run all enabled scrapers
    python run_scrapers.py

    # Run a specific group of scrapers
    python run_scrapers.py --group workday
    ```
4.  **Processing**: After scraping, run `process_jobs.py` to analyze the collected jobs. This script reads the cached job postings, extracts text, and sends it to the OpenAI API with your resume.
    ```bash
    # Process all cached jobs
    python process_jobs.py
    ```
5.  **Rating**: The AI model evaluates each job against your resume and returns ratings for experience, education, skills, and interest.
6.  **Output**: The processed data is saved to `processed_jobs.csv`. The script also generates ranked lists of jobs.

## Job Board Discovery

This project includes a powerful tool to automatically discover new job boards. It uses `nodriver` to perform searches on privacy-focused search engines, filtering out major job sites to identify smaller, niche boards.

- **Find new sources**: Automatically generates search queries (e.g., "richmond real estate jobs") to find potential job boards.
- **Smart Filtering**: Excludes known large job boards like Indeed and LinkedIn.
- **Scoring**: Ranks discovered sites based on job-related keywords.

For more details on how to configure and run the discovery tool, see the **[JOB_BOARD_FINDER_README.md](JOB_BOARD_FINDER_README.md)**.

## Dependencies

This project relies on several Python libraries. You can install them using pip:

```bash
pip install nodriver openai beautifulsoup4 trafilatura pandas geopy tqdm pyyaml aiofiles python-dotenv termcolor
```

You also need to have a version of **Chrome/Chromium** installed that is compatible with the `nodriver` library.

## Automatic Error Reporting

When a scraper fails or a job has insufficient content, the system automatically creates or updates a GitHub issue with comprehensive debugging information, including:

- Error details and stack traces
- Operation history (breadcrumbs)
- Statistics (pages scraped, jobs found, etc.)
- Debug artifacts (screenshots, HTML dumps, error context JSON)
- Console logs from the browser

Each scraper gets its own issue that is updated on subsequent failures, preventing duplicate issues.

**GitHub Authentication Required:**
This feature requires the GitHub CLI (`gh`) to be installed and authenticated.
```bash
# Install GitHub CLI (if not already installed)
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md

# Authenticate with GitHub
gh auth login
```

## Usage

1.  **Installation**: Install the required Python libraries as described above.
2.  **Configuration**:
    -   Create a `.env` file and add your OpenAI API key: `OPENAI_API_KEY="your_openai_api_key"`
    -   Update `config.yaml` to specify the job boards to scrape.
    -   Place your resume file (e.g., `resume.md`) in the root directory and set the path in `config.yaml`.
    -   **(Optional)** Set up GitHub CLI authentication for error reporting.
3.  **Scraping**: Run `run_scrapers.py` to collect job postings.
    ```bash
    # Run all enabled scrapers
    python run_scrapers.py

    # To see a list of all available scrapers
    python run_scrapers.py --list
    ```
4.  **Processing**: After scraping, run `process_jobs.py` to rate the jobs.
    ```bash
    python process_jobs.py
    ```
    You can customize processing with command-line arguments. For example, to force reprocessing:
    ```bash
    python process_jobs.py --force
    ```
5.  **Review Results**: Open `processed_jobs.csv` to see the rated job postings. You can also check `ranked_jobs.csv` and `high_quality_matches_*.csv` for filtered lists.