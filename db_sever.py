import asyncio
import copy
import json
import time
from string import whitespace

from influxdb_client import InfluxDBClient, Point
from datetime import datetime


#DB select 주기 = 30 sec

loop_period = 30
max_connection_count = 5
total_pump = 6
token = "lo3_ITMkhVF5jsVZIV0rttr8QLkcMex742KyNtljhX0SPRIW84S5c9gL3ZFIdbx26fsMLC5Qagd7kow24NQtaw=="
org = "hd"
bucket = "hd"
url = "http://localhost:8086"

class DBServer:
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.influx_db_flag = False
        # influx db setting
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.query_api = self.client.query_api()
        self.current_try_count = 5
        self.result = {}
        self.receive_data = {}
        self.receive_count = {}
        self.lock = asyncio.Lock()

        # Flux 쿼리 작성
    def influxdb_connection_check(self):
        try:
            self.client.ping()
            self.influx_db_flag = True
        except Exception as e :
            self.influx_db_flag = False
            print(f"Error, Do not connected InfluxDB")
        return self.influx_db_flag

    # 테스트 4시간 기준 데이터
    def get_query(self):
        query = '''
        from(bucket: "hd")
          |> range(start: -4h)
          |> filter(fn: (r) => r["_measurement"] == "hd")
        '''
        return query


    @staticmethod
    def hex_decode(hex_string) :
        byte_data = bytes.fromhex(hex_string)
        return byte_data.decode("utf-8")

    def parsing_data(self,tables):

        for table in tables:
            for record in table.records:
                value_time = record.get_time()
                value = record.get_value()
                try :
                    value_dict = json.loads(value)
                except json.JSONDecodeError:
                    print(f"Error decoding JSON : {value}")
                    continue

                if "data" in value_dict["payload"] :
                    data_value = value_dict["payload"]["data"]
                    data_value_dict = self.parsing_data_dict(data_value, value_time)
                    self.receive_data.update(data_value_dict)


    def parsing_data_dict(self, value, value_time):
        decode_value = self.hex_decode(value)

        if "S" in decode_value and "E" in decode_value:
            item = decode_value.split(",")
            number = int(item[1])

            temp_data = {
                "pump": int(item[2]) == 1,
                "drain": int(item[3]) == 1,
                "status": True,
                "receive_time": value_time
            }

            if number not in self.receive_data:
                self.receive_data[number] = temp_data
            else:
                exist_data = self.receive_data[number]
                if value_time > exist_data["receive_time"]:
                    self.receive_data[number] = temp_data

            self.receive_count[number] = 0
            return self.receive_data

    async def run(self):
        print(f"while loop")
        while not self.stop_event.is_set() :
            async with self.lock:
                self.influxdb_connection_check()
                print(f"before run check flag : {self.influx_db_flag}")
                #result 초기 세팅
                for i in range(total_pump):
                    item_temp = {"pump": None, "drain": None, "status": False, "receive_time": None}
                    item = {(int(i) + 1): item_temp}
                    self.result.update(item)

                    receive_item = {(int(i) + 1) : 0}
                    self.receive_count.update(receive_item)


                if self.influx_db_flag:

                    # query = get_query()
                    query = self.get_query()
                    tables = self.query_api.query(query)
                    self.parsing_data(tables)
                    # 데이터가 들어왔는지 count 하고
                    no_data_keys = set(self.result.keys()) - set(self.receive_data.keys())
                    for i in no_data_keys :
                        self.receive_count[i] += 1
                        if self.receive_count[i] >= max_connection_count :
                            self.result[i]["status"] = False
                            self.receive_count[i] = 0

                    self.result.update(self.receive_data)

                    print(f"TEST : {self.result}")
                await asyncio.sleep(loop_period)


if __name__ == "__main__":
    server = DBServer()
    server.run()

