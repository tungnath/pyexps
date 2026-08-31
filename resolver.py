import requests

def get_final_url(start_url, timeout=10):
    """
    Follows redirects and returns the final URL.
    
    :param start_url: The initial URL (possibly shortened or redirecting)
    :param timeout: Timeout in seconds for the request
    :return: Final resolved URL or None if failed
    """
    try:
        # Send a HEAD request first to avoid downloading the full content
        response = requests.head(start_url, allow_redirects=True, timeout=timeout)
        
        # If HEAD fails (some servers block it), fallback to GET
        if response.status_code >= 400 or not response.url:
            response = requests.get(start_url, allow_redirects=True, timeout=timeout)
        
        return response.url  # Final resolved URL
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    url = input("Enter the URL to check: ").strip()
    final_url = get_final_url(url)
    
    if final_url:
        print(f"Final URL: {final_url}")
    else:
        print("Could not resolve the final URL.")
		
		
# How It Works
# HEAD request first – avoids downloading large files unnecessarily.
# Fallback to GET – in case the server blocks HEAD requests.
# allow_redirects=True – automatically follows all HTTP 3xx redirects.
# Error handling – catches network errors, timeouts, and invalid URLs.