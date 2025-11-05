# Job Finder - Architecture Documentation

## Overview

This project has been refactored into a mature, configuration-driven system for scraping job boards and matching them against candidate profiles using AI.

## Key Features

✅ **YAML Configuration** - All settings in one place (`config.yaml`)
✅ **Unified Scraper Architecture** - Consistent interface for all job boards
✅ **Factory Pattern** - Automatic scraper selection based on site type
✅ **Single Entry Point** - One command to run all scrapers
✅ **Easy Extensibility** - Add new job boards without writing code
✅ **Backward Compatible** - Old scraper files still work

## Architecture

### Configuration System

**config.yaml** - Central configuration file containing:
- OpenAI settings (model, temperature)
- Location settings (coordinates, radius, cities)
- Job rating weights and thresholds
- File paths
- Browser settings (timeouts, retries, user agent)
- **Job boards** - All scraper configurations

**config_loader.py** - Configuration management:
```python
from config_loader import get_config

config = get_config()
model = config.get('openai.model')  # Dot notation access
sites = config.get_enabled_sites()  # Get all enabled sites
```

### Scraper Architecture

#### Base Classes

**BaseScraper** (`scrapers/base_scraper.py`)
- Abstract base class for all scrapers
- Provides common functionality:
  - Browser initialization and cleanup
  - Navigation with retries
  - Job downloading and caching
  - Statistics tracking
  - Logging integration

#### Scraper Types

1. **StandardScraper** - For traditional pagination (Workday, ApplicantPro)
   - Uses CSS selectors for job links
   - Click-based pagination with next/previous buttons

2. **IframeScraper** - For iframe-based sites (iCIMS)
   - Switches to iframe context
   - Handles pagination within iframe
   - Custom disabled-button detection

3. **URLPaginationScraper** - For URL-based pagination (CareerPlug)
   - Constructs page URLs (`?page=1`, `?page=2`, etc.)
   - Stops when empty page found
   - Random delays between pages

4. **CustomClickScraper** - For click-through sites (ADP)
   - Clicks individual job buttons
   - Extracts content inline
   - Handles back navigation

5. **CustomNavigationScraper** - For unique navigation (Virginia State)
   - Custom URL construction
   - Cookie consent handling
   - Set-based deduplication

#### Factory Pattern

**scraper_factory.py** - Creates appropriate scraper instances:
```python
from scrapers import create_scraper

scraper = create_scraper(site_config)
result = await scraper.scrape()
```

### Entry Points

#### For Scraping

**run_scrapers.py** - Unified scraper runner:

```bash
# Run all enabled scrapers
python run_scrapers.py

# Run specific group
python run_scrapers.py --group workday

# Run specific site
python run_scrapers.py --site bbinsurance

# List all available scrapers
python run_scrapers.py --list
```

#### For Processing

**process_jobs.py** - AI-powered job matching:

```bash
# Process all cached jobs
python process_jobs.py

# Use custom resume and weights
python process_jobs.py --resume my_resume.md --exp-weight 0.4
```

## Adding New Job Boards

### Option 1: Via Configuration Only

For sites that match existing patterns, just add to `config.yaml`:

```yaml
job_boards:
  - group: "workday"
    type: "standard"
    enabled: true
    selectors:
      job_link: '[data-automation-id="jobTitle"]'
      next_page: '[data-uxi-widget-type="stepToNextButton"]:not([disabled])'
      next_page_disabled: '[data-uxi-widget-type="stepToNextButton"][disabled]'
    sites:
      - name: "new_company"
        url: "https://new_company.wd1.myworkdayjobs.com/Careers"
        enabled: true
```

### Option 2: Custom Scraper Type

For completely unique sites:

1. Create new scraper class inheriting from `BaseScraper`
2. Implement `extract_job_links()` and `navigate_to_next_page()`
3. Register with factory:
```python
from scrapers import register_scraper_type

register_scraper_type('my_custom', MyCustomScraper)
```

## Configuration Examples

### Adjusting AI Rating Weights

```yaml
rating:
  weights:
    experience: 0.40  # Increase experience weight
    education: 0.10   # Decrease education weight
    skills: 0.35
    interest: 0.15
  thresholds:
    high_quality: 7.0  # Stricter threshold
    min_category_score: 6
```

### Changing Location

```yaml
location:
  primary_city: "Austin"
  coordinates:
    latitude: 30.2672
    longitude: -97.7431
  radius_miles: 30
  area_cities:
    - austin
    - round rock
    - cedar park
```

### Browser Tuning

```yaml
browser:
  headless: false  # Show browser for debugging
  timeouts:
    page_load_ms: 30000  # Increase for slow sites
  retries:
    max_retries: 5  # More retries
```

### Disabling/Enabling Sites

```yaml
sites:
  - name: "slowsite"
    url: "https://..."
    enabled: false  # Temporarily disable

  - name: "newsite"
    url: "https://..."
    enabled: true   # Enable new site
```

## File Structure

```
job-finder/
├── config.yaml              # Central configuration
├── config_loader.py         # Config management
├── run_scrapers.py         # Unified entry point
├── process_jobs.py         # Job processing & AI matching
├── functions.py            # Shared scraping utilities
├── logging_config.py       # Logging setup
├── scrapers/               # Scraper architecture
│   ├── __init__.py
│   ├── base_scraper.py     # Abstract base class
│   ├── standard_scraper.py
│   ├── iframe_scraper.py
│   ├── url_pagination_scraper.py
│   ├── custom_click_scraper.py
│   ├── custom_navigation_scraper.py
│   └── scraper_factory.py
├── scraper_*.py            # Legacy scrapers (still work)
├── cache/                  # Cached job postings
└── README.md              # User documentation
```

## Migration Notes

### For Existing Users

**The old scraper files still work!** You can continue using:
```bash
python scraper_workday.py
python scraper_icims.py
```

**Or migrate to the new system:**
```bash
python run_scrapers.py --group workday
python run_scrapers.py --group icims
```

### Benefits of New System

1. **Single configuration file** - No more editing Python files
2. **Enable/disable sites** - Toggle sites without code changes
3. **Consistent logging** - All scrapers use same format
4. **Better error handling** - Unified error capture
5. **Easier testing** - Test configurations without code
6. **Version control friendly** - Config changes don't mix with code

## Development

### Running Tests

```bash
# Test config loading
python -c "from config_loader import get_config; print(get_config().get_enabled_sites())"

# List all scrapers
python run_scrapers.py --list

# Test single site
python run_scrapers.py --site bbinsurance
```

### Debugging

1. Enable debug mode in config:
```yaml
processing:
  debug: true
```

2. Run with visible browser:
```yaml
browser:
  headless: false
```

3. Check logs in `logs/` directory

### Extending

To add a new scraper type:

```python
# my_custom_scraper.py
from scrapers.base_scraper import BaseScraper

class MyCustomScraper(BaseScraper):
    async def extract_job_links(self):
        # Your custom logic
        pass

    async def navigate_to_next_page(self):
        # Your custom logic
        pass

# Register it
from scrapers import register_scraper_type
register_scraper_type('my_custom', MyCustomScraper)
```

Then use in config:
```yaml
job_boards:
  - group: "my_sites"
    type: "my_custom"
    ...
```

## Performance Tips

1. **Parallel workers**: Adjust for your CPU
```yaml
processing:
  parallel_workers: 16  # Reduce if system struggles
```

2. **Timeouts**: Increase for slow networks
```yaml
browser:
  timeouts:
    page_load_ms: 30000
```

3. **Caching**: Jobs are cached automatically
   - Rerunning scrapers skips already downloaded jobs
   - Delete `cache/` to force re-download

## Troubleshooting

### "Config file not found"
- Ensure `config.yaml` exists in project root
- Or specify: `python run_scrapers.py --config /path/to/config.yaml`

### "No enabled sites found"
- Check `enabled: true` in config
- Run `python run_scrapers.py --list` to verify

### "Scraper type not recognized"
- Check `type:` matches available types
- Available: standard, iframe, url_pagination, custom_click, custom_navigation

### Dependencies
Ensure all packages are installed:
```bash
pip install playwright aiofiles trafilatura openai pandas geopy tqdm pyyaml
playwright install
```

## Future Enhancements

Potential improvements:
- [ ] Database backend for job storage
- [ ] Web UI for configuration
- [ ] Scheduled scraping with cron
- [ ] Email notifications for high-quality matches
- [ ] Integration with job application APIs
- [ ] Multi-location support
- [ ] Custom LLM providers (Claude, Gemini, etc.)

## Support

For issues or questions:
1. Check this documentation
2. Review `config.yaml` comments
3. Check logs in `logs/` directory
4. Review error messages carefully

## License

[Your License Here]
