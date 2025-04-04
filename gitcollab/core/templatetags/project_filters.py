from django import template
import requests
import base64

register = template.Library()

@register.filter
def get_readme_gist(username):
    try:
        url = f'https://api.github.com/repos/{username}/{username}/readme'
        response = requests.get(url, headers={'Accept': 'application/vnd.github+json'})
        if response.status_code == 200:
            content = base64.b64decode(response.json()['content']).decode('utf-8')
            return content[:200]
        return 'No profile README'
    except:
        return 'Error fetching README'