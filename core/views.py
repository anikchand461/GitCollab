from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from .models import Project, Comment, ContributorRequest
import requests
from social_django.models import UserSocialAuth

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
        repo_link = request.POST['repo_link']
        description = request.POST['description']
        contributors_needed = request.POST['contributors_needed']
        # Validate GitHub URL
        if not repo_link.startswith('https://github.com/') or len(repo_link.split('/')) < 5:
            return render(request, 'create_project.html', {'error': 'Invalid GitHub repository URL'})
        Project.objects.create(
            personally = request.user,
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
    return render(request, 'project_detail.html', {'project': project})

@login_required
def manage_requests(request):
    projects = Project.objects.filter(owner=request.user)
    contributor_requests = ContributorRequest.objects.filter(project__in=projects, status='pending')
    if request.method == 'POST':
        req_id = request.POST['request_id']
        action = request.POST['action']
        req = get_object_or_404(ContributorRequest, id=req_id)
        if action == 'accept':
            req.status = 'accepted'
            req.save()
            project = req.project
            project.contributors_needed -= 1
            project.save()
            # Send GitHub collaboration invite
            try:
                owner_social = UserSocialAuth.objects.get(user=project.owner, provider='github')
                requester_social = UserSocialAuth.objects.get(user=req.requester, provider='github')
                github_token = owner_social.access_token  # Owner's token to invite
                headers = {
                    'Authorization': f'token {github_token}',
                    'Accept': 'application/vnd.github+json'
                }
                repo_parts = project.repo_link.rstrip('/').split('/')
                repo_owner = repo_parts[-2]
                repo_name = repo_parts[-1]
                url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/collaborators/{requester_social.uid}'
                response = requests.put(url, headers=headers)
                if response.status_code == 201:
                    print(f"Collaboration invite sent to {requester_social.uid} for {repo_owner}/{repo_name}")
                elif response.status_code == 204:
                    print(f"{requester_social.uid} is already a collaborator or invite pending")
                else:
                    print(f"Failed to send invite: {response.status_code} - {response.text}")
            except UserSocialAuth.DoesNotExist:
                print("GitHub auth data missing for owner or requester")
            except Exception as e:
                print(f"Error sending invite: {str(e)}")
        elif action == 'reject':
            req.status = 'rejected'
            req.save()
    return render(request, 'manage_requests.html', {'requests': contributor_requests})