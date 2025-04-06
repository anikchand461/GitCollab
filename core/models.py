from django.db import models
from django.contrib.auth.models import User

class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name

class Project(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    repo_link = models.URLField()
    description = models.TextField(max_length=500)
    contributors_needed = models.PositiveIntegerField(default=0)
    likes = models.ManyToManyField(User, related_name='liked_projects', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    buy_me_a_coffee = models.BooleanField(default=False)  # New field
    patreon = models.BooleanField(default=False)         # New field
    paypal = models.BooleanField(default=False)          # New field
    desired_skills = models.ManyToManyField(Skill, blank=True, related_name='projects')  # New field


    def __str__(self):
        return f"{self.owner.username} - {self.repo_link}"

class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

class ContributorRequest(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='requests')
    requester = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, null=True)
    readme = models.TextField(blank=True, null=True)  
    twitter = models.URLField(blank=True, null=True)
    linkedin = models.URLField(blank=True, null=True)
    buy_me_a_coffee = models.URLField(blank=True, null=True)  
    patreon = models.URLField(blank=True, null=True)  
    paypal = models.URLField(blank=True, null=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name='profiles')
    access_token = models.CharField(max_length=40, blank=True, null=True)  # New field

    def reputation_score(self):
        # Example logic for reputation score
        return 42  # Replace with actual logic

    def masked_access_token(self):
        if self.access_token:
            return '•' * len(self.access_token)  # Mask the token
        return None


    def reputation_score(self):
        # Sum of likes from all projects owned by this user
        return sum(project.likes.count() for project in self.user.projects.all())

    def __str__(self):
        return f"{self.user.username}'s Profile"