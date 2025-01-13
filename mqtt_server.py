import copy
import asyncio
import paho.mqtt.client as mqtt
import datetime
import json
import time
import random



# MQTT 설정
mqtt_broker = "192.168.1.121"
mqtt_port = 1883
mqtt_topic = "application/app/device/ac1f09fffe12824d/rx"
mqtt_client_id = f"client_{int(time.time())}_{random.randint(1000, 9999)}"

# 연결 횟수 제한
max_try_count = 5
connection_limit_sec = 60

class MQTTServer:
    def __init__(self):

        self.broker = mqtt_broker
        self.port = mqtt_port
        self.topic = mqtt_topic
        self.client_id = mqtt_client_id
        self.latest_message = None
        self.result = {}
        self.lock = asyncio.Lock()
        self.connection_try_count = 0
        self.message = "오류가 발생하였습니다"

        # MQTT 클라이언트 초기화
        self.client = mqtt.Client(client_id=self.client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        try:
                self.client.subscribe(self.topic, qos=1)
        except Exception as e :
            print("reconnect")
            self.message = "서버와 연결 중 오류가 발생하였습니다"
            self.server_reconnect()

    def on_message(self, client, userdata, message):
        print("on_message")
        try:
            # 메시지를 JSON 형식으로 디코딩
            payload = json.loads(message.payload.decode())

            # JSON에서 "payload" 키를 찾아 "data" 필드를 추출
            pre_data = payload.get("data", None)
            self.latest_message =  bytes.fromhex(pre_data).decode("utf-8", errors="ignore")
            if "S" in self.latest_message and "E" in self.latest_message:
                item = self.latest_message.split(",")
                temp_data = {
                    "pump": int(item[2]) == 1,
                    "drain": int(item[3]) == 1,
                    "status": True,
                    "receive_time": datetime.datetime.now()
                }
                self.result[item[1]] = temp_data

        except json.JSONDecodeError:
            print("Message is not a valid JSON format")
        except Exception as e:
            print(f"Error processing message: {e}")

    async def start(self):
        """MQTT 클라이언트 시작"""
        while True:
            try :
                if self.client.is_connected() is False:
                    self.client.connect(self.broker, self.port, 120)
                    self.client.loop_start()
                else:
                    # self.client.loop_forever()
                    await self.period_check_data()
            except :
                await self.server_reconnect()
            await asyncio.sleep(2)


    def stop(self):
        """MQTT 클라이언트 중지"""
        self.client.loop_stop()
        self.client.disconnect()

    async def server_reconnect(self):
        try:
            if not self.client.is_connected():
                self.message = "서버와 연결이 끊어졌습니다"
                self.client.reconnect()
        except Exception as e :
            self.message = "서버와 연결 중 오류가 발생하였습니다"

    async def get_result(self):
        """현재 저장된 결과 반환"""
        async with self.lock:
            print(f"RESULT : {self.result}")
            return copy.deepcopy(self.result)

    async def get_server_status(self):
        """MQTT 서버 연결 상태 반환"""
        async with self.lock:
            return self.client.is_connected()

    async def get_message(self):
        async with self.lock:
            return self.message

    async def period_check_data(self):
        """수신된 데이터를 파싱하여 저장"""
        if self.result:
            for item in self.result:
                receive_time = self.result[item]["receive_time"]
                now_time = datetime.datetime.now()
                diff_time = now_time - receive_time
                if diff_time.total_seconds() > connection_limit_sec:
                    self.result[item]["status"] = False


    async def periodic_receive(self, interval):
        """주기적으로 메시지를 확인하고 파싱"""
        await self.period_check_data()
        await asyncio.sleep(interval)

