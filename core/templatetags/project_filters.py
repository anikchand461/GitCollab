from django import template
import requests
import base64

register = template.Library()

@register.filter
def get_readme_gist(username):
    try:
        # Fetch user’s public repos to find the default README (e.g., username/username repo)
        repo_url = f'https://api.github.com/repos/{username}/{username}/readme'
        response = requests.get(repo_url, headers={'Accept': 'application/vnd.github+json'})
        if response.status_code == 200:
            readme_data = response.json()
            content = base64.b64decode(readme_data['content']).decode('utf-8')
            return content[:200]  # Return first 200 characters
        return 'No profile README'
    except requests.RequestException:
        return 'Error fetching README'