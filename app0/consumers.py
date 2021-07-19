import json
import threading
import time

from asgiref.sync import sync_to_async, async_to_sync
from channels.consumer import AsyncConsumer
from channels.generic.websocket import AsyncWebsocketConsumer
from urllib import parse
from .models import Room


class MainFisherConsummer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.roomName = None
        self.groupName = None
        self.userName = None
        self.teamName = None

    async def connect(self):
        # user_name = None
        room_name = self.scope['url_route']['kwargs']['room_name']
        try:
            user_name = (parse.parse_qs(self.scope['query_string'])['username'.encode('ascii')])[0].decode('ascii')
            method = (parse.parse_qs(self.scope['query_string'])['method'.encode('ascii')])[0].decode('ascii')
        except:
            await self.close()
            print("connection closed !")
            return
        if user_name == '' or user_name is None:
            await self.close()
            print("connection closed !")
            return
        if method != 'joinroom' and method != 'createroom':
            await self.close()
            print("connection closed !")
            return
        group_name = room_name + '_' + user_name
        response, responsecode = await self.myconnect(room_name, user_name, group_name, method)
        if response == 'accept':
            data = {'status': 'succeed'}
            await self.channel_layer.group_add(
                self.groupName,
                self.channel_name
            )
            await self.accept()
            await self.send(text_data=json.dumps(data))
            # time.sleep(2)
            usernames = await self.get_all_usernames()
            for i in await self.get_all_groupnames():
                data = {'type': 'chat_msg', 'mtype': 'usernames_updated', 'usernames': usernames}
                await self.channel_layer.group_send(i, data)

        else:
            data = {'status': 'failed', 'status_code': responsecode}
            await self.accept()
            await self.send(text_data=json.dumps(data))
            await self.close()

    async def disconnect(self, channel_name):
        print('disconnected')
        if self.userName is None:
            await self.close()
            return
        if self.teamName is None:
            if self.userName != await self.get_roomownerusername():
                response = await self.mydisconnect(channel_name)
                usernames = await self.get_all_usernames()
                for i in await self.get_all_groupnames():
                    data = {'type': 'chat_msg', 'mtype': 'usernames_updated', 'usernames': usernames}
                    await self.channel_layer.group_send(i, data)
                await self.close()
            else:
                groupnames = await self.get_all_groupnames()
                response = await self.mydisconnect(channel_name)
                for i in groupnames:
                    data = {'type': 'chat_msg', 'mtype': 'room_cancelled'}
                    await self.channel_layer.group_send(i, data)
                await self.close()

    async def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data)
        if data['username'] != self.userName:
            await self.channel_layer.group_send(self.groupName,
                                                {'type': 'chat_msg', "status": "failed",
                                                 "status_code": "Username mismatch"})
            return
        if data['mtype'] == 'message':
            status, to_groupname = await self.myreceive(data)
            if status == 'succeed':
                data.pop('to')
                data['type'] = 'chat_msg'
                data['status'] = 'succeed'
                for i in to_groupname:
                    await self.channel_layer.group_send(i, data)
            else:
                await self.channel_layer.group_send(self.groupName,
                                                    {'type': 'chat_msg', "status": "failed",
                                                     "status_code": "You can't chat before starting the game"})
        elif data['mtype'] == 'option_picking':
            if data['choice'] == 1 or data['choice'] == 2:
                status, MembersUserName, userNames_UserGroups = await self.myreceive(data)
                if status == 'succeed':
                    data['type'] = 'chat_msg'
                    data['status'] = 'succeed'
                    for i in MembersUserName:
                        await self.channel_layer.group_send(userNames_UserGroups[i], data)
                else:
                    status_code = MembersUserName
                    data['type'] = 'chat_msg'
                    await self.channel_layer.group_send(self.groupName,
                                                        {'type': 'chat_msg', 'mtype': 'option_picking',
                                                         "status": "failed",
                                                         "status_code": status_code})
            else:
                return
        elif data['mtype'] == 'command':
            status, userNames_UserGroups, userName_teamName, teamName_MembersUserName, teamName_leadersUserName = await self.myreceive(
                data)
            if status == "member_required":
                await self.channel_layer.group_send(self.groupName,
                                                    {'type': 'chat_msg', "status": "failed",
                                                     "status_code": "member_required"})
            elif status == "succeed":
                for key, value in userName_teamName.items():
                    data = {'type': 'chat_msg', 'mtype': 'command', 'commandname': 'startgame', 'teamname': value,
                            'membersname': teamName_MembersUserName[value],
                            'leadername': teamName_leadersUserName[value]}
                    await self.channel_layer.group_send(userNames_UserGroups[key], data)
                data['type'] = 'start_game'
                threading.Thread(target=self.GameManager, args=(data,)).start()
                print('startgame data sent successful')
                # t=threading.Thread(self.GameManager())
                # t.start()
                # print('after starting a thread')

    @async_to_sync
    async def gamemanager_assist(self, data):
        await self.set_default_game_score()
        timer = 20

        for i in range(6):
            all_groupnames = await self.get_all_groupnames()
            print(all_groupnames)
            await self.day_started(i)
            data = {'type': 'game_controller', 'mtype': 'command', 'commandname': 'day_started', 'day': 'day' + str(i),
                    'timer': timer}
            for j in all_groupnames:
                await self.channel_layer.group_send(j, data)
            time.sleep(timer)
            all_groupnames = await self.get_all_groupnames()
            data = {'type': 'game_controller', 'mtype': 'command', 'commandname': 'day_ended', 'day': 'day' + str(i)}
            for j in all_groupnames:
                await self.channel_layer.group_send(j, data)
            count, score = await self.day_completed(i)
            data = {'type': 'chat_msg', 'mtype': 'score', 'count': count, 'profit': score}
            for j in all_groupnames:
                await self.channel_layer.group_send(j, data)
            print('day completed')

    def GameManager(self, data):
        self.gamemanager_assist(data)

    async def game_controller(self, event):
        event.pop('type')
        await self.send(text_data=json.dumps(event))

    async def chat_msg(self, event):
        event.pop('type')
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event))
        if event['mtype'] == 'room_cancelled':
            self.userName = None
            await self.close()

    @sync_to_async
    def myconnect(self, room_name, user_name, group_name, method):
        re = 'accept'
        if method == 'createroom':
            if len(Room.objects.filter(roomName=room_name)) == 0:
                new = Room(roomName=room_name, userNames=[user_name], roomOwnerGroup=group_name,
                           roomOwnerUserName=user_name,
                           userGroups=[group_name], userNames_UserGroups_dict={user_name: group_name},
                           userNames_ChannelName_dict={user_name: self.channel_name},
                           dayStat=dict(day0=None, day1=None, day2=None,
                                        day3=None, day4=None,
                                        day5=None, ))
                new.save()
            else:
                return 'close', 'room_unavilable'
        elif method == 'joinroom':
            if len(Room.objects.filter(roomName=room_name)) == 0:
                return 'close', 'room_unavilable'
            db_object = Room.objects.get(roomName=room_name)
            if db_object.member_count >= 16 or db_object.gameStatus is True:
                return 'close', 'room_unavilable'
            if group_name in db_object.userGroups:
                return 'close', 'username_exists'
            else:
                db_object.userNames.append(user_name)
                db_object.userGroups.append(group_name)
                db_object.userNames_UserGroups_dict[user_name] = group_name
                db_object.userNames_ChannelName_dict[user_name] = self.channel_name
                db_object.member_count += 1
                db_object.save()
        self.roomName = room_name
        self.userName = user_name
        self.groupName = group_name
        return re, None

    @sync_to_async
    def mydisconnect(self, channel_name):
        print(channel_name)
        self.close()
        if self.teamName is None:
            db_object = Room.objects.get(roomName=self.roomName)
            if db_object.roomOwnerUserName != self.userName:
                del db_object.userNames_UserGroups_dict[self.userName]
                del db_object.userNames_ChannelName_dict[self.userName]
                db_object.userNames.remove(self.userName)
                db_object.userGroups.remove(self.groupName)
                db_object.member_count -= 1
                db_object.save()
                return 'user_exited'
            else:
                db_object.delete()
                return 'room_cancelled'

    @sync_to_async
    def myreceive(self, data):
        username = data['username']
        if username == self.userName:
            if data['mtype'] == 'message':
                if data['to'] == 'all_members':
                    db_object = Room.objects.get(roomName=self.roomName)
                    if db_object.gameStatus:
                        to_username = list(
                            db_object.teamName_MembersUserName_dict[(db_object.userName_teamName_dict[username])])
                        to_groupname = []
                        for i in to_username:
                            to_groupname.append(db_object.userNames_UserGroups_dict[i])
                        return 'succeed', to_groupname
                    else:
                        return 'failed', None
            elif data['mtype'] == 'option_picking':
                db_object = Room.objects.get(roomName=self.roomName)
                print(data)
                if db_object.dayStat[data['day']] == 'started':
                    if data['username'] == db_object.teamName_leadersUserName_dict[data['teamname']]:
                        index = None
                        if data['teamname'] == 'team0':
                            index = 0
                        elif data['teamname'] == 'team1':
                            index = 1
                        elif data['teamname'] == 'team2':
                            index = 2
                        elif data['teamname'] == 'team3':
                            index = 3
                        db_object.fishCount[data['day']][index] = data['choice']
                        MembersUserName = list(db_object.teamName_MembersUserName_dict[data['teamname']])
                        userNames_UserGroups = db_object.userNames_UserGroups_dict
                        db_object.save()
                        return 'succeed', MembersUserName, userNames_UserGroups
                    else:
                        return 'failed', 'username teamname mismatch', None

                else:
                    return 'failed', 'wrong daydata', None

            elif data['mtype'] == 'command':
                if data['commandname'] == 'startgame':
                    db_object = Room.objects.get(roomName=self.roomName)
                    if data['username'] == db_object.roomOwnerUserName:
                        if db_object.member_count >= 4:
                            roomusernames = list(db_object.userNames)
                            userNames_UserGroups = db_object.userNames_UserGroups_dict
                            userName_teamName = {}
                            teamName_MembersUserName = {}
                            teamName_leadersUserName = {}
                            fishTotalScore = {}
                            for i in range(4):
                                teamname = 'team' + str(i)
                                teamName_MembersUserName[teamname] = []
                                teamName_leadersUserName[teamname] = None
                                fishTotalScore[teamname] = 0
                            for i in range(len(roomusernames)):
                                teamname = 'team' + str(i % 4)
                                userName_teamName[roomusernames[i]] = teamname
                                teamName_MembersUserName[teamname].append(roomusernames[i])
                            for i in range(4):
                                teamname = 'team' + str(i)
                                teamName_leadersUserName[teamname] = teamName_MembersUserName[teamname][0]
                            db_object.userName_teamName_dict = userName_teamName
                            db_object.teamName_MembersUserName_dict = teamName_MembersUserName
                            db_object.teamName_leadersUserName_dict = teamName_leadersUserName
                            db_object.fishTotalScore = fishTotalScore
                            db_object.gameStatus = True
                            db_object.save()
                            return "succeed", userNames_UserGroups, userName_teamName, teamName_MembersUserName, teamName_leadersUserName
                        else:
                            return "member_required", None, None, None, None

    @sync_to_async
    def get_all_groupnames(self):
        db_object = Room.objects.get(roomName=self.roomName)
        return list(db_object.userGroups)

    @sync_to_async
    def get_all_usernames(self):
        db_object = Room.objects.get(roomName=self.roomName)
        return list(db_object.userNames)

    @sync_to_async
    def get_roomownerusername(self):
        db_object = Room.objects.get(roomName=self.roomName)
        return db_object.roomOwnerUserName

    @sync_to_async
    def set_default_game_score(self):
        db_object = Room.objects.get(roomName=self.roomName)
        for i in range(6):
            day = 'day' + str(i)
            db_object.fishCount[day] = [1, 1, 1, 1]
        db_object.save()

    @sync_to_async
    def day_started(self, day):
        day_str = 'day' + str(day)
        db_object = Room.objects.get(roomName=self.roomName)
        db_object.dayStat[day_str] = 'started'
        db_object.save()

    @sync_to_async
    def day_completed(self, day):
        amount = 100
        day_str = 'day' + str(day)
        db_object = Room.objects.get(roomName=self.roomName)
        db_object.dayStat[day_str] = 'ended'
        fishCount = list(db_object.fishCount[day_str])
        profit = {1: None, 2: None}
        if fishCount.count(1) == 4:
            profit[1] = 25
            profit[2] = 25
        elif fishCount.count(1) == 3:
            profit[1] = 0
            profit[2] = 75
        elif fishCount.count(1) == 2:
            profit[1] = -12.5
            profit[2] = 50
        elif fishCount.count(1) == 1:
            profit[1] = -25
            profit[2] = -25
        if day == 4 or day == 6:
            amount = 200
        fishscore = []
        for i in fishCount:
            calculated = amount * (profit[i] / 100)
            fishscore.append(calculated)
        for i in range(len(fishscore)):
            db_object.fishTotalScore['team' + str(i)] += fishscore[i]
        db_object.fishScore = fishscore
        db_object.save()
        return fishCount, fishscore
