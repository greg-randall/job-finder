#!/usr/bin/env python3
"""
Test script to figure out the correct way to access element attributes in nodriver.
"""

import asyncio
import nodriver as uc


async def test_element_attributes():
    """Test different ways to access element attributes."""
    browser = None

    try:
        print("="*80)
        print("Testing nodriver element attribute access")
        print("="*80)

        # Initialize browser
        print("\n1. Initializing browser...")
        browser = await uc.start(headless=True)
        print("   ✓ Browser initialized")

        # Navigate to a test page with links
        print("\n2. Navigating to example.com...")
        tab = await browser.get('https://example.com')
        await asyncio.sleep(2)
        print("   ✓ Navigation successful")

        # Try to find a link element
        print("\n3. Finding link element...")
        link = await tab.select('a')

        if link:
            print(f"   ✓ Found link element: {type(link)}")
            print(f"   Element type: {link.__class__.__name__}")

            # Check what attributes/methods are available
            print("\n4. Inspecting element attributes...")
            attrs = [attr for attr in dir(link) if not attr.startswith('_')]
            print(f"   Available attributes/methods: {', '.join(attrs[:20])}")

            # Try different ways to access href
            print("\n5. Testing different attribute access methods...")

            # Method 1: Direct property access
            try:
                href_direct = link.href
                print(f"   ✓ link.href = {href_direct}")
            except Exception as e:
                print(f"   ✗ link.href failed: {str(e)}")

            # Method 2: attrs dict
            try:
                if hasattr(link, 'attrs'):
                    print(f"   link.attrs type: {type(link.attrs)}")
                    print(f"   link.attrs contents: {link.attrs}")
                    if isinstance(link.attrs, dict):
                        href_attrs = link.attrs.get('href')
                        print(f"   ✓ link.attrs.get('href') = {href_attrs}")
                else:
                    print(f"   ✗ link.attrs does not exist")
            except Exception as e:
                print(f"   ✗ link.attrs.get('href') failed: {str(e)}")

            # Method 3: attributes property
            try:
                if hasattr(link, 'attributes'):
                    print(f"   link.attributes type: {type(link.attributes)}")
                    print(f"   link.attributes contents: {link.attributes}")
                else:
                    print(f"   ✗ link.attributes does not exist")
            except Exception as e:
                print(f"   ✗ link.attributes failed: {str(e)}")

            # Method 4: get_attribute method (if it exists)
            try:
                if hasattr(link, 'get_attribute'):
                    href_method = await link.get_attribute('href')
                    print(f"   ✓ link.get_attribute('href') = {href_method}")
                else:
                    print(f"   ✗ link.get_attribute does not exist")
            except Exception as e:
                print(f"   ✗ link.get_attribute('href') failed: {str(e)}")

            # Method 5: Use JavaScript to get the href
            try:
                # First get element properties using JavaScript
                href_js = await link.apply('el => el.href')
                print(f"   ✓ element.apply('el => el.href') = {href_js}")
            except Exception as e:
                print(f"   ✗ element.apply() failed: {str(e)}")

            # Method 6: Try to access the text content
            try:
                if hasattr(link, 'text'):
                    text = await link.text if asyncio.iscoroutinefunction(link.text) else link.text
                    print(f"   ✓ link.text = {text}")
            except Exception as e:
                print(f"   ✗ link.text failed: {str(e)}")
        else:
            print("   ✗ No link element found")

        print("\n" + "="*80)
        print("Test complete!")
        print("="*80)

        return True

    except Exception as e:
        print(f"\n❌ Error occurred: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

    finally:
        if browser:
            browser.stop()


if __name__ == "__main__":
    asyncio.run(test_element_attributes())
