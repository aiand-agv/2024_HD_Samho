import configparser
import os


# 옵션 가져오기
def get_configparser(option_title, option_name, default_value) -> str:
    now_dir = os.getcwd()
    file_path = os.path.join(now_dir, 'option.ini')

    option_value = str(default_value)
    if os.path.exists(file_path):
        config = configparser.ConfigParser()
        config.read(file_path, encoding='utf-8')
        option_value = config.get(option_title, option_name, fallback=option_value)
    return option_value