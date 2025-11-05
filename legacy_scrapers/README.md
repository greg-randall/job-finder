# Legacy Scrapers

⚠️ **These scrapers are deprecated and replaced by the new unified architecture.**

## What are these files?

These are the original individual scraper files that were used before the refactor to a configuration-driven system. Each file contained hardcoded URLs and scraping logic.

## Why were they replaced?

The new system offers:
- ✅ **Single configuration file** (`config.yaml`) instead of 15 Python files
- ✅ **Unified architecture** with consistent error handling
- ✅ **Easy enable/disable** of sites without code changes
- ✅ **Better maintainability** - update one base class instead of 15 files
- ✅ **Single entry point** (`run_scrapers.py`) instead of running each file

## How to use the new system

### Old way (deprecated):
```bash
python scraper_workday.py
python scraper_icims.py
python scraper_adp.py
# ... 15 separate commands
```

### New way:
```bash
# Run all scrapers
python run_scrapers.py

# Run specific group
python run_scrapers.py --group workday

# List all available
python run_scrapers.py --list
```

## Configuration

All job boards are now configured in `config.yaml`:

```yaml
job_boards:
  - group: "workday"
    type: "standard"
    sites:
      - name: "bbinsurance"
        url: "https://bbinsurance.wd1.myworkdayjobs.com/..."
        enabled: true
```

## Can I still use these?

**Technically yes**, but it's not recommended. The legacy scrapers will:
- ❌ Not benefit from unified error handling
- ❌ Not have consistent logging
- ❌ Require code changes for every site modification
- ❌ Not be maintained going forward

## Migration

All sites from these legacy scrapers have been migrated to `config.yaml`. See `ARCHITECTURE.md` for the new system documentation.

## Files Mapping

| Legacy File | New Location |
|------------|--------------|
| scraper_workday.py | config.yaml → workday group (17 sites) |
| scraper_applicantpro.py | config.yaml → applicantpro group (3 sites) |
| scraper_icims.py | config.yaml → icims group (4 sites) |
| scraper_careerplug.py | config.yaml → careerplug group (2 sites) |
| scraper_adp.py | config.yaml → adp group (2 sites) |
| scraper_virginia.py | config.yaml → virginia group (1 site) |
| All others | Individual sites in config.yaml |

## Delete these files?

These files are kept in `legacy_scrapers/` for reference. You can safely delete this entire folder once you're comfortable with the new system.

```bash
# When ready to fully clean up:
rm -rf legacy_scrapers/
```

---

**For documentation on the new system, see `ARCHITECTURE.md` in the project root.**
