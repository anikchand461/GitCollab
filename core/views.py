from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from .models import Project, Comment, ContributorRequest, User, Profile
import requests
from social_django.models import UserSocialAuth
from django.contrib import messages
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from django.db.models import Min

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'login.html')

@login_required
def logout_view(request):
    auth_logout(request)
    return redirect('login')

@login_required
def home(request):
    # Step 1: Order projects by latest created first
    projects = Project.objects.all().order_by('-created_at')

    project_requests = {}

    for project in projects:
        # Step 2: Get unique users with pending requests (deduped by user)
        requests = (
            ContributorRequest.objects
            .filter(project=project, status='pending')
            .values('requester')  # group by requester
            .annotate(min_id=Min('id'))[:5]  # get one (earliest) request per user
        )

        request_user_info = []
        for req in requests:
            user = User.objects.get(id=req['requester'])  # Fetch the user once per ID
            avatar_url = f"https://github.com/{user.username}.png"
            request_user_info.append({
                'username': user.username,
                'avatar_url': avatar_url
            })

        project_requests[project.id] = request_user_info

    # Step 3: Fetch payment URLs from the owner's profile
    for project in projects:
        profile = Profile.objects.filter(user=project.owner).first()
        project.buy_me_a_coffee_url = profile.buy_me_a_coffee if profile and project.buy_me_a_coffee else None
        project.patreon_url = profile.patreon if profile and project.patreon else None
        project.paypal_url = profile.paypal if profile and project.paypal else None

    return render(request, 'home.html', {
        'projects': projects,
        'project_requests': project_requests
    })


@login_required
def create_project(request):
    if request.method == 'POST':
        repo_link = request.POST['repo_link'].strip()
        if not repo_link.startswith('https://github.com/') or len(repo_link.split('/')) < 5:
            return render(request, 'create_project.html', {'error': 'Invalid GitHub repository URL'})
        # Remove trailing slash and ensure proper format
        repo_link = repo_link.rstrip('/')
        description = request.POST['description']
        contributors_needed = request.POST['contributors_needed']
        # Get payment options from the form (checkboxes)
        buy_me_a_coffee = 'buy_me_a_coffee' in request.POST
        patreon = 'patreon' in request.POST
        paypal = 'paypal' in request.POST

        Project.objects.create(
            owner=request.user,
            repo_link=repo_link,
            description=description,
            contributors_needed=contributors_needed,
            buy_me_a_coffee=buy_me_a_coffee,
            patreon=patreon,
            paypal=paypal
        )
        return redirect('home')
    return render(request, 'create_project.html')

import logging
logger = logging.getLogger(__name__)

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == 'POST':
        # Handle AJAX like request
        if 'like' in request.POST and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if project.likes.filter(id=request.user.id).exists():
                project.likes.remove(request.user)
                liked = False
            else:
                project.likes.add(request.user)
                liked = True
            return JsonResponse({
                'liked': liked,
                'like_count': project.likes.count()
            })
        # Handle non-AJAX like request (fallback)
        elif 'like' in request.POST:
            if project.likes.filter(id=request.user.id).exists():
                project.likes.remove(request.user)
            else:
                project.likes.add(request.user)
            return redirect('project_detail', project_id=project_id)
        # Handle comment submission
        elif 'comment' in request.POST:
            Comment.objects.create(project=project, user=request.user, text=request.POST['comment'])
            messages.success(request, 'Comment added successfully.')
            return redirect('project_detail', project_id=project_id)
        # Handle join request
        elif 'request_join' in request.POST:
            # Check if request already exists to prevent duplicates
            if not ContributorRequest.objects.filter(project=project, requester=request.user).exists():
                ContributorRequest.objects.create(project=project, requester=request.user)
                messages.success(request, 'Request Sent')
            else:
                messages.info(request, 'You have already requested to join this project')
            return redirect('project_detail', project_id=project_id)
        # Handle comment deletion
        elif 'delete_comment' in request.POST:
            comment_id = request.POST.get('comment_id')
            comment = Comment.objects.filter(id=comment_id, user=request.user).first()
            if comment:
                comment.delete()
                messages.success(request, 'Comment deleted.')
            else:
                messages.error(request, 'You are not allowed to delete this comment.')
            return redirect('project_detail', project_id=project_id)

    return render(request, 'project_detail.html', {'project': project})

@login_required
def profile_view(request):
    # Get or create the user's profile
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        if 'import_readme' in request.POST:
            # Manual README import requested
            github_username = request.user.username
            readme_url = f"https://raw.githubusercontent.com/{github_username}/{github_username}/main/README.md"
            try:
                readme_response = requests.get(readme_url, timeout=5)
                if readme_response.status_code == 200:
                    profile.readme = readme_response.text
                    profile.save()
                    messages.success(request, 'README imported successfully.')
                else:
                    messages.error(request, f'Could not find a README for your GitHub profile (Status: {readme_response.status_code}).')
            except requests.RequestException as e:
                messages.error(request, f'Error connecting to GitHub: {str(e)}')
            return redirect('profile')
        else:
            # Normal profile update
            profile.bio = request.POST.get('bio', '')
            profile.readme = request.POST.get('readme', '')  # Save user-edited README
            profile.twitter = request.POST.get('twitter', '')
            profile.linkedin = request.POST.get('linkedin', '')
            profile.buy_me_a_coffee = request.POST.get('buy_me_a_coffee', '')
            profile.patreon = request.POST.get('patreon', '')
            profile.paypal = request.POST.get('paypal', '')
            profile.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')

    # Only fetch GitHub README on initial page load, not on every request
    github_username = request.user.username
    github_avatar = f"https://github.com/{github_username}.png"
    
    # Calculate reputation
    reputation = profile.reputation_score()
    
    # Convert README from markdown to HTML
    import markdown
    readme_html = markdown.markdown(profile.readme) if profile.readme else ""
    
    context = {
        'profile': profile,
        'github_username': github_username,
        'github_avatar': github_avatar,
        'reputation': reputation,
        'readme_html': readme_html,
        'is_new_user': created,  # Pass whether this is a new user
    }
    return render(request, 'profile.html', context)


@login_required
def manage_requests(request):
    projects = Project.objects.filter(owner=request.user)
    if not projects.exists():
        return render(request, 'manage_requests.html', {'message': 'You have no projects with contributor requests.'})
    raw_requests = ContributorRequest.objects.filter(project__in=projects, status='pending')

    contributor_requests = []
    for req in raw_requests:
        try:
            social = UserSocialAuth.objects.get(user=req.requester, provider='github')
            github_username = social.extra_data.get('login')
            avatar_url = f"https://github.com/{github_username}.png"
        except UserSocialAuth.DoesNotExist:
            github_username = req.requester.username
            avatar_url = None

        contributor_requests.append({
            'id': req.id,
            'requester': req.requester,
            'project': req.project,
            'github_username': github_username,
            'avatar_url': avatar_url,
        })

    
    if request.method == 'POST':
        req_id = request.POST['request_id']
        action = request.POST['action']
        req = get_object_or_404(ContributorRequest, id=req_id)
        if req.project.owner != request.user:
            raise Http404("You are not authorized to manage this request.")
        
        if action == 'accept':
            req.status = 'accepted'
            req.save()
            project = req.project
            if project.contributors_needed > 0:
                project.contributors_needed -= 1
            project.save()
            # Get requester's GitHub username
            try:
                requester_social = UserSocialAuth.objects.get(user=req.requester, provider='github')
                requester_username = requester_social.extra_data.get('login')
                if not requester_username:
                    return render(request, 'manage_requests.html', {
                        'requests': contributor_requests,
                        'error': 'Requester GitHub username not found'
                    })
            except UserSocialAuth.DoesNotExist:
                return render(request, 'manage_requests.html', {
                    'requests': contributor_requests,
                    'error': 'GitHub authentication data missing for requester'
                })
            
            # Construct GitHub collaborator page URL
            repo_parts = project.repo_link.rstrip('/').split('/')
            repo_owner = repo_parts[-2]
            repo_name = repo_parts[-1]
            github_collaborator_url = f'https://github.com/{repo_owner}/{repo_name}/settings/access'
            
            # Automate GitHub collaborator addition with Selenium
            driver = None  # Initialize driver outside try block
            try:
                # Set up Selenium WebDriver (Chrome)
                service = Service(executable_path='path/to/chromedriver')  # Replace with your ChromeDriver path
                options = webdriver.ChromeOptions()
                # options.add_argument('--headless')  # Uncomment for headless mode
                driver = webdriver.Chrome(service=service, options=options)
                
                # Navigate to GitHub collaborator page
                driver.get(github_collaborator_url)
                
                # Check if login is required
                if 'login' in driver.current_url:
                    return render(request, 'manage_requests.html', {
                        'requests': contributor_requests,
                        'error': 'Manual login required in browser for GitHub automation'
                    })
                
                # Wait for "Add People" button and click it
                add_people_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Add people')]"))
                )
                add_people_button.click()
                
                # Wait for the search input field and type the username
                search_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, 'collaborator-search-field'))
                )
                search_input.send_keys(requester_username)
                time.sleep(1)  # Wait for search results
                
                # Select the first username from the dropdown
                first_result = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'autocomplete-results')]//li[1]"))
                )
                first_result.click()
                
                # Click the "Add <username> to this repository" button
                add_collaborator_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(), 'Add {requester_username}')]"))
                )
                add_collaborator_button.click()
                
                # Wait briefly to ensure the action completes
                time.sleep(2)
                
                # Success message
                return render(request, 'manage_requests.html', {
                    'requests': contributor_requests,
                    'message': f'Successfully invited {requester_username} as a collaborator'
                })
            
            except Exception as e:
                return render(request, 'manage_requests.html', {
                    'requests': contributor_requests,
                    'error': f'Failed to automate GitHub invite: {str(e)}'
                })
            finally:
                if driver is not None:  # Only quit if driver was initialized
                    driver.quit()
        
        elif action == 'reject':
            req.status = 'rejected'
            req.save()
    
    return render(request, 'manage_requests.html', {'requests': contributor_requests})