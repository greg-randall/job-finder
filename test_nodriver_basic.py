#!/usr/bin/env python3
"""
Simple nodriver test to verify basic functionality.

This script tests:
1. Browser initialization
2. Page navigation
3. Content extraction
4. Proper cleanup

Usage:
    python3 test_nodriver_basic.py
"""

import asyncio
import sys
import nodriver as uc


async def test_basic_nodriver():
    """Test basic nodriver functionality."""
    browser = None

    try:
        print("="*80)
        print("Starting nodriver basic test")
        print("="*80)

        # Initialize browser
        print("\n1. Initializing browser...")
        browser = await uc.start(
            headless=False,  # Set to True to run headless
            browser_args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        print("   ✓ Browser initialized successfully")

        # Navigate to a simple page
        print("\n2. Navigating to example.com...")
        tab = await browser.get('https://example.com')
        print("   ✓ Navigation successful")

        # Wait a moment for the page to load
        await asyncio.sleep(2)

        # Get page title
        print("\n3. Getting page title...")
        title = await tab.evaluate('document.title')
        print(f"   ✓ Page title: {title}")

        # Get page content
        print("\n4. Getting page content...")
        content = await tab.evaluate('document.body.innerText')
        print(f"   ✓ Content length: {len(content)} characters")
        print(f"\n   First 200 characters of content:")
        print(f"   {content[:200]}...")

        # Get current URL
        print("\n5. Getting current URL...")
        current_url = await tab.evaluate('window.location.href')
        print(f"   ✓ Current URL: {current_url}")

        print("\n" + "="*80)
        print("✓ All tests passed successfully!")
        print("="*80)

        return True

    except Exception as e:
        print(f"\n❌ Error occurred: {str(e)}")
        print(f"   Error type: {type(e).__name__}")

        import traceback
        print("\nFull traceback:")
        print(traceback.format_exc())

        return False

    finally:
        # Cleanup
        print("\n6. Cleaning up browser...")
        if browser:
            try:
                browser.stop()
                print("   ✓ Browser closed successfully")
            except Exception as e:
                print(f"   ⚠ Warning during cleanup: {str(e)}")


async def main():
    """Main entry point."""
    success = await test_basic_nodriver()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(1)
