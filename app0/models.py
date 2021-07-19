from django.db import models
from django.contrib.postgres.fields import ArrayField


# Create your models here.
class Room(models.Model):
    roomName = models.CharField(max_length=500, default=None, primary_key=True)
    roomOwnerGroup = models.CharField(max_length=500, default=None)
    roomOwnerUserName = models.CharField(max_length=500, default=None)
    userNames = ArrayField(models.CharField(max_length=500), default=None, null=True)
    current_UserNames = ArrayField(models.CharField(max_length=500), default=None, null=True)
    userGroups = ArrayField(models.CharField(max_length=500), default=None)
    userNames_UserGroups_dict = models.JSONField(default=dict)
    userNames_ChannelName_dict = models.JSONField(default=dict)
    teamName_leadersUserName_dict = models.JSONField(default=dict, null=True)
    teamName_MembersUserName_dict = models.JSONField(default=dict, null=True)
    userName_teamName_dict = models.JSONField(default=dict, null=True)
    member_count = models.IntegerField(default=1)
    gameStatus = models.BooleanField(default=False)
    dayStat = models.JSONField(default=dict, null=True)
    fishCount = models.JSONField(default=dict, null=True)
    fishScore = models.JSONField(default=dict, null=True)
    fishTotalScore = models.JSONField(default=dict, null=True)

    def __str__(self):
        return self.roomName
