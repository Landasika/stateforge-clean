from django.db import models
from django.contrib.auth.models import User
import hashlib 
from django.core.exceptions import ValidationError  

class Challenge(models.Model):
    id = models.AutoField(primary_key=True, unique=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    docker_image = models.CharField(max_length=100, unique=True)
    docker_port = models.IntegerField()
    start_port = models.IntegerField()
    end_port = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    flag = models.CharField(max_length=100)
    point = models.IntegerField()
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self.start_port > self.end_port:
            raise ValidationError("Start port should be less than end port") 
        if self.flag:
            if not self.flag.startswith("hashed_"):
                self.flag = "hashed_" + hashlib.sha256(self.flag.encode('utf-8')).hexdigest()
        super(Challenge, self).save(*args, **kwargs)

class UserChallenge(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    container_id = models.CharField(max_length=100)
    port = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_live = models.BooleanField(default=False)
    no_of_attempt = models.IntegerField(default=0)
    is_solved = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user.username} - {self.challenge.name}"
