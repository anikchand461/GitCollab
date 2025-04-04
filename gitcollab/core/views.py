from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import Http404
from .models import Project, Comment, ContributorRequest
import requests
from social_django.models import UserSocialAuth
from django.contrib import messages
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

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
    projects = Project.objects.all()
    return render(request, 'home.html', {'projects': projects})

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
        Project.objects.create(
            owner=request.user,
            repo_link=repo_link,
            description=description,
            contributors_needed=contributors_needed
        )
        return redirect('home')
    return render(request, 'create_project.html')

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if request.method == 'POST':
        if 'comment' in request.POST:
            Comment.objects.create(project=project, user=request.user, text=request.POST['comment'])
        elif 'like' in request.POST:
            project.likes.add(request.user)
        elif 'request_join' in request.POST:
            ContributorRequest.objects.create(project=project, requester=request.user)
            messages.success(request, 'Request sent to project owner!')

    return render(request, 'project_detail.html', {'project': project})

@login_required
def manage_requests(request):
    projects = Project.objects.filter(owner=request.user)
    if not projects.exists():
        return render(request, 'manage_requests.html', {'message': 'You have no projects with contributor requests.'})
    contributor_requests = ContributorRequest.objects.filter(project__in=projects, status='pending')
    
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