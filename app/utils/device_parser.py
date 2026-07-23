def parse_user_agent(ua_string: str | None) -> tuple[str, str, str]:
    """
    Extract basic device, browser, and operating system properties from a User-Agent header.
    Returns a tuple of (device, browser, os) strings.
    """
    if not ua_string:
        return "Unknown Device", "Unknown Browser", "Unknown OS"
    
    ua_lower = ua_string.lower()
    
    # OS parsing
    if "windows" in ua_lower:
        client_os = "Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        client_os = "macOS"
    elif "linux" in ua_lower:
        client_os = "Linux"
    elif "android" in ua_lower:
        client_os = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        client_os = "iOS"
    else:
        client_os = "Unknown OS"

    # Browser parsing
    if "firefox" in ua_lower:
        client_browser = "Firefox"
    elif "edge" in ua_lower:
        client_browser = "Edge"
    elif "chrome" in ua_lower:
        client_browser = "Chrome"
    elif "safari" in ua_lower:
        client_browser = "Safari"
    else:
        client_browser = "Unknown Browser"

    # Device parsing
    if "mobile" in ua_lower or "iphone" in ua_lower or "android" in ua_lower:
        client_device = "Mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        client_device = "Tablet"
    else:
        client_device = "Desktop"

    return client_device, client_browser, client_os
