# chat/consumers.py
import json
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
import random
from channels.layers import get_channel_layer

from . models import PairedUser, ActiveUser, OnlineUsers




class UserInfos():

    def save_paired_user(user, stranger):
        User = PairedUser()
        User.user_id = user
        User.stranger_id = stranger
        User.save()
        # stranger
        Stranger = PairedUser()
        Stranger.user_id = stranger
        Stranger.stranger_id = user
        Stranger.save()

    def delete_paired_user(user, stranger):
        User = PairedUser.objects.get(user_id=user)
        User.delete()
        # stranger
        Stranger = PairedUser.objects.get(user_id=stranger)
        Stranger.delete()

    def save_active_user(user):
        User = ActiveUser()
        User.user_id = user
        User.save()

    def delete_active_user(user):
        User = ActiveUser.objects.get(user_id=user)
        User.delete()


    def send_user_number(self):
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type':'display_number_of_users'
            })


    def send_connected_info(self):
        async_to_sync(self.channel_layer.send)(
        self.channel_name,
        {
            'type': 'connected_with_stranger',
        })
        async_to_sync(self.channel_layer.send)(
        PairedUser.objects.get(user_id=self.channel_name).stranger_id,
        {
            'type': 'connected_with_stranger',
        })


    def connect_with_user(self):

        if len(ActiveUser.objects.all()) < 1:
            # Save waiting user to database
            UserInfos.save_active_user(self.channel_name)
            
        elif len(ActiveUser.objects.all()) >= 1 and self.channel_name not in ActiveUser.objects.all():
            # get active user from database and delete him
            stranger = ActiveUser.objects.first().user_id
            UserInfos.delete_active_user(stranger)
            # save connected pair to database
            UserInfos.save_paired_user(self.channel_name, stranger)
            # Send info that users are connected
            UserInfos.send_connected_info(self)
          


    def disconnect_with_stranger(self):

        try:
            # if user has pair
            stranger = PairedUser.objects.get(user_id=self.channel_name).stranger_id
            # Send stranger info that you disconnected
            async_to_sync(self.channel_layer.send)(
                stranger,
                {
                    'type': 'disconnected_with_stranger',
                }
            )
            
            # delete disconnected pair from database
            UserInfos.delete_paired_user(self.channel_name, stranger)

        except:
            #if user was in waiting room
            UserInfos.delete_active_user(self.channel_name)


    def send_typing_info(self):
        user = self.channel_name

        # Send typing info to connected user
        async_to_sync(self.channel_layer.send)(
            PairedUser.objects.get(user_id=self.channel_name).stranger_id,
            {
                'type': 'typing',
                'message': user,
            }
        )
        # Send typing info to yourself
        async_to_sync(self.channel_layer.send)(
            self.channel_name,
            {
                'type': 'typing',
                'message': user,
            }
        )

    def send_user_message(self, text_data_json):
        try:
            message = text_data_json['message']
            user = self.channel_name
            message = str(user) + ' ' + message

            # Send message to connected user
            async_to_sync(self.channel_layer.send)(
                PairedUser.objects.get(user_id=self.channel_name).stranger_id,
                {
                    'type': 'chat_message',
                    'message': message,
                }
            )
            # Send message to yourself
            async_to_sync(self.channel_layer.send)(
                self.channel_name,
                {
                    'type': 'chat_message',
                    'message': message,
                }
            )
        except:
            pass




# define all actions after websocket connection
class ChatConsumer(WebsocketConsumer):
    
    def connect(self):
        self.room_name = 'room'
        self.room_group_name = '%s' % self.room_name
    
        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )

        self.accept()

        #if join room connect with stranger
        UserInfos.connect_with_user(self)

        # send user number to frontend
        UserInfos.send_user_number(self)

        # update number of online users
        if OnlineUsers.objects.all():
            users_number = OnlineUsers.objects.first().number + 1
            online_users_number = OnlineUsers.objects.first()
            online_users_number.number = users_number
            online_users_number.save()
            

        else:
            user_nubmer = OnlineUsers()
            user_nubmer.number = 1
            user_nubmer.save()
        



    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

        # update online user number
        users_number = OnlineUsers.objects.first().number - 1
        online_users_number = OnlineUsers.objects.first()
        online_users_number.number = users_number
        online_users_number.save()
        # send user number to frontend
        UserInfos.send_user_number(self)


    # Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)

        try:
            if text_data_json['action'] == 'typing':
                #send typing info
               UserInfos.send_typing_info(self)

            if text_data_json['action'] == 'leave':
                # disconnect with stranger (not with server)
                UserInfos.disconnect_with_stranger(self)

            if text_data_json['action'] == 'connect_new':
                # connect with new stranger
                UserInfos.connect_with_user(self)
            
            
        except:
            # Send user message
            UserInfos.send_user_message(self, text_data_json)



    # Receive message from room group
    def chat_message(self, event):

        # split after first space
        sender = event['message'].split(' ',1)[0]
        message = event['message'].split(' ',1)[1]

        if self.channel_name == sender:
            message_type = 'sender'
        else:
            message_type = 'receiver'

        # Send message to WebSocket and then handle it with javascript
        self.send(text_data=json.dumps({
            'message_type': message_type,
            'message': message
        }))


    # Display if user is typing
    def typing(self, event):

        if self.channel_name != event['message']:
            # Send info that user is typing
            self.send(text_data=json.dumps({
                'message_type': 'typing',
                'message': True
            }))




    def connected_with_stranger(self, event):
        self.send(text_data=json.dumps({
            'message_type': 'connected_with_stranger',
        }))

    def disconnected_with_stranger(self, event):
        self.send(text_data=json.dumps({
            'message_type': 'disconnected_with_stranger',
        }))

    
    def display_number_of_users(self, event):
        number_of_users = OnlineUsers.objects.first().number
        self.send(text_data=json.dumps({
            'message_type': 'number_of_users',
            'number_of_users':number_of_users
        }))
